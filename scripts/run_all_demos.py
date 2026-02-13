#!/usr/bin/env python3
"""Run all 3 AgenticOS demos in a single process.

Pre-acquires Azure AD token once and runs each demo sequentially.
No subprocess spawning to avoid KeyboardInterrupt issues.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

SYSTEM_PROMPT = """You are AgenticOS, an AI agent that controls a Windows desktop.
You can see the screen (screenshot) and the UI element tree (accessibility tree).

For each step, respond with ONLY a JSON object (no markdown, no extra text):
{
  "thought": "your reasoning about what to do next",
  "action": {
    "type": "<action_type>",
    "params": { ... }
  }
}

Available action types and their params:
- click: {"x": int, "y": int}
- double_click: {"x": int, "y": int}
- right_click: {"x": int, "y": int}
- type_text: {"text": "text to type"}
- press_key: {"key": "key name like enter, tab, escape"}
- hotkey: {"keys": ["ctrl", "s"]}
- scroll: {"x": int, "y": int, "clicks": -3}
- shell: {"command": "shell command to run"}
- open_app: {"app_name": "notepad"}
- wait: {"seconds": 1.0}
- done: {"success": true|false, "summary": "what was accomplished"}

When the task is fully complete, use "done" with success=true.
Use coordinates from the UI element tree (the center point values).
To open an application, prefer open_app with its name.
Do NOT repeat the same action more than twice. If an action isn't working, try an alternative approach."""


def run_single_demo(task: str, output: str, max_steps: int,
                    azure_ad_token: str, api_base: str, api_version: str):
    """Run a single demo and save GIF."""
    import litellm
    from agenticos.observation.screenshot import ScreenCapture
    from agenticos.grounding.accessibility import UIAGrounder
    from agenticos.actions.compositor import ActionCompositor, Action, ActionType
    from agenticos.observation.recorder import GifRecorder

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"  Task:     {task[:80]}...")
    print(f"  Output:   {output}")
    print(f"  Steps:    max {max_steps}")
    print()

    screen = ScreenCapture(monitor=1, scale=1.0)
    grounder = UIAGrounder()
    compositor = ActionCompositor()

    recorder = GifRecorder(fps=5, max_duration=120)
    recorder.start()

    steps = []
    success = False
    t_start = time.time()

    for step_num in range(1, max_steps + 1):
        print(f"  -- Step {step_num}/{max_steps} --")

        # Observe
        try:
            screenshot = screen.grab()
            b64 = screenshot.to_base64()
        except Exception as e:
            print(f"    Screenshot error: {e}")
            break

        import threading
        elements = []
        detect_done = threading.Event()
        def _detect():
            nonlocal elements
            try:
                elements = grounder.detect()
            except Exception:
                elements = []
            detect_done.set()
        t = threading.Thread(target=_detect, daemon=True)
        t.start()
        if not detect_done.wait(timeout=15):
            print(f"    UIA timeout (15s), using screenshot only")
        else:
            pass  # elements already set

        print(f"    {len(elements)} elements")

        elem_text = "\n".join(el.description() for el in elements[:50])
        if len(elements) > 50:
            elem_text += f"\n... ({len(elements) - 50} more)"

        history = ""
        if steps:
            history = "\n\nPrevious steps:\n" + "\n".join(
                f"  {s['step']}. [{s['action_type']}] {s['thought'][:80]}"
                for s in steps
            )

        # Think
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": [
                {"type": "text", "text": f"Task: {task}\n\nUI Elements:\n{elem_text}{history}\n\nNext action?"},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
            ]},
        ]

        print("    Thinking...", end=" ", flush=True)
        t0 = time.perf_counter()
        try:
            resp = litellm.completion(
                model="azure/gpt-4o",
                messages=messages,
                max_tokens=4096,
                temperature=0.1,
                azure_ad_token=azure_ad_token,
                api_base=api_base,
                api_version=api_version,
            )
            content = resp.choices[0].message.content
            dt = time.perf_counter() - t0
            print(f"({dt:.1f}s, {resp.usage.total_tokens} tok)")
        except Exception as e:
            print(f"\n    LLM error: {e}")
            break

        # Parse
        try:
            m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
            if m:
                parsed = json.loads(m.group(1))
            else:
                m = re.search(r'\{.*"action".*\}', content, re.DOTALL)
                parsed = json.loads(m.group()) if m else json.loads(content)

            thought = parsed.get("thought", "")
            act = parsed.get("action", {})
            action_type = act.get("type", "done")
            params = act.get("params", {})
        except Exception:
            print(f"    Parse fail: {content[:100]}...")
            continue

        print(f"    Thought: {thought[:100]}")
        print(f"    Action: {action_type}: {params}")

        steps.append({"step": step_num, "thought": thought,
                       "action_type": action_type, "action_params": params})

        try:
            recorder.add_annotation(f"Step {step_num}: {action_type}")
        except Exception:
            pass

        # Done check
        if action_type == "done":
            success = params.get("success", True)
            print(f"\n    {'SUCCESS' if success else 'FAILED'}: {params.get('summary', 'Done')}")
            break

        # Execute
        type_map = {"type": "type_text", "key_press": "press_key",
                    "key": "press_key", "open": "open_app"}
        mapped = type_map.get(action_type, action_type)

        try:
            action = Action(type=ActionType(mapped), params=params)
            result = compositor.execute(action)
            print(f"    {'OK' if result.success else 'WARN'}")
        except Exception as e:
            print(f"    Action error: {e}")

        time.sleep(1.5)
        try:
            recorder.add_annotation("")
        except Exception:
            pass

    elapsed = time.time() - t_start

    # Save
    recorder.stop()
    try:
        gif = recorder.save(str(output_path))
    except Exception:
        gif = None

    status = "SUCCESS" if success else "INCOMPLETE"
    print(f"\n  {status} - {len(steps)} steps in {elapsed:.1f}s")
    if gif:
        print(f"  GIF: {gif}")

    try:
        screen.close()
    except Exception:
        pass

    return success, len(steps), elapsed, gif


def main():
    print("=" * 70)
    print("  AgenticOS - Demo Suite (3 Demos)")
    print("=" * 70)
    print()

    # Acquire Azure AD token
    print("Acquiring Azure AD token...", end=" ", flush=True)
    from azure.identity import DefaultAzureCredential
    cred = DefaultAzureCredential()
    token = cred.get_token("https://cognitiveservices.azure.com/.default").token
    print("OK")
    print()

    API_BASE = "https://bugtotest-resource.cognitiveservices.azure.com/"
    API_VERSION = "2024-12-01-preview"

    demos = [
        {
            "name": "Demo 1: Settings - Brightness and Volume",
            "task": (
                "Open Windows Settings app. Navigate to Display settings and drag "
                "the brightness slider to 100 percent (all the way right). Then navigate "
                "to Sound settings and drag the volume slider to 10 percent (almost all the way left)."
            ),
            "output": "recordings/demo1_settings.gif",
            "max_steps": 20,
        },
        {
            "name": "Demo 2: Edge - 4K Video Fullscreen",
            "task": (
                "Open Microsoft Edge browser. In the address bar, go to youtube.com and "
                "search for '4k landscape video'. Click on the first video result. "
                "Make the video full screen by clicking the fullscreen button. Wait 10 seconds. "
                "Then press Escape to exit fullscreen, and click the pause button to pause the video."
            ),
            "output": "recordings/demo2_edge_video.gif",
            "max_steps": 20,
        },
        {
            "name": "Demo 3: Outlook Email and Teams Message",
            "task": (
                "Step 1: Open Microsoft Outlook. Click 'New mail' or 'New message' to compose a new email. "
                "Set the To field to jiaqizou@microsoft.com. Set the Subject to 'Sent from AgenticOS-Opus4.6'. "
                "Type 'hello' in the email body. Click Send. "
                "Step 2: Open Microsoft Teams. Use the search bar to find 'Jiaqi Zou'. "
                "Open a chat with Jiaqi Zou. Type 'Hi' in the message box and send it."
            ),
            "output": "recordings/demo3_outlook_teams.gif",
            "max_steps": 25,
        },
    ]

    results = []

    for i, demo in enumerate(demos, 1):
        print()
        print("=" * 70)
        print(f"  [{i}/3] {demo['name']}")
        print("=" * 70)

        ok, nsteps, elapsed, gif = run_single_demo(
            task=demo["task"],
            output=demo["output"],
            max_steps=demo["max_steps"],
            azure_ad_token=token,
            api_base=API_BASE,
            api_version=API_VERSION,
        )
        results.append((demo["name"], ok, nsteps, elapsed, gif))

        # Pause between demos to let UI settle
        if i < len(demos):
            print("\n  Waiting 5s before next demo...\n")
            time.sleep(5)

    # Final summary
    print()
    print("=" * 70)
    print("  Demo Suite Results")
    print("=" * 70)
    for name, ok, nsteps, elapsed, gif in results:
        status = "PASS" if ok else "WARN"
        print(f"  [{status}] {name}")
        print(f"         {nsteps} steps, {elapsed:.1f}s")
        if gif:
            print(f"         GIF: {gif}")
    print("=" * 70)


if __name__ == "__main__":
    main()
