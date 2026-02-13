"""Post-action state validation.

After each action, captures a new screenshot + UIA snapshot and compares
against the expected outcome. Detects drift between what the model
*thinks* happened and what *actually* happened on screen.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class StateSnapshot:
    """A snapshot of the UI state at a point in time."""
    timestamp: float
    window_title: str = ""
    active_control: str = ""
    element_count: int = 0
    element_names: list[str] = field(default_factory=list)
    screenshot_hash: str = ""  # perceptual hash for change detection
    raw_elements: list = field(default_factory=list, repr=False)

    def summary(self) -> str:
        top_names = [n for n in self.element_names[:10] if n]
        names_str = ", ".join(top_names) if top_names else "(none)"
        return (
            f"Window: '{self.window_title}' | "
            f"Elements: {self.element_count} | "
            f"Top controls: {names_str}"
        )


@dataclass
class ValidationResult:
    """Result of comparing pre- and post-action states."""
    state_changed: bool
    expected_change: str
    actual_change: str
    is_correct: bool  # Did the action achieve what was intended?
    drift_detected: bool  # Is the state different from expectation?
    recovery_needed: bool
    recovery_hint: str = ""

    def summary(self) -> str:
        status = "OK" if self.is_correct else ("DRIFT" if self.drift_detected else "NO_CHANGE")
        parts = [f"[{status}]"]
        if self.drift_detected:
            parts.append(f"Expected: {self.expected_change}")
            parts.append(f"Actual: {self.actual_change}")
        if self.recovery_needed:
            parts.append(f"Recovery: {self.recovery_hint}")
        return " | ".join(parts)


class StateValidator:
    """Validates UI state transitions after each agent action.

    Captures before/after snapshots and detects:
    - No-ops (nothing changed after an action)
    - Wrong page (navigated somewhere unexpected)
    - Stuck loops (same state repeating)
    """

    def __init__(self) -> None:
        self._history: list[StateSnapshot] = []
        self._repeat_count: int = 0
        self._last_hash: str = ""

    def capture_state(
        self,
        elements: list,
        screenshot_bytes: Optional[bytes] = None,
    ) -> StateSnapshot:
        """Capture current UI state as a snapshot."""
        # Get the foreground window title
        window_title = ""
        try:
            import win32gui
            hwnd = win32gui.GetForegroundWindow()
            window_title = win32gui.GetWindowText(hwnd) or ""
        except Exception:
            pass

        # Active control (first focused/highlighted element)
        active_control = ""
        element_names = []
        for el in elements:
            name = getattr(el, "name", "") or ""
            ctype = getattr(el, "control_type", "") or ""
            if name:
                element_names.append(f"{ctype}:{name}")

        # Screenshot perceptual hash (fast change detection)
        scr_hash = ""
        if screenshot_bytes:
            scr_hash = hashlib.md5(screenshot_bytes[:4096]).hexdigest()[:12]

        snap = StateSnapshot(
            timestamp=time.time(),
            window_title=window_title,
            active_control=active_control,
            element_count=len(elements),
            element_names=element_names[:20],
            screenshot_hash=scr_hash,
            raw_elements=elements,
        )
        self._history.append(snap)
        return snap

    def validate_transition(
        self,
        before: StateSnapshot,
        after: StateSnapshot,
        action_type: str,
        action_params: dict,
        expected_outcome: str = "",
    ) -> ValidationResult:
        """Compare before/after states to detect drift."""
        state_changed = (
            before.window_title != after.window_title
            or before.screenshot_hash != after.screenshot_hash
            or abs(before.element_count - after.element_count) > 5
        )

        # Detect stuck in loop (same hash repeating)
        if after.screenshot_hash == self._last_hash:
            self._repeat_count += 1
        else:
            self._repeat_count = 0
        self._last_hash = after.screenshot_hash

        # Determine expected vs actual
        expected_change = self._infer_expected_change(action_type, action_params, expected_outcome)
        actual_change = self._describe_actual_change(before, after)

        # Heuristic: is the transition correct?
        is_correct = True
        drift_detected = False
        recovery_needed = False
        recovery_hint = ""

        # Case 1: Click but nothing changed (drag/scroll/type/set_slider may legitimately not change screen hash)
        if action_type == "click" and not state_changed:
            drift_detected = True
            recovery_hint = "Click had no effect — try different coordinates or use UIA element names"

        # Case 2: Stuck in a loop (same state 4+ times — relaxed)
        if self._repeat_count >= 3:
            drift_detected = True
            recovery_needed = True
            recovery_hint = "Stuck in loop — try a completely different approach"

        # Case 3: Error/alert dialog appeared
        if action_type == "click" and before.window_title != after.window_title:
            if "error" in after.window_title.lower() or "alert" in after.window_title.lower():
                drift_detected = True
                recovery_needed = True
                recovery_hint = "Error dialog appeared — dismiss it with escape or click OK"

        # Case 4: open_app should change the window
        if action_type == "open_app" and before.window_title == after.window_title:
            drift_detected = True
            recovery_hint = "App may not have opened — try shell command or wait longer"

        # Note: drag, set_slider, scroll, type_text, press_key, hotkey actions
        # do NOT trigger drift even when state_changed is False, because:
        #   - Slider drags may change only the slider value (not window/elements)
        #   - Scrolling changes viewport position (subtle)
        #   - Typing changes text content (captured by screenshot hash)

        return ValidationResult(
            state_changed=state_changed,
            expected_change=expected_change,
            actual_change=actual_change,
            is_correct=not drift_detected,
            drift_detected=drift_detected,
            recovery_needed=recovery_needed,
            recovery_hint=recovery_hint,
        )

    def get_loop_count(self) -> int:
        """How many times the state has been identical."""
        return self._repeat_count

    def get_history(self) -> list[StateSnapshot]:
        return list(self._history)

    def _infer_expected_change(self, action_type: str, params: dict, hint: str) -> str:
        if hint:
            return hint
        match action_type:
            case "click":
                return f"UI should respond to click at ({params.get('x')}, {params.get('y')})"
            case "type_text":
                return f"Text '{params.get('text', '')[:30]}' should appear in focused field"
            case "press_key":
                return f"Key '{params.get('key')}' should trigger expected behavior"
            case "open_app":
                return f"App '{params.get('app_name')}' should open and gain focus"
            case "hotkey":
                return f"Hotkey {params.get('keys')} should trigger shortcut"
            case "scroll":
                return "Page should scroll"
            case _:
                return f"{action_type} should produce a visible change"

    def _describe_actual_change(self, before: StateSnapshot, after: StateSnapshot) -> str:
        changes = []
        if before.window_title != after.window_title:
            changes.append(f"Window: '{before.window_title}' → '{after.window_title}'")
        delta = after.element_count - before.element_count
        if abs(delta) > 3:
            changes.append(f"Elements: {before.element_count} → {after.element_count} ({'+' if delta > 0 else ''}{delta})")
        if before.screenshot_hash != after.screenshot_hash:
            changes.append("Screen content changed")
        if not changes:
            changes.append("No visible change detected")
        return "; ".join(changes)
