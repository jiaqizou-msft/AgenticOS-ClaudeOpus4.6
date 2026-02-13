#!/usr/bin/env python3
"""AgenticOS Demo Runner v2 — with state validation, recovery, and memory.

Key improvements over v1:
- Post-action state validation: detects when model prediction ≠ reality
- Undo/go-back recovery: automatically fixes wrong navigation
- Step memory: caches successful patterns to skip LLM calls
- Detailed logging: what model thinks vs what actually happened

Usage:
    python scripts/run_demo_detached.py --demo 1
    python scripts/run_demo_detached.py --demo 2
    python scripts/run_demo_detached.py --demo 3
    python scripts/run_demo_detached.py --demo all
"""

from __future__ import annotations

import json
import os
import re
import signal
import sys
import time
import threading
from pathlib import Path

# Ignore signals so we can't be interrupted
try:
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    signal.signal(signal.SIGBREAK, signal.SIG_IGN)  # type: ignore[attr-defined]
except (AttributeError, OSError):
    pass

# Setup paths
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

# Pre-import everything at module level
import litellm  # noqa: E402
from agenticos.observation.screenshot import ScreenCapture  # noqa: E402
from agenticos.grounding.accessibility import UIAGrounder, UIElement  # noqa: E402
from agenticos.actions.compositor import ActionCompositor, Action, ActionType  # noqa: E402
from agenticos.observation.recorder import GifRecorder  # noqa: E402
from agenticos.agent.state_validator import StateValidator, StateSnapshot  # noqa: E402
from agenticos.agent.recovery import RecoveryManager, RecoveryStrategy  # noqa: E402
from agenticos.agent.step_memory import StepMemory, CachedStep  # noqa: E402
from agenticos.agent.reinforcement import QLearner, RewardSignal, Transition  # noqa: E402
from agenticos.agent.human_teacher import HumanTeacher, TEACHING_TOPICS  # noqa: E402

LOG_FILE = ROOT / "recordings" / "demo_log.txt"
MEMORY_FILE = ROOT / "recordings" / "step_memory.json"
RL_FILE = ROOT / "recordings" / "rl_qtable.json"
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

_log_fh = None


def log(msg: str):
    """Print and write to log file."""
    ts = time.strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    # Use ascii-safe output for redirected stdout (cp1252 can't handle unicode)
    safe_line = line.encode("ascii", errors="replace").decode("ascii")
    print(safe_line, flush=True)
    global _log_fh
    if _log_fh:
        _log_fh.write(line + "\n")
        _log_fh.flush()


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
- drag: {"start_x": int, "start_y": int, "end_x": int, "end_y": int}
- set_slider: {"name": "Brightness", "value": 100}  (value is percentage 0-100)
- shell: {"command": "shell command to run"}
- open_app: {"app_name": "notepad"}
- wait: {"seconds": 1.0}
- done: {"success": true|false, "summary": "what was accomplished"}

CRITICAL RULES:
1. NEVER use "done" until ALL parts of the task are fully completed and verified.
2. Carefully examine the UI element tree. Use the EXACT coordinates from element centers.
3. If clicking doesn't work, try the element by name with shell commands or keyboard.
4. For clicking elements: match the element NAME in the tree, use its CENTER coordinates.
5. After each action, verify the screen changed as expected.
6. If you're stuck (same state 2+ times), try a completely different approach.
7. For typing: first click the target field, wait, then type_text.
8. Prefer keyboard shortcuts over clicking when available.
9. To go back to a previous state: use escape, alt+left, or ctrl+z.
10. When state validation shows DRIFT, acknowledge it and correct your approach.
11. SLIDER INTERACTION: ALWAYS use "set_slider" for any slider control (brightness, volume, etc).
    Example: {"type": "set_slider", "params": {"name": "Brightness", "value": 100}}
    This directly sets the slider value via Windows UI Automation — much more reliable than drag.
    Only fall back to "drag" if set_slider fails.
12. Elements with val="..." show the current value. Use bbox coordinates for precise targeting."""

# Azure OpenAI config
API_BASE = "https://bugtotest-resource.cognitiveservices.azure.com/"
API_VERSION = "2024-12-01-preview"

DEMOS = {
    1: {
        "name": "Demo 1: System Tray - Brightness and Volume",
        "task": (
            "Adjust display brightness and volume using the system tray Quick Settings panel.\n\n"
            "Step 1: Click on the system tray icons area at the very bottom-right corner of the "
            "taskbar. Look for the battery/volume/WiFi icons in the notification area. Click on them "
            "to open the Quick Settings flyout panel.\n\n"
            "Step 2: Use set_slider to set the brightness to 100%. "
            "The action is: {\"type\": \"set_slider\", \"params\": {\"name\": \"Brightness\", \"value\": 100}}\n\n"
            "Step 3: Use set_slider to set the volume to 10%. "
            "The action is: {\"type\": \"set_slider\", \"params\": {\"name\": \"Volume\", \"value\": 10}}\n\n"
            "Step 4: Click anywhere outside the panel (like the desktop center) to close it.\n\n"
            "Step 5: IMMEDIATELY use done with success=true. Do NOT do any more steps after closing "
            "the panel. The task is complete once brightness=100% and volume=10% are set.\n\n"
            "IMPORTANT: Use 'set_slider' for ALL slider adjustments. It directly sets the value "
            "via Windows UI Automation and is much more reliable than drag.\n"
            "IMPORTANT: As soon as you have set both sliders and closed the panel, you MUST call done."
        ),
        "output": "recordings/demo1_settings.gif",
        "max_steps": 15,
    },
    2: {
        "name": "Demo 2: Edge - 4K Video Fullscreen",
        "task": (
            "1. Use open_app to open 'msedge'. "
            "2. Wait 3 seconds for Edge to load. "
            "3. Use hotkey keys=['ctrl','l'] to focus the address bar. "
            "4. Use type_text to type 'youtube.com' then press_key 'enter'. "
            "5. Wait 3 seconds for YouTube to load. "
            "6. Click on the YouTube search bar and type_text '4k landscape video' then press_key 'enter'. "
            "7. Wait 3 seconds for results. Click on the first video thumbnail. "
            "8. Wait 3 seconds for video to start. Press key 'f' to toggle fullscreen. "
            "9. Use wait for 10 seconds. "
            "10. Press_key 'f' to exit fullscreen, then press_key 'k' to pause the video. "
            "11. Done with success=true."
        ),
        "output": "recordings/demo2_edge_video.gif",
        "max_steps": 20,
    },
    3: {
        "name": "Demo 3: Outlook Email and Teams Message",
        "task": (
            "Part A - Email:\n"
            "1. Use open_app to open 'outlook'. Wait 3 seconds.\n"
            "2. Click 'New mail' or 'New message' button. Wait 2 seconds.\n"
            "3. Click the To field and type_text 'jiaqizou@microsoft.com'. Press_key 'tab'.\n"
            "4. Click the Subject field and type_text 'Sent from AgenticOS-Opus4.6'. Press_key 'tab'.\n"
            "5. Click the email body and type_text 'hello'.\n"
            "6. Use hotkey keys=['ctrl','enter'] to send. Wait 2 seconds.\n"
            "Part B - Teams:\n"
            "7. Use open_app to open 'msteams'. Wait 3 seconds.\n"
            "8. Use hotkey keys=['ctrl','e'] to open search.\n"
            "9. Type_text 'Jiaqi Zou' and press_key 'enter'. Wait 2 seconds.\n"
            "10. Click on 'Jiaqi Zou' in the results. Wait 2 seconds.\n"
            "11. Click the message box, type_text 'Hi', and press_key 'enter'.\n"
            "12. Done with success=true."
        ),
        "output": "recordings/demo3_outlook_teams.gif",
        "max_steps": 25,
    },
}


def get_azure_ad_token() -> str:
    """Get Azure AD token, trying env var first."""
    tok = os.environ.get("AZURE_AD_TOKEN", "")
    if tok:
        log("Using AZURE_AD_TOKEN from environment")
        return tok
    log("Acquiring Azure AD token via DefaultAzureCredential...")
    from azure.identity import DefaultAzureCredential
    cred = DefaultAzureCredential()
    tok = cred.get_token("https://cognitiveservices.azure.com/.default").token
    log("Token acquired OK")
    return tok


def detect_with_timeout(grounder: UIAGrounder, timeout: float = 12.0) -> list:
    """Run UIA detection with a timeout."""
    elements: list = []
    done_event = threading.Event()

    def _detect():
        nonlocal elements
        try:
            elements = grounder.detect()
        except Exception as e:
            log(f"    UIA detect error: {e}")
            elements = []
        done_event.set()

    t = threading.Thread(target=_detect, daemon=True)
    t.start()
    if not done_event.wait(timeout=timeout):
        log(f"    UIA timeout ({timeout}s), screenshot only")
    return elements


def parse_llm_response(content: str) -> dict:
    """Robustly parse LLM JSON response, handling multiple formats."""
    # Try markdown code block first
    m = re.search(r'```(?:json)?\s*(\{.*\})\s*```', content, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    # Find balanced JSON with "action"
    brace_depth = 0
    start_idx = None
    for i, ch in enumerate(content):
        if ch == '{':
            if brace_depth == 0:
                start_idx = i
            brace_depth += 1
        elif ch == '}':
            brace_depth -= 1
            if brace_depth == 0 and start_idx is not None:
                candidate = content[start_idx:i + 1]
                try:
                    parsed = json.loads(candidate)
                    if "action" in parsed:
                        return parsed
                except json.JSONDecodeError:
                    pass
                start_idx = None

    # Last resort
    return json.loads(content)


def extract_action(parsed: dict) -> tuple[str, str, dict]:
    """Extract (thought, action_type, params) handling multiple JSON formats."""
    thought = parsed.get("thought", "")
    act = parsed.get("action", {})

    if "type" in act:
        action_type = act["type"]
        params = act.get("params", {})
    else:
        # Format: {"click": {"x": ..., "y": ...}}
        KNOWN_ACTIONS = {
            "click", "double_click", "right_click", "type_text",
            "press_key", "hotkey", "scroll", "shell", "open_app",
            "wait", "done", "drag", "set_slider", "type", "key", "key_press", "open",
        }
        action_type = "done"
        params = {}
        for key in act:
            if key in KNOWN_ACTIONS:
                action_type = key
                params = act[key] if isinstance(act[key], dict) else {}
                break

    # Normalize action type aliases
    TYPE_MAP = {
        "type": "type_text",
        "key_press": "press_key",
        "key": "press_key",
        "open": "open_app",
    }
    action_type = TYPE_MAP.get(action_type, action_type)

    return thought, action_type, params


def execute_action(compositor: ActionCompositor, action_type: str, params: dict) -> tuple[bool, str]:
    """Execute an action and return (success, message)."""
    try:
        action = Action(type=ActionType(action_type), params=params)
        result = compositor.execute(action)
        if result.success:
            return True, "OK"
        else:
            return False, f"WARN: {result.error}"
    except Exception as e:
        return False, f"ERROR: {e}"


def run_demo(demo_cfg: dict, token: str, memory: StepMemory, rl: QLearner) -> tuple[bool, int, float, str | None]:
    """Run a single demo with state validation, recovery, RL, and memory."""
    task = demo_cfg["task"]
    output = demo_cfg["output"]
    max_steps = demo_cfg["max_steps"]
    output_path = ROOT / output

    log(f"  Task: {task[:120]}...")
    log(f"  Output: {output_path}")
    log(f"  Max steps: {max_steps}")

    screen = ScreenCapture(monitor=1, scale=1.0)
    grounder = UIAGrounder()
    compositor = ActionCompositor()
    validator = StateValidator()
    recovery_mgr = RecoveryManager(max_recovery_attempts=3)
    episode_reward = 0.0

    recorder = GifRecorder(fps=5, max_duration=180)
    recorder.start()

    steps: list[dict] = []
    success = False
    t_start = time.time()
    consecutive_no_change = 0

    for step_num in range(1, max_steps + 1):
        log(f"\n  ── Step {step_num}/{max_steps} ──")

        # ── 1. Observe: Screenshot ──
        try:
            screenshot = screen.grab()
            b64 = screenshot.to_base64()
            scr_bytes = screenshot.to_bytes()
        except Exception as e:
            log(f"    Screenshot error: {e}")
            break

        # ── 2. Observe: UIA Elements ──
        elements = detect_with_timeout(grounder, timeout=12.0)
        log(f"    Observed: {len(elements)} UI elements")

        # ── 3. State Snapshot (BEFORE action) ──
        state_before = validator.capture_state(elements, scr_bytes)
        log(f"    State: {state_before.summary()}")

        # ── 4. Build element text for LLM ──
        elem_text = "\n".join(el.description() for el in elements[:60])
        if len(elements) > 60:
            elem_text += f"\n... ({len(elements) - 60} more)"

        # ── 5. History context ──
        history = ""
        if steps:
            recent = steps[-8:]  # Last 8 steps
            history = "\n\nPrevious steps:\n" + "\n".join(
                f"  {s['step']}. [{s['action_type']}] {s.get('thought', '')[:60]} → {s.get('validation', 'n/a')}"
                for s in recent
            )

        # ── 6. Check memory cache ──
        elem_names = [getattr(el, 'name', '') for el in elements]
        # NOTE: Memory lookup disabled — caching with full task intent is too broad.
        # The memory key should be per sub-goal, not the full task string. Until this is
        # rearchitected (use LLM thought as intent), skip memory lookup to prevent
        # replaying stale/incorrect actions.
        cached_ep = None
        if False:  # Memory lookup disabled for now
            cached_ep = memory.lookup(
                window_title=state_before.window_title,
                element_names=elem_names,
                intent=task[:100],
            )
        if cached_ep and cached_ep.steps:
            cached = cached_ep.steps[0]
            log(f"    MEMORY HIT: {cached.action_type} {cached.action_params} (used {cached_ep.use_count}x)")
            thought = f"[cached] {cached.thought}"
            action_type = cached.action_type
            params = cached.action_params
        else:
            # ── 7. LLM Call ──
            # Add state validation feedback if there was drift
            validation_feedback = ""
            if steps and steps[-1].get("drift"):
                validation_feedback = (
                    f"\n\n⚠ STATE VALIDATION: The last action did NOT produce the expected result. "
                    f"What happened: {steps[-1].get('validation', 'unknown')}. "
                    f"Current window: '{state_before.window_title}'. "
                    f"Try a different approach."
                )

            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": [
                    {"type": "text", "text": (
                        f"Task: {task}\n\n"
                        f"Current window: {state_before.window_title}\n"
                        f"UI Elements:\n{elem_text}"
                        f"{history}"
                        f"{validation_feedback}\n\n"
                        f"What is the next action?"
                    )},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                ]},
            ]

            log("    Calling LLM...")
            t0 = time.perf_counter()
            try:
                resp = litellm.completion(
                    model="azure/gpt-4o",
                    messages=messages,
                    max_tokens=4096,
                    temperature=0.1,
                    azure_ad_token=token,
                    api_base=API_BASE,
                    api_version=API_VERSION,
                )
                content = resp.choices[0].message.content
                dt = time.perf_counter() - t0
                log(f"    LLM: {dt:.1f}s, {resp.usage.total_tokens} tok")
            except Exception as e:
                log(f"    LLM error: {e}")
                break

            # ── 8. Parse ──
            try:
                parsed = parse_llm_response(content)
                thought, action_type, params = extract_action(parsed)
            except Exception:
                log(f"    Parse fail: {content[:200]}")
                continue

        log(f"    Think: {thought[:120]}")
        log(f"    Act:   {action_type}: {params}")

        # ── 8b. RL confidence check ──
        rl_state_key = rl.make_state_key(state_before.window_title, elem_names)
        warn, warn_msg = rl.should_warn(rl_state_key, action_type)
        if warn:
            log(f"    {warn_msg}")

        # ── 9. Premature done guard ──
        if action_type == "done":
            if step_num < 4:
                log(f"    REJECTED premature done at step {step_num}")
                continue
            success = params.get("success", True)
            log(f"    ✓ DONE: {'SUCCESS' if success else 'FAILED'}: {params.get('summary', '')}")
            steps.append({"step": step_num, "thought": thought, "action_type": "done",
                          "action_params": params, "validation": "done"})
            break

        # ── 10. Execute action ──
        try:
            recorder.add_annotation(f"Step {step_num}: {action_type}")
        except Exception:
            pass

        exec_ok, exec_msg = execute_action(compositor, action_type, params)
        log(f"    Exec: {exec_msg}")

        time.sleep(1.0)

        # ── 11. Post-action state validation ──
        try:
            post_screenshot = screen.grab()
            post_bytes = post_screenshot.to_bytes()
        except Exception:
            post_bytes = scr_bytes  # fallback

        post_elements = detect_with_timeout(grounder, timeout=8.0)
        state_after = validator.capture_state(post_elements, post_bytes)

        validation = validator.validate_transition(
            before=state_before,
            after=state_after,
            action_type=action_type,
            action_params=params,
            expected_outcome=thought,
        )

        log(f"    Validate: {validation.summary()}")
        log(f"    State now: {state_after.summary()}")

        drift = validation.drift_detected
        step_record = {
            "step": step_num,
            "thought": thought,
            "action_type": action_type,
            "action_params": params,
            "validation": validation.summary(),
            "drift": drift,
            "window_before": state_before.window_title,
            "window_after": state_after.window_title,
        }
        steps.append(step_record)

        # ── 12. Recovery if needed ──
        if validation.recovery_needed and not recovery_mgr.should_abort():
            recovery_actions = recovery_mgr.get_recovery_actions(
                window_title=state_after.window_title,
                hint=validation.recovery_hint,
            )
            if recovery_actions:
                ra = recovery_actions[0]
                log(f"    🔄 RECOVERY: {ra.description}")
                recovery_mgr.record_attempt(ra.strategy)
                exec_ok2, exec_msg2 = execute_action(compositor, ra.action_type, ra.action_params)
                log(f"    Recovery exec: {exec_msg2}")
                time.sleep(ra.delay_after)

        # ── 13. Track no-change loops ──
        # Only count click actions as "no-change" — drags/sliders/typing may change
        # subtle state that our snapshot doesn't capture
        if not validation.state_changed and action_type == "click":
            consecutive_no_change += 1
            if consecutive_no_change >= 3:
                log(f"    ⚠ {consecutive_no_change} consecutive no-change clicks — forcing different approach")
                consecutive_no_change = 0
        elif validation.state_changed:
            consecutive_no_change = 0

        # ── 14. Update memory ──
        # Only store when action succeeded, no drift, AND state actually changed
        if exec_ok and not drift and validation.state_changed:
            memory.store_single_step(
                window_title=state_before.window_title,
                element_names=elem_names,
                intent=thought[:120],  # Use sub-goal, not full task
                action_type=action_type,
                action_params=params,
                thought=thought,
                success=True,
            )

        # ── 15. RL reward update ──
        reward = RewardSignal.compute(
            action_type=action_type,
            exec_success=exec_ok,
            state_changed=validation.state_changed,
            drift_detected=drift,
            recovery_needed=validation.recovery_needed,
        )
        rl_state_after = rl.make_state_key(state_after.window_title,
            [getattr(el, 'name', '') for el in post_elements])
        rl.update(Transition(
            state_key=rl_state_key,
            action_type=action_type,
            action_key=f"{action_type}:{json.dumps(params, sort_keys=True)[:50]}",
            reward=reward,
            next_state_key=rl_state_after,
            timestamp=time.time(),
        ))
        episode_reward += reward
        confidence = rl.get_action_confidence(rl_state_key, action_type)
        log(f"    RL: reward={reward:+.2f} cumul={episode_reward:+.1f} conf={confidence:.0%}")

        try:
            recorder.add_annotation("")
        except Exception:
            pass

    elapsed = time.time() - t_start

    # Save GIF
    recorder.stop()
    gif_path = None
    try:
        gif_path = recorder.save(str(output_path))
        log(f"  GIF saved: {gif_path}")
    except Exception as e:
        log(f"  GIF save error: {e}")

    status = "SUCCESS" if success else "INCOMPLETE"
    log(f"  Result: {status} -- {len(steps)} steps in {elapsed:.1f}s")
    log(f"  Memory: {memory.stats}")

    # RL end-of-episode
    done_reward = RewardSignal.compute(
        action_type="done", exec_success=True,
        state_changed=False, drift_detected=False,
        recovery_needed=False, task_done=True, task_success=success,
    )
    episode_reward += done_reward
    rl.end_episode(episode_reward)
    log(f"  RL episode: total_reward={episode_reward:+.1f} | {rl.stats}")
    trend = rl.get_improvement_trend()
    if trend != "insufficient_data":
        log(f"  RL trend: {trend}")

    try:
        screen.close()
    except Exception:
        pass

    return success, len(steps), elapsed, gif_path


def main():
    global _log_fh

    import argparse
    parser = argparse.ArgumentParser(description="AgenticOS Demo Runner v2")
    parser.add_argument("--demo", default="all", help="Demo number (1,2,3) or 'all'")
    args = parser.parse_args()

    _log_fh = open(LOG_FILE, "w", encoding="utf-8")

    log("=" * 64)
    log("  AgenticOS Demo Runner v4")
    log("  State Validation | Recovery | RL | Step Memory | UIA Sliders")
    log("=" * 64)

    token = get_azure_ad_token()
    memory = StepMemory(persist_path=str(MEMORY_FILE))
    rl = QLearner(persist_path=str(RL_FILE))
    teacher = HumanTeacher(persist_dir=str(ROOT / "recordings" / "teaching"))
    log(f"  Memory loaded: {memory.size} episodes")
    log(f"  RL loaded: {rl.stats}")
    log(f"  Teaching: {teacher.get_stats()}")

    if args.demo == "all":
        demo_nums = [1, 2, 3]
    else:
        demo_nums = [int(x.strip()) for x in args.demo.split(",")]

    results = []
    for i, num in enumerate(demo_nums):
        demo = DEMOS[num]
        log("")
        log("=" * 64)
        log(f"  [{i + 1}/{len(demo_nums)}] {demo['name']}")
        log("=" * 64)

        ok, nsteps, elapsed, gif = run_demo(demo, token, memory, rl)
        results.append((demo["name"], ok, nsteps, elapsed, gif))

        if i < len(demo_nums) - 1:
            log("\n  Waiting 5s before next demo...\n")
            time.sleep(5)

    log("")
    log("=" * 64)
    log("  RESULTS SUMMARY")
    log("=" * 64)
    for name, ok, nsteps, elapsed, gif in results:
        status = "PASS" if ok else "WARN"
        log(f"  [{status}] {name} -- {nsteps} steps, {elapsed:.1f}s")
        if gif:
            log(f"           GIF: {gif}")
    log(f"  Memory final: {memory.stats}")
    log(f"  RL final: {rl.stats}")

    # ── Teaching suggestions ──
    suggestions = teacher.get_suggested_topics(max_topics=3)
    if suggestions:
        log("")
        log("=" * 64)
        log("  TEACHING REQUEST: I'd like you to demonstrate these tasks for me")
        log("=" * 64)
        for s in suggestions:
            log(f"  [{s['id']}] {s['topic']}")
            log(f"    {s['description'][:120]}...")
        log("")
        log("  To teach me, run: python scripts/human_teach.py --topic <topic_id>")

    log("=" * 64)
    log("  ALL DONE")

    _log_fh.close()


if __name__ == "__main__":
    main()
