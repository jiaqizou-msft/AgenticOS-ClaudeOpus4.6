#!/usr/bin/env python3
"""AgenticOS Skill Runner v1 — Execute skills with amortized replay.

This is the new entry point that replaces demo-lookup with composable skills.
It accepts natural language intents or explicit skill sequences, and uses
the skill cache for amortized replay (no LLM on cache hit).

Usage:
    # Natural language intent (auto-decomposes into skills)
    python scripts/run_skill.py --intent "Turn brightness to 100%"

    # Explicit skill sequence
    python scripts/run_skill.py --skills open_quick_settings,set_slider:name:Brightness:value:100,close_panel

    # Plan only (preview, don't execute)
    python scripts/run_skill.py --intent "Set volume to 50%" --plan-only

    # Force fresh execution (skip cache)
    python scripts/run_skill.py --intent "Turn brightness to 100%" --no-cache

    # Show action log
    python scripts/run_skill.py --show-log

    # List all available skills
    python scripts/run_skill.py --list-skills

    # List all recipes
    python scripts/run_skill.py --list-recipes
"""

from __future__ import annotations

import json
import os
import signal
import sys
import time
import threading
from pathlib import Path
from dataclasses import dataclass

# Ignore signals for stability
try:
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    signal.signal(signal.SIGBREAK, signal.SIG_IGN)  # type: ignore[attr-defined]
except (AttributeError, OSError):
    pass

# Setup paths
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

# Imports
import litellm  # noqa: E402
from agenticos.observation.screenshot import ScreenCapture  # noqa: E402
from agenticos.grounding.accessibility import UIAGrounder  # noqa: E402
from agenticos.actions.compositor import ActionCompositor, Action, ActionType  # noqa: E402
from agenticos.observation.recorder import GifRecorder  # noqa: E402
from agenticos.agent.state_validator import StateValidator  # noqa: E402

from skill_library import SKILLS, RECIPES, Skill, get_skill_catalog  # noqa: E402
from skill_cache import SkillCache, CachedAction, UIFingerprint, CacheEntry  # noqa: E402
from skill_composer import SkillComposer, SkillPlan, SkillStep  # noqa: E402
from action_logger import ActionLogger, ActionLogEntry  # noqa: E402

# ── Paths ──
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
CACHE_FILE = DATA_DIR / "skill_cache.json"
LOG_FILE = DATA_DIR / "action_log.jsonl"

# Azure config
API_BASE = "https://bugtotest-resource.cognitiveservices.azure.com/"
API_VERSION = "2024-12-01-preview"

SKILL_SYSTEM_PROMPT = """You are AgenticOS, an AI agent that controls a Windows desktop.
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
- type_text: {"text": "text to type"}
- press_key: {"key": "key name like enter, tab, escape"}
- hotkey: {"keys": ["ctrl", "s"]}
- scroll: {"x": int, "y": int, "clicks": -3}
- set_slider: {"name": "Brightness", "value": 100}
- shell: {"command": "shell command to run"}
- open_app: {"app_name": "notepad"}
- wait: {"seconds": 1.0}
- done: {"success": true|false, "summary": "what was accomplished"}

CRITICAL RULES:
1. Complete ONLY the specific skill task described. Do NOT do more.
2. Use coordinates from the UI element tree when available.
   For Electron apps (Teams, VS Code, Slack, etc.) the element tree may NOT expose all interactive content.
   In that case, look at the SCREENSHOT carefully to find the target visually and estimate click coordinates from what you see.
3. Use "set_slider" for ALL slider controls — much more reliable than drag.
4. Call done ONLY when the FULL task objective is achieved. Read the TASK carefully.
5. If stuck, try a different approach (keyboard shortcut, etc).
6. Simple skills (press key, set slider) need 1-2 actions. Complex skills (search + navigate + interact) may need many more. Do NOT say done prematurely."""


def ts() -> str:
    return time.strftime("%H:%M:%S")


def log(msg: str):
    safe = msg.encode("ascii", errors="replace").decode("ascii")
    print(f"[{ts()}] {safe}", flush=True)


def get_token() -> str:
    """Get Azure AD token."""
    tok = os.environ.get("AZURE_AD_TOKEN", "")
    if tok:
        return tok
    api_key = os.environ.get("AZURE_API_KEY", "")
    if api_key:
        return api_key
    from azure.identity import DefaultAzureCredential
    cred = DefaultAzureCredential()
    return cred.get_token("https://cognitiveservices.azure.com/.default").token


def detect_with_timeout(grounder: UIAGrounder, timeout: float = 8.0) -> list:
    """Run UIA detection with a timeout."""
    elements: list = []
    done_event = threading.Event()

    def _detect():
        nonlocal elements
        try:
            elements = grounder.detect()
        except Exception:
            elements = []
        done_event.set()

    t = threading.Thread(target=_detect, daemon=True)
    t.start()
    done_event.wait(timeout=timeout)
    return elements


def execute_action(compositor: ActionCompositor, action_type: str, params: dict) -> tuple[bool, str]:
    """Execute an action and return (success, message)."""
    try:
        action = Action(type=ActionType(action_type), params=params)
        result = compositor.execute(action)
        return (True, "OK") if result.success else (False, f"WARN: {result.error}")
    except Exception as e:
        return False, f"ERROR: {e}"


def parse_llm_response(content: str) -> dict:
    """Parse LLM JSON response."""
    import re
    m = re.search(r'```(?:json)?\s*(\{.*\})\s*```', content, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

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
    return json.loads(content)


def run_skill_step(
    skill: Skill,
    params: dict,
    token: str,
    cache: SkillCache,
    action_logger: ActionLogger,
    compositor: ActionCompositor,
    screen: ScreenCapture,
    grounder: UIAGrounder,
    validator: StateValidator,
    no_cache: bool = False,
    recorder: GifRecorder | None = None,
) -> tuple[bool, list[CachedAction], float, int]:
    """Execute a single skill step, using cache if available.
    
    Returns: (success, actions_taken, elapsed_time, tokens_used)
    """
    t_start = time.time()
    tokens_used = 0

    # ── 0. Pre-launch command (if any) ──
    if skill.pre_launch:
        try:
            cmd = skill.pre_launch.format(**params)
            log(f"    Pre-launch: {cmd}")
            import subprocess
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=60
            )
            if result.stdout.strip():
                for line in result.stdout.strip().splitlines():
                    log(f"    Pre-launch: {line}")
            if result.returncode != 0:
                log(f"    Pre-launch FAILED (exit {result.returncode})")
                if result.stderr.strip():
                    log(f"    Pre-launch stderr: {result.stderr.strip()[:200]}")
            time.sleep(4.0)  # Extra settle time after pre-launch
        except subprocess.TimeoutExpired:
            log(f"    Pre-launch TIMEOUT (60s)")
        except Exception as e:
            log(f"    Pre-launch error: {e}")

    # ── 1. Observe current state ──
    screenshot = screen.grab()
    b64 = screenshot.to_base64()
    elements = detect_with_timeout(grounder)
    
    # Build fingerprint
    window_title = ""
    if elements:
        # Try to get window title from elements
        for el in elements:
            name = getattr(el, 'name', '')
            ctrl = getattr(el, 'control_type', '')
            if ctrl == 'Window' and name:
                window_title = name
                break
    if not window_title:
        state = validator.capture_state(elements, screenshot.to_bytes())
        window_title = state.window_title

    fingerprint = UIFingerprint.from_state(window_title, elements)
    log(f"    State: '{window_title}' | {len(elements)} elements")

    # ── 2. Check cache ──
    if not no_cache:
        cached = cache.lookup(skill.id, params, fingerprint)
        if cached:
            log(f"    CACHE HIT: {cached.skill_id} — replaying {len(cached.actions)} cached actions")
            actions = cached.actions
            all_ok = True
            for i, ca in enumerate(actions):
                if ca.action_type == "done":
                    log(f"    [cached {i+1}/{len(actions)}] done")
                    continue
                log(f"    [cached {i+1}/{len(actions)}] {ca.action_type}: {ca.params}")
                ok, msg = execute_action(compositor, ca.action_type, ca.params)
                if not ok:
                    log(f"    Cache replay FAILED at step {i+1}: {msg}")
                    all_ok = False
                    # Invalidate cache and re-run with LLM
                    cache.invalidate(skill.id, params)
                    log(f"    Cache invalidated — falling through to LLM execution")
                    break
                time.sleep(0.5)

                if recorder:
                    try:
                        recorder.add_annotation(f"[cached] {ca.action_type}")
                    except Exception:
                        pass

            if all_ok:
                elapsed = time.time() - t_start
                action_logger.log(ActionLogEntry(
                    skill_id=skill.id, params=params, actions=actions,
                    cached=True, success=True, duration=elapsed,
                    pre_fingerprint=fingerprint.to_dict(),
                ))
                return True, actions, elapsed, 0

    # ── 3. LLM-guided execution ──
    log(f"    LLM execution: {skill.name}")
    prompt = skill.format_prompt(**params)

    actions_taken: list[CachedAction] = []
    success = False

    for step_num in range(1, skill.max_steps + 2):  # +1 for done step
        elapsed_so_far = time.time() - t_start
        if elapsed_so_far > skill.timeout:
            log(f"    TIMEOUT after {elapsed_so_far:.1f}s")
            break

        # Re-observe for multi-step skills
        if step_num > 1:
            screenshot = screen.grab()
            b64 = screenshot.to_base64()
            elements = detect_with_timeout(grounder)

        elem_text = "\n".join(
            getattr(el, 'description', lambda: str(el))()
            if callable(getattr(el, 'description', None)) else str(el)
            for el in elements[:120]
        )

        # Build history
        history = ""
        if actions_taken:
            history = "\nPrevious actions in this skill:\n" + "\n".join(
                f"  {a.step_index}. {a.action_type}: {a.params}" for a in actions_taken
            )

        messages = [
            {"role": "system", "content": SKILL_SYSTEM_PROMPT},
            {"role": "user", "content": [
                {"type": "text", "text": (
                    f"SKILL: {skill.name}\n"
                    f"TASK: {prompt}\n\n"
                    f"Current window: {window_title}\n"
                    f"UI Elements:\n{elem_text}"
                    f"{history}\n\n"
                    f"What is the next action? Complete this skill in minimum steps."
                )},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
            ]},
        ]

        log(f"    Calling LLM (step {step_num}/{skill.max_steps})...")
        t0 = time.perf_counter()
        try:
            resp = litellm.completion(
                model="azure/gpt-4o",
                messages=messages,
                max_tokens=400,
                temperature=0.1,
                azure_ad_token=token,
                api_base=API_BASE,
                api_version=API_VERSION,
            )
            content = resp.choices[0].message.content
            dt = time.perf_counter() - t0
            tokens_used += resp.usage.total_tokens
            log(f"    LLM: {dt:.1f}s, {resp.usage.total_tokens} tok")
        except Exception as e:
            log(f"    LLM error: {e}")
            break

        # Parse response
        try:
            parsed = parse_llm_response(content)
            thought = parsed.get("thought", "")
            act = parsed.get("action", {})
            action_type = act.get("type", "done")
            action_params = act.get("params", {})
        except Exception:
            log(f"    Parse fail: {content[:200]}")
            continue

        log(f"    Think: {thought[:100]}")
        log(f"    Act:   {action_type}: {action_params}")

        cached_action = CachedAction(
            action_type=action_type,
            params=action_params,
            thought=thought[:120],
            step_index=step_num,
            exec_time=time.time(),
        )

        if action_type == "done":
            # Count non-done, non-wait actions taken so far
            real_actions = sum(1 for a in actions_taken if a.action_type not in ("done", "wait", "nudge"))
            if real_actions < skill.min_steps:
                log(f"    REJECTED DONE: only {real_actions}/{skill.min_steps} real actions completed. Nudging LLM to continue.")
                # Record a nudge so the LLM sees it was rejected
                nudge = CachedAction(
                    action_type="nudge",
                    params={"message": f"Done rejected: only {real_actions}/{skill.min_steps} steps completed. The task is NOT finished. Continue with the next step."},
                    thought="System: premature done rejected",
                    step_index=step_num,
                    exec_time=time.time(),
                )
                actions_taken.append(nudge)
                continue
            success = action_params.get("success", True)
            actions_taken.append(cached_action)
            log(f"    DONE: {'SUCCESS' if success else 'FAILED'}")
            break

        # Execute
        ok, msg = execute_action(compositor, action_type, action_params)
        log(f"    Exec: {msg}")
        actions_taken.append(cached_action)

        if recorder:
            try:
                recorder.add_annotation(f"Step {step_num}: {action_type}")
            except Exception:
                pass

        # Auto-succeed for single-step skills that execute OK
        # (no need to waste an LLM call just to say "done")
        if ok and skill.max_steps == 1:
            success = True
            log(f"    Auto-done: single-step skill completed successfully")
            break

        time.sleep(0.5)

        # Update window title for context
        new_elements = detect_with_timeout(grounder, timeout=4.0)
        for el in new_elements:
            name = getattr(el, 'name', '')
            ctrl = getattr(el, 'control_type', '')
            if ctrl == 'Window' and name:
                window_title = name
                break

    # If we used all steps and the last action succeeded, consider it a success
    if not success and actions_taken and actions_taken[-1].action_type != "done":
        # Check if any non-done action executed (implicit success for low-step skills)
        if skill.max_steps <= 2 and any(
            a.action_type not in ("done",) for a in actions_taken
        ):
            success = True
            log(f"    Auto-done: skill completed (all actions executed)")

    elapsed = time.time() - t_start

    # ── 4. Cache successful execution ──
    if success and actions_taken and not no_cache:
        post_fingerprint = UIFingerprint.from_state(window_title, elements)
        cache.store(
            skill_id=skill.id,
            params=params,
            actions=actions_taken,
            pre_fingerprint=fingerprint,
            post_fingerprint=post_fingerprint,
            success=True,
            total_time=elapsed,
            llm_tokens=tokens_used,
        )
        log(f"    Cached for future replay ({len(actions_taken)} actions, ~{tokens_used} tokens)")

    # ── 5. Log ──
    post_fp = UIFingerprint.from_state(window_title, elements)
    action_logger.log(ActionLogEntry(
        skill_id=skill.id,
        params=params,
        actions=actions_taken,
        cached=False,
        success=success,
        duration=elapsed,
        tokens_used=tokens_used,
        pre_fingerprint=fingerprint.to_dict(),
        post_fingerprint=post_fp.to_dict(),
    ))

    return success, actions_taken, elapsed, tokens_used


def run_plan(
    plan: SkillPlan,
    token: str,
    cache: SkillCache,
    action_logger: ActionLogger,
    no_cache: bool = False,
    record_gif: bool = True,
) -> tuple[bool, int, float, int, str | None]:
    """Execute a full skill plan.
    
    Returns: (all_success, total_steps, total_time, total_tokens, gif_path)
    """
    log("=" * 64)
    log(f"  AgenticOS Skill Runner v1")
    log(f"  Intent: {plan.intent}")
    log(f"  Plan: {plan.summary()}")
    log(f"  Source: {plan.source} (confidence={plan.confidence:.0%})")
    log(f"  Cache: {cache.summary()}")
    log("=" * 64)

    screen = ScreenCapture(monitor=1, scale=1.0)
    grounder = UIAGrounder()
    compositor = ActionCompositor()
    validator = StateValidator()

    recorder = None
    gif_path = None
    if record_gif:
        recorder = GifRecorder(fps=5, max_duration=120)
        recorder.start()

    total_steps = 0
    total_time = 0.0
    total_tokens = 0
    all_success = True

    for i, step in enumerate(plan.steps):
        skill = SKILLS.get(step.skill_id)
        if not skill:
            log(f"\n  [{i+1}/{len(plan.steps)}] SKIP: Unknown skill '{step.skill_id}'")
            continue

        log(f"\n  [{i+1}/{len(plan.steps)}] {skill.name}")
        log(f"    Params: {step.params}")

        success, actions, elapsed, tokens = run_skill_step(
            skill=skill,
            params=step.params,
            token=token,
            cache=cache,
            action_logger=action_logger,
            compositor=compositor,
            screen=screen,
            grounder=grounder,
            validator=validator,
            no_cache=no_cache,
            recorder=recorder,
        )

        total_steps += len(actions)
        total_time += elapsed
        total_tokens += tokens

        status = "PASS" if success else "FAIL"
        log(f"    Result: {status} ({len(actions)} actions, {elapsed:.1f}s, {tokens} tok)")

        if not success:
            all_success = False
            log(f"    Skill '{step.skill_id}' failed — continuing with remaining skills")

        if i < len(plan.steps) - 1:
            time.sleep(0.5)

    # Save GIF
    if recorder:
        recorder.stop()
        gif_dir = ROOT / "recordings" / "skills"
        gif_dir.mkdir(parents=True, exist_ok=True)
        gif_name = plan.intent[:40].replace(" ", "_").replace("/", "_").replace("\\", "_")
        gif_file = gif_dir / f"{gif_name}_{int(time.time())}.gif"
        try:
            gif_path = recorder.save(str(gif_file))
            log(f"\n  GIF saved: {gif_path}")
        except Exception as e:
            log(f"\n  GIF save error: {e}")

    try:
        screen.close()
    except Exception:
        pass

    log("")
    log("=" * 64)
    log(f"  RESULTS")
    log("=" * 64)
    overall = "SUCCESS" if all_success else "PARTIAL"
    log(f"  Status: {overall}")
    log(f"  Steps: {total_steps} | Time: {total_time:.1f}s | Tokens: {total_tokens}")
    log(f"  Cache: {cache.summary()}")
    log("=" * 64)

    return all_success, total_steps, total_time, total_tokens, gif_path


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="AgenticOS Skill Runner v1 — Composable, cacheable desktop automation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --intent "Turn brightness to 100%%"
  %(prog)s --skills open_quick_settings,set_slider:name:Brightness:value:100,close_panel
  %(prog)s --intent "Set volume to 50%%" --plan-only
  %(prog)s --intent "Open notepad and type Hello" --no-cache
  %(prog)s --list-skills
  %(prog)s --list-recipes
  %(prog)s --show-log
        """,
    )
    parser.add_argument("--intent", type=str, help="Natural language intent to execute")
    parser.add_argument("--skills", type=str, help="Comma-separated skill sequence (skill_id:param:val,...)")
    parser.add_argument("--plan-only", action="store_true", help="Show plan without executing")
    parser.add_argument("--no-cache", action="store_true", help="Skip cache, force fresh LLM execution")
    parser.add_argument("--no-gif", action="store_true", help="Don't record GIF")
    parser.add_argument("--show-log", action="store_true", help="Show recent action log entries")
    parser.add_argument("--list-skills", action="store_true", help="List all available skills")
    parser.add_argument("--list-recipes", action="store_true", help="List all available recipes")
    parser.add_argument("--cache-stats", action="store_true", help="Show cache statistics")
    parser.add_argument("--clear-cache", action="store_true", help="Clear the skill cache")
    args = parser.parse_args()

    # ── Info commands ──
    if args.list_skills:
        print(get_skill_catalog())
        print(f"\nTotal: {len(SKILLS)} skills")
        return

    if args.list_recipes:
        print("Available Recipes:\n")
        for r in RECIPES.values():
            chain = " → ".join(f"{sid}" for sid, _ in r.skills)
            print(f"  {r.id}: {r.description}")
            print(f"    Steps: {chain}\n")
        print(f"Total: {len(RECIPES)} recipes")
        return

    if args.show_log:
        action_logger = ActionLogger(str(LOG_FILE))
        entries = action_logger.read_recent(20)
        if not entries:
            print("No action log entries found.")
            return
        print(f"Recent actions ({len(entries)} entries):\n")
        for e in entries:
            cached_tag = "[CACHED]" if e.get("cached") else "[LIVE]"
            status = "PASS" if e.get("success") else "FAIL"
            print(f"  {e.get('timestamp', '?')} {cached_tag} {status} "
                  f"{e.get('skill_id', '?')}({json.dumps(e.get('params', {}))}) "
                  f"— {e.get('duration', 0):.1f}s, {e.get('tokens_used', 0)} tok")
        return

    cache = SkillCache(persist_path=str(CACHE_FILE))

    if args.cache_stats:
        print(cache.summary())
        entries = cache.get_all_entries()
        if entries:
            print(f"\nCached entries:")
            for e in entries:
                print(f"  {e.skill_id}({json.dumps(e.params)}) — "
                      f"replayed {e.replay_count}x, "
                      f"last used {time.strftime('%Y-%m-%d %H:%M', time.localtime(e.last_used))}")
        return

    if args.clear_cache:
        cache.clear()
        print("Cache cleared.")
        return

    # ── Compose plan ──
    if not args.intent and not args.skills:
        parser.print_help()
        return

    token = get_token()
    composer = SkillComposer(token=token)

    if args.skills:
        skill_specs = [s.strip() for s in args.skills.split(",")]
        plan = composer.compose_from_skills(skill_specs)
    else:
        plan = composer.compose(args.intent, use_llm=True)

    if not plan.steps:
        print(f"Could not decompose intent: '{args.intent}'")
        print("Try --list-skills to see available skills, or use --skills for explicit specification.")
        return

    log(f"Plan: {plan.summary()}")

    if args.plan_only:
        print(f"\nPlan for: {plan.intent}")
        print(f"Source: {plan.source} (confidence={plan.confidence:.0%})")
        print(f"Steps:")
        for i, s in enumerate(plan.steps):
            skill = SKILLS.get(s.skill_id)
            name = skill.name if skill else s.skill_id
            print(f"  {i+1}. {name} — {s.params}")
        print(f"\nTo execute: remove --plan-only flag")
        return

    # ── Execute plan ──
    action_logger = ActionLogger(str(LOG_FILE))
    success, steps, elapsed, tokens, gif = run_plan(
        plan=plan,
        token=token,
        cache=cache,
        action_logger=action_logger,
        no_cache=args.no_cache,
        record_gif=not args.no_gif,
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
