#!/usr/bin/env python3
"""Record a GIF demo of AgenticOS performing a task.

Fully synchronous — avoids asyncio issues on Windows Python 3.13.

Usage:
    python scripts/record_demo.py "Open Notepad and type Hello World" --output demo.gif
    python scripts/record_demo.py "Open Calculator" --model azure/gpt-4o --azure-ad
"""

from __future__ import annotations

import argparse
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
To open an application, prefer open_app with its name."""


def record(task: str, output: str, model: str | None = None,
           max_steps: int = 10, azure_ad: bool = False):
    """Record a demo GIF of an agent performing a task (fully sync)."""
    import litellm
    from agenticos.observation.screenshot import ScreenCapture
    from agenticos.grounding.accessibility import UIAGrounder
    from agenticos.actions.compositor import ActionCompositor, Action, ActionType, ActionResult
    from agenticos.observation.recorder import GifRecorder
    from agenticos.utils.config import AgenticOSConfig, resolve_api_key

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    config = AgenticOSConfig(
        confirm_actions=False,
        auto_record_gif=True,
        max_steps=max_steps,
        azure_ad_auth=azure_ad,
    )
    if model:
        config.llm_model = model

    print("=" * 60)
    print("  🖥️  AgenticOS — Live Demo")
    print("=" * 60)
    print(f"  Task:     {task}")
    print(f"  Model:    {config.llm_model}")
    print(f"  Output:   {output}")
    print(f"  Steps:    max {max_steps}")
    print(f"  Azure AD: {azure_ad}")
    print("=" * 60)
    print()

    # Components
    screen = ScreenCapture(monitor=config.screenshot_monitor, scale=config.screenshot_scale)
    grounder = UIAGrounder()
    compositor = ActionCompositor()

    # Auth
    api_key = resolve_api_key(config)
    azure_ad_token = None
    if azure_ad:
        # Check if token is pre-acquired via env var
        azure_ad_token = os.environ.get("AZURE_AD_TOKEN")
        if not azure_ad_token:
            from azure.identity import DefaultAzureCredential
            print("🔑 Acquiring Azure AD token...", end=" ", flush=True)
            cred = DefaultAzureCredential()
            azure_ad_token = cred.get_token("https://cognitiveservices.azure.com/.default").token
            print("✅")
        else:
            print("🔑 Using pre-acquired Azure AD token ✅")
        print()

    # GIF recorder
    recorder = GifRecorder(fps=config.gif_fps, max_duration=config.gif_max_duration)
    recorder.start()

    steps = []
    success = False
    t_start = time.time()

    for step_num in range(1, max_steps + 1):
        print(f"━━ Step {step_num}/{max_steps} ━━━━━━━━━━━━━━━━━━━━━━━━━━")

        # ── Observe ──
        screenshot = screen.grab()
        b64 = screenshot.to_base64()
        elements = grounder.detect()
        print(f"  👁️  {len(elements)} UI elements | {screenshot.width}×{screenshot.height}")

        elem_text = "\n".join(el.description() for el in elements[:50])
        if len(elements) > 50:
            elem_text += f"\n... ({len(elements) - 50} more)"

        history = ""
        if steps:
            history = "\n\nPrevious steps:\n" + "\n".join(
                f"  {s['step']}. [{s['action_type']}] {s['thought'][:80]}"
                for s in steps
            )

        # ── Think ──
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": [
                {"type": "text", "text": f"Task: {task}\n\nUI Elements:\n{elem_text}{history}\n\nNext action?"},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
            ]},
        ]

        kwargs: dict = {
            "model": config.llm_model,
            "messages": messages,
            "max_tokens": config.llm_max_tokens,
            "temperature": config.llm_temperature,
        }
        if api_key and not azure_ad_token:
            kwargs["api_key"] = api_key
        if config.llm_base_url:
            kwargs["api_base"] = config.llm_base_url
        if config.llm_api_version:
            kwargs["api_version"] = config.llm_api_version
        if azure_ad_token:
            kwargs["azure_ad_token"] = azure_ad_token

        print("  🧠 Thinking...", end=" ", flush=True)
        t0 = time.perf_counter()
        try:
            resp = litellm.completion(**kwargs)
            content = resp.choices[0].message.content
            dt = time.perf_counter() - t0
            print(f"({dt:.1f}s, {resp.usage.total_tokens} tokens)")
        except Exception as e:
            print(f"\n  ❌ LLM error: {e}")
            break

        # ── Parse ──
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
            print(f"  ⚠️  Parse failed: {content[:150]}...")
            continue

        print(f"  💭 {thought}")
        print(f"  ⚡ {action_type}: {params}")

        steps.append({"step": step_num, "thought": thought,
                       "action_type": action_type, "action_params": params})
        recorder.add_annotation(f"Step {step_num}: {action_type}")

        # ── Done? ──
        if action_type == "done":
            success = params.get("success", True)  # Default to True when agent says done
            print(f"\n  {'✅' if success else '❌'} {params.get('summary', 'Task completed')}")
            break

        # ── Act ──
        # Map LLM variations to actual ActionType values
        type_map = {
            "type": "type_text", "key_press": "press_key",
            "key": "press_key", "open": "open_app",
        }
        mapped_type = type_map.get(action_type, action_type)

        try:
            action = Action(type=ActionType(mapped_type), params=params)
            result = compositor.execute(action)
            print(f"  {'✅' if result.success else '⚠️ '} Executed")
        except Exception as e:
            print(f"  ⚠️  Action error: {e}")

        time.sleep(1.0)
        recorder.add_annotation("")
        print()

    elapsed = time.time() - t_start

    # Save GIF
    recorder.stop()
    gif = recorder.save(str(output_path))

    print()
    print("=" * 60)
    status = "✅ SUCCESS" if success else "❌ INCOMPLETE"
    print(f"  {status} — {len(steps)} steps in {elapsed:.1f}s")
    if gif:
        print(f"  🎬 GIF: {gif}")
    print("=" * 60)

    # Cleanup to avoid mss __del__ warnings
    try:
        screen.close()
    except Exception:
        pass


def main():
    parser = argparse.ArgumentParser(description="AgenticOS Demo Recorder")
    parser.add_argument("task", help="Task for the agent to perform")
    parser.add_argument("--output", default="recordings/demo.gif", help="Output GIF path")
    parser.add_argument("--model", default=None, help="LLM model (e.g. azure/gpt-4o)")
    parser.add_argument("--max-steps", type=int, default=10, help="Max steps")
    parser.add_argument("--azure-ad", action="store_true", help="Azure AD token auth")
    args = parser.parse_args()

    record(args.task, args.output, args.model, args.max_steps, args.azure_ad)


if __name__ == "__main__":
    main()
