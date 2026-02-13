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
12. Elements with val="..." show the current value. Use bbox coordinates for precise targeting.
13. CONTENT VERIFICATION: After clicking on search results or videos, ALWAYS check the window title
    and visible content to verify you selected the RIGHT item. If the title does not match what you
    searched for (e.g. you searched '4k landscape video' but the video title is about something else),
    go BACK and select a different result. Never proceed with wrong content.
14. VIDEO CONTROLS: On YouTube, 'k' toggles play/pause, 'f' toggles fullscreen. After pressing 'k',
    verify the video is actually paused by checking if a play button is visible.
15. EMAIL COMPOSE: In Outlook, use Tab to move between To, Subject, and Body fields. After typing in
    To field, press Tab to move to Subject. After Subject, press Tab again to reach the Body.
    Use Ctrl+Enter to send the email."""

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
        "pre_launch": 'start msedge --inprivate "https://www.youtube.com/results?search_query=4k+landscape+nature+video"',
        "task": (
            "Play a 4K landscape nature video on YouTube in Edge, go fullscreen, then pause it.\n"
            "Edge is already open with YouTube search results for '4k landscape nature video'.\n\n"
            "Step 1: wait 3 seconds for results to fully load. If you see a consent/cookie dialog,\n"
            "        click 'Reject all' or 'Accept all' to dismiss it.\n"
            "Step 2: Look at the YouTube search results on screen. You need to click on a video\n"
            "        thumbnail. The thumbnails are the large images on the LEFT side of each result.\n"
            "        Look at the SCREENSHOT carefully to find a thumbnail image that shows nature,\n"
            "        landscapes, mountains, or forests. Click on the FIRST visible video thumbnail\n"
            "        (the large image area, not the title text). The thumbnail is usually around\n"
            "        x=500-700, y=300-500 area for the first result.\n"
            "Step 3: wait 3 seconds for the video to start playing.\n"
            "Step 4: VERIFY: Check the window title — it should mention landscape, nature, 4K,\n"
            "        scenic, etc. If wrong, hotkey ['alt','left'] to go back and try a different video.\n"
            "Step 5: press_key 'f' to enter fullscreen.\n"
            "Step 6: wait 10 seconds.\n"
            "Step 7: press_key 'f' to exit fullscreen.\n"
            "Step 8: press_key 'k' to PAUSE the video.\n"
            "Step 9: wait 1 second.\n"
            "Step 10: done with success=true.\n\n"
            "CRITICAL: Click on a video THUMBNAIL (the large preview image), not on text links.\n"
            "If clicking at one position doesn't work, try scrolling down a bit and clicking\n"
            "a different thumbnail. Use Tab key to navigate between results if clicking fails."
        ),
        "output": "recordings/demo2_edge_video.gif",
        "max_steps": 25,
    },
    3: {
        "name": "Demo 3: Outlook Email and Teams Message",
        "pre_launch": "start outlook",
        "task": (
            "Send an email in Outlook and a message in Teams.\n\n"
            "===== PART A: Send Email in Outlook =====\n"
            "Step 1: The Outlook app should already be open. Click on it in the taskbar or use\n"
            "        open_app 'outlook'. Wait 3 seconds.\n"
            "Step 2: Use hotkey ['ctrl','n'] to create a new email. Wait 2 seconds.\n"
            "Step 3: The cursor should be in the To field. type_text 'jiaqizou@microsoft.com'.\n"
            "Step 4: Press Tab ONCE to move past To field. Then check: if you see a CC/BCC area,\n"
            "        press Tab again to skip it.\n"
            "Step 5: Now type the Subject: type_text 'Sent from AgenticOS-Opus4.6'.\n"
            "Step 6: Press Tab ONCE to move from Subject to Body.\n"
            "Step 7: type_text 'Hello from AgenticOS! This email was composed and sent by an AI agent.'.\n"
            "Step 8: VERIFY the email by looking at the screenshot:\n"
            "        - Is the To field filled with jiaqizou@microsoft.com?\n"
            "        - Is the Subject filled with 'Sent from AgenticOS-Opus4.6'?\n"
            "        - Is the Body filled with 'Hello from AgenticOS...'?\n"
            "        If any field is EMPTY, do NOT send. Instead click on that field and fix it.\n"
            "Step 9: hotkey ['ctrl','enter'] to SEND the email. Wait 2 seconds.\n"
            "Step 10: The compose window should close (email sent).\n\n"
            "===== PART B: Send Teams Message =====\n"
            "Step 11: open_app 'msteams'. Wait 4 seconds.\n"
            "Step 12: hotkey ['ctrl','e'] to open search. Wait 1 second.\n"
            "Step 13: type_text 'Jiaqi Zou' then press_key 'enter'. Wait 2 seconds.\n"
            "Step 14: Click on the contact 'Jiaqi Zou' in search results. Wait 2 seconds.\n"
            "Step 15: The chat message box should be at the bottom. Click on it.\n"
            "Step 16: type_text 'Hi from AgenticOS!' then press_key 'enter'.\n"
            "Step 17: done with success=true.\n\n"
            "CRITICAL RULES:\n"
            "- IMPORTANT: If a 'Discard' dialog appears, click 'No' or 'Don't save' or 'Cancel'\n"
            "  to dismiss it without discarding the draft. Then start over with Ctrl+N.\n"
            "- Use Ctrl+N for new email, Tab to navigate fields, Ctrl+Enter to send.\n"
            "- VERIFY all fields are filled BEFORE sending — look at the screenshot.\n"
            "- Do NOT call done until BOTH the email AND the Teams message are sent."
        ),
        "output": "recordings/demo3_outlook_teams.gif",
        "max_steps": 30,
    },
    4: {
        "name": "Demo 4: File Explorer - Create Folder in Downloads",
        "pre_launch": "start explorer %USERPROFILE%\\Downloads",
        "min_done_step": 7,
        "done_verify_path": "~/Downloads/TestFromAgenticOS",
        "task": (
            "Create a new folder called 'TestFromAgenticOS' in the Downloads folder using File Explorer.\n"
            "File Explorer is already open showing the Downloads folder.\n\n"
            "YOU MUST FOLLOW EVERY STEP IN ORDER. Do NOT skip steps or call done early.\n\n"
            "Step 1: wait 3 seconds for File Explorer to fully load.\n"
            "Step 2: Click on an empty area in the FILE LIST (the main white area on the right side)\n"
            "        to make sure File Explorer has keyboard focus. Click around x=800, y=500.\n"
            "Step 3: hotkey ['ctrl','shift','n'] to create a new folder.\n"
            "        A new folder named 'New folder' should appear with its name selected for editing.\n"
            "        If nothing happens, try right_click at x=800, y=500 then click 'New' then 'Folder'.\n"
            "Step 4: wait 1 second for the new folder name to be editable.\n"
            "Step 5: type_text 'TestFromAgenticOS' — this replaces the default 'New folder' name.\n"
            "Step 6: press_key 'enter' to CONFIRM the folder name. This is CRITICAL — without Enter\n"
            "        the folder name is not saved.\n"
            "Step 7: wait 2 seconds. Look at the UI elements — you should now see a ListItem or\n"
            "        element named 'TestFromAgenticOS' in the file list. If not, the folder was\n"
            "        NOT created — go back to Step 2 and try again.\n"
            "Step 8: hotkey ['alt','f4'] to close File Explorer.\n"
            "Step 9: done with success=true, summary='Created TestFromAgenticOS folder in Downloads'.\n\n"
            "CRITICAL RULES:\n"
            "- Do NOT press Alt+F4 before pressing Enter to confirm the folder name!\n"
            "- Do NOT call done until you see 'TestFromAgenticOS' in the element list.\n"
            "- After Ctrl+Shift+N, the cursor is already in the name field — just type immediately.\n"
            "- The system will verify the folder exists on disk before accepting done."
        ),
        "output": "recordings/demo4_file_explorer.gif",
        "max_steps": 15,
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

    # Minimize all windows before starting to give a clean desktop
    try:
        import pyautogui
        pyautogui.hotkey('win', 'd')  # Show desktop
        time.sleep(1.0)
    except Exception:
        pass

    # Pre-launch apps for demos that need them (saves LLM steps on window management)
    pre_launch = demo_cfg.get("pre_launch")
    if pre_launch:
        log(f"  Pre-launching: {pre_launch}")
        try:
            import subprocess
            subprocess.Popen(pre_launch, shell=True)
            time.sleep(4.0)  # Wait for app to open
        except Exception as e:
            log(f"  Pre-launch error: {e}")

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
        elem_text = "\n".join(el.description() for el in elements[:100])
        if len(elements) > 100:
            elem_text += f"\n... ({len(elements) - 100} more)"

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

            # ── Inject learned teaching patterns ──
            teaching_hint = ""
            try:
                teacher = HumanTeacher(persist_dir=str(ROOT / "recordings" / "teaching"))
                for topic, pattern in teacher._patterns.items():
                    if pattern.action_sequence and pattern.success_rate > 0:
                        teaching_hint += f"\n\nLEARNED FROM HUMAN DEMO ({topic}):\n"
                        for act in pattern.action_sequence:
                            teaching_hint += f"  - {act.get('type', 'action')}: {act}\n"
                        teaching_hint += f"  (demonstrated {pattern.source_demos}x, success rate {pattern.success_rate:.0%})\n"
            except Exception:
                pass

            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": [
                    {"type": "text", "text": (
                        f"Task: {task}\n\n"
                        f"Current window: {state_before.window_title}\n"
                        f"UI Elements:\n{elem_text}"
                        f"{history}"
                        f"{validation_feedback}"
                        f"{teaching_hint}\n\n"
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
            min_done = demo_cfg.get("min_done_step", 4)
            if step_num < min_done:
                log(f"    REJECTED premature done at step {step_num} (need step >= {min_done})")
                continue

            # Filesystem verification (e.g. check folder was actually created)
            verify_path = demo_cfg.get("done_verify_path")
            if verify_path:
                expanded = os.path.expanduser(verify_path)
                if not os.path.exists(expanded):
                    log(f"    REJECTED done: verification path does not exist: {expanded}")
                    log(f"    The task is NOT complete. Continue working.")
                    continue
                else:
                    log(f"    ✓ Verified: {expanded} exists")

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
