"""Recovery strategies for UI navigation errors.

Provides common undo/go-back patterns based on standard Windows UI
conventions. When the agent detects it's on the wrong page or stuck,
these strategies help return to a known-good state.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class RecoveryStrategy(str, Enum):
    """Standard recovery strategies based on UI conventions."""
    ESCAPE = "escape"           # Close dialog, cancel, exit fullscreen
    ALT_LEFT = "alt_left"       # Browser/Explorer back navigation
    ALT_F4 = "alt_f4"           # Close current window
    CTRL_Z = "ctrl_z"           # Undo last action
    CTRL_W = "ctrl_w"           # Close current tab (browser)
    CLICK_BACK = "click_back"   # Click a visible back button
    CLOSE_DIALOG = "close_dialog"  # Press Enter or Escape on a dialog
    REFOCUS = "refocus"         # Alt+Tab to switch windows
    RESTART_APP = "restart_app" # Close and reopen app


@dataclass
class RecoveryAction:
    """A concrete recovery action to execute."""
    strategy: RecoveryStrategy
    description: str
    action_type: str
    action_params: dict
    delay_after: float = 0.5


# Context-aware recovery strategies
APP_RECOVERY_MAP: dict[str, list[RecoveryStrategy]] = {
    # Browsers
    "edge": [RecoveryStrategy.ESCAPE, RecoveryStrategy.ALT_LEFT, RecoveryStrategy.CTRL_W],
    "chrome": [RecoveryStrategy.ESCAPE, RecoveryStrategy.ALT_LEFT, RecoveryStrategy.CTRL_W],
    "firefox": [RecoveryStrategy.ESCAPE, RecoveryStrategy.ALT_LEFT, RecoveryStrategy.CTRL_W],
    # Office apps — do NOT auto-undo (Ctrl+Z) in compose windows, it deletes text
    "outlook": [RecoveryStrategy.ESCAPE],
    "teams": [RecoveryStrategy.ESCAPE],
    "word": [RecoveryStrategy.ESCAPE, RecoveryStrategy.CTRL_Z],
    "excel": [RecoveryStrategy.ESCAPE, RecoveryStrategy.CTRL_Z],
    # System — Quick Settings: do NOT press Escape (it closes the panel!)
    "quick settings": [],  # No automatic recovery — let LLM figure it out
    "settings": [RecoveryStrategy.ESCAPE, RecoveryStrategy.ALT_LEFT, RecoveryStrategy.CLICK_BACK],
    "explorer": [],  # No auto-recovery — Escape cancels rename, Alt+Left navigates back
    "file explorer": [],  # Same as explorer
    # v2 apps
    "surface": [RecoveryStrategy.ESCAPE, RecoveryStrategy.CLICK_BACK],
    "paint": [RecoveryStrategy.ESCAPE, RecoveryStrategy.CTRL_Z],
    "snipping": [RecoveryStrategy.ESCAPE],
    "store": [RecoveryStrategy.ESCAPE, RecoveryStrategy.ALT_LEFT],
    "powerpoint": [RecoveryStrategy.ESCAPE, RecoveryStrategy.CTRL_Z],
    "security": [RecoveryStrategy.ESCAPE, RecoveryStrategy.ALT_LEFT],
    "feedback": [RecoveryStrategy.ESCAPE],
    "clipboard": [],  # Win+V panel — Escape closes it
    # Generic
    "default": [RecoveryStrategy.ESCAPE, RecoveryStrategy.ALT_LEFT, RecoveryStrategy.CTRL_Z],
}


def _strategy_to_action(strategy: RecoveryStrategy) -> RecoveryAction:
    """Convert a strategy enum to a concrete action."""
    match strategy:
        case RecoveryStrategy.ESCAPE:
            return RecoveryAction(
                strategy=strategy,
                description="Press Escape to close dialog/menu/fullscreen",
                action_type="press_key",
                action_params={"key": "escape"},
            )
        case RecoveryStrategy.ALT_LEFT:
            return RecoveryAction(
                strategy=strategy,
                description="Press Alt+Left to go back",
                action_type="hotkey",
                action_params={"keys": ["alt", "left"]},
            )
        case RecoveryStrategy.ALT_F4:
            return RecoveryAction(
                strategy=strategy,
                description="Press Alt+F4 to close window",
                action_type="hotkey",
                action_params={"keys": ["alt", "F4"]},
                delay_after=1.0,
            )
        case RecoveryStrategy.CTRL_Z:
            return RecoveryAction(
                strategy=strategy,
                description="Press Ctrl+Z to undo",
                action_type="hotkey",
                action_params={"keys": ["ctrl", "z"]},
            )
        case RecoveryStrategy.CTRL_W:
            return RecoveryAction(
                strategy=strategy,
                description="Press Ctrl+W to close tab",
                action_type="hotkey",
                action_params={"keys": ["ctrl", "w"]},
                delay_after=0.5,
            )
        case RecoveryStrategy.REFOCUS:
            return RecoveryAction(
                strategy=strategy,
                description="Press Alt+Tab to switch windows",
                action_type="hotkey",
                action_params={"keys": ["alt", "tab"]},
                delay_after=0.5,
            )
        case RecoveryStrategy.CLOSE_DIALOG:
            return RecoveryAction(
                strategy=strategy,
                description="Press Enter to dismiss dialog",
                action_type="press_key",
                action_params={"key": "enter"},
            )
        case _:
            return RecoveryAction(
                strategy=RecoveryStrategy.ESCAPE,
                description="Press Escape (fallback)",
                action_type="press_key",
                action_params={"key": "escape"},
            )


class RecoveryManager:
    """Manages recovery from wrong UI states.

    Tracks recovery attempts and provides context-aware undo strategies.
    """

    def __init__(self, max_recovery_attempts: int = 3) -> None:
        self.max_recovery_attempts = max_recovery_attempts
        self._attempts: dict[str, int] = {}  # strategy -> count
        self._total_recoveries: int = 0

    def get_recovery_actions(
        self,
        window_title: str = "",
        hint: str = "",
    ) -> list[RecoveryAction]:
        """Get ordered list of recovery actions for the current context.

        Args:
            window_title: Current foreground window title.
            hint: Optional hint from the state validator.

        Returns:
            Ordered list of recovery actions to try.
        """
        # Determine app context from window title
        title_lower = window_title.lower()

        # No recovery for desktop/empty window (LLM needs to re-open the right app)
        if not title_lower.strip():
            return []

        strategies = list(APP_RECOVERY_MAP.get("default", []))

        for app_key, app_strategies in APP_RECOVERY_MAP.items():
            if app_key in title_lower:
                strategies = list(app_strategies)
                break

        # Filter out strategies already tried too many times
        available = [
            s for s in strategies
            if self._attempts.get(s.value, 0) < self.max_recovery_attempts
        ]

        if not available:
            # Reset and try again from scratch
            self._attempts.clear()
            available = strategies

        return [_strategy_to_action(s) for s in available]

    def record_attempt(self, strategy: RecoveryStrategy) -> None:
        """Record that a recovery strategy was attempted."""
        self._attempts[strategy.value] = self._attempts.get(strategy.value, 0) + 1
        self._total_recoveries += 1

    def reset(self) -> None:
        """Reset recovery state for a new task."""
        self._attempts.clear()
        self._total_recoveries = 0

    @property
    def total_recoveries(self) -> int:
        return self._total_recoveries

    def should_abort(self) -> bool:
        """Check if we've exhausted all recovery options."""
        return self._total_recoveries >= self.max_recovery_attempts * len(RecoveryStrategy)
