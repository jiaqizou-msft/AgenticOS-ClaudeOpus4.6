"""Action compositor — sequences, retries, and verifies OS actions.

Provides the action abstraction layer between the agent's decisions
and the raw executors (keyboard, mouse, shell, window).
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from agenticos.actions.keyboard import KeyboardExecutor
from agenticos.actions.mouse import MouseExecutor
from agenticos.actions.shell import ShellExecutor, ShellResult
from agenticos.actions.window import WindowManager
from agenticos.utils.exceptions import ActionError


class ActionType(str, Enum):
    """Types of actions the agent can perform."""
    CLICK = "click"
    DOUBLE_CLICK = "double_click"
    RIGHT_CLICK = "right_click"
    TYPE_TEXT = "type_text"
    PRESS_KEY = "press_key"
    HOTKEY = "hotkey"
    SCROLL = "scroll"
    DRAG = "drag"
    SET_SLIDER = "set_slider"
    SHELL = "shell"
    OPEN_APP = "open_app"
    FOCUS_WINDOW = "focus_window"
    CLOSE_WINDOW = "close_window"
    MINIMIZE_WINDOW = "minimize_window"
    MAXIMIZE_WINDOW = "maximize_window"
    WAIT = "wait"
    SCREENSHOT = "screenshot"


@dataclass
class Action:
    """An action to be executed on the OS.

    Attributes:
        type: The type of action.
        params: Parameters for the action.
        description: Human-readable description.
        element_idx: Index of the target UI element (from grounding).
        requires_confirmation: Whether user must confirm this action.
    """
    type: ActionType
    params: dict[str, Any] = field(default_factory=dict)
    description: str = ""
    element_idx: Optional[int] = None
    requires_confirmation: bool = False

    @classmethod
    def click(cls, x: int, y: int, description: str = "") -> "Action":
        return cls(ActionType.CLICK, {"x": x, "y": y}, description)

    @classmethod
    def double_click(cls, x: int, y: int, description: str = "") -> "Action":
        return cls(ActionType.DOUBLE_CLICK, {"x": x, "y": y}, description)

    @classmethod
    def right_click(cls, x: int, y: int, description: str = "") -> "Action":
        return cls(ActionType.RIGHT_CLICK, {"x": x, "y": y}, description)

    @classmethod
    def type_text(cls, text: str, description: str = "") -> "Action":
        return cls(ActionType.TYPE_TEXT, {"text": text}, description)

    @classmethod
    def press_key(cls, key: str, description: str = "") -> "Action":
        return cls(ActionType.PRESS_KEY, {"key": key}, description)

    @classmethod
    def hotkey(cls, *keys: str, description: str = "") -> "Action":
        return cls(ActionType.HOTKEY, {"keys": list(keys)}, description)

    @classmethod
    def scroll(cls, x: int, y: int, clicks: int = -3, description: str = "") -> "Action":
        return cls(ActionType.SCROLL, {"x": x, "y": y, "clicks": clicks}, description)

    @classmethod
    def shell(cls, command: str, description: str = "") -> "Action":
        return cls(ActionType.SHELL, {"command": command}, description)

    @classmethod
    def open_app(cls, app_name: str, description: str = "") -> "Action":
        return cls(ActionType.OPEN_APP, {"app_name": app_name}, description)

    @classmethod
    def focus_window(cls, title: str, description: str = "") -> "Action":
        return cls(ActionType.FOCUS_WINDOW, {"title": title}, description)

    @classmethod
    def wait(cls, seconds: float = 1.0, description: str = "") -> "Action":
        return cls(ActionType.WAIT, {"seconds": seconds}, description)


@dataclass
class ActionResult:
    """Result of executing an action.

    Attributes:
        action: The action that was executed.
        success: Whether the action succeeded.
        error: Error message if failed.
        output: Output data (e.g., shell command output).
        elapsed_ms: Execution time in milliseconds.
        retry_count: Number of retries attempted.
    """
    action: Action
    success: bool
    error: Optional[str] = None
    output: Optional[str] = None
    elapsed_ms: float = 0.0
    retry_count: int = 0


class ActionCompositor:
    """Composes and executes actions with retry logic and verification.

    Bridges the agent's action decisions with the raw executors,
    adding safety checks, retries, and inter-action delays.

    Example:
        >>> compositor = ActionCompositor()
        >>> action = Action.click(500, 300, "Click Save button")
        >>> result = compositor.execute(action)
        >>> print(result.success)
    """

    def __init__(
        self,
        max_retries: int = 2,
        retry_delay: float = 0.5,
        inter_action_delay: float = 0.3,
    ) -> None:
        """Initialize the action compositor.

        Args:
            max_retries: Maximum retries per action on failure.
            retry_delay: Delay between retries in seconds.
            inter_action_delay: Delay between sequential actions.
        """
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.inter_action_delay = inter_action_delay

        self.keyboard = KeyboardExecutor()
        self.mouse = MouseExecutor()
        self.shell = ShellExecutor()
        self.window = WindowManager()

    def execute(self, action: Action) -> ActionResult:
        """Execute a single action with retry logic.

        Args:
            action: The action to execute.

        Returns:
            ActionResult with success/failure details.
        """
        last_error = None

        for attempt in range(self.max_retries + 1):
            try:
                start = time.perf_counter()
                output = self._dispatch(action)
                elapsed_ms = (time.perf_counter() - start) * 1000

                return ActionResult(
                    action=action,
                    success=True,
                    output=output,
                    elapsed_ms=elapsed_ms,
                    retry_count=attempt,
                )

            except ActionError as e:
                last_error = str(e)
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay)

        return ActionResult(
            action=action,
            success=False,
            error=last_error,
            retry_count=self.max_retries,
        )

    def execute_sequence(
        self,
        actions: list[Action],
        stop_on_failure: bool = True,
    ) -> list[ActionResult]:
        """Execute a sequence of actions in order.

        Args:
            actions: List of actions to execute.
            stop_on_failure: Whether to stop the sequence on first failure.

        Returns:
            List of ActionResult objects.
        """
        results: list[ActionResult] = []

        for action in actions:
            result = self.execute(action)
            results.append(result)

            if not result.success and stop_on_failure:
                break

            time.sleep(self.inter_action_delay)

        return results

    def _dispatch(self, action: Action) -> Optional[str]:
        """Route action to the appropriate executor.

        Args:
            action: Action to dispatch.

        Returns:
            Output string if any.

        Raises:
            ActionError: If execution fails.
        """
        p = action.params

        match action.type:
            case ActionType.CLICK:
                self.mouse.click(p["x"], p["y"])
            case ActionType.DOUBLE_CLICK:
                self.mouse.double_click(p["x"], p["y"])
            case ActionType.RIGHT_CLICK:
                self.mouse.right_click(p["x"], p["y"])
            case ActionType.TYPE_TEXT:
                self.keyboard.type_unicode(p["text"])
            case ActionType.PRESS_KEY:
                self.keyboard.press(p["key"])
            case ActionType.HOTKEY:
                self.keyboard.hotkey(*p["keys"])
            case ActionType.SCROLL:
                self.mouse.scroll(p["x"], p["y"], p.get("clicks", -3))
            case ActionType.DRAG:
                self.mouse.drag(
                    p["start_x"], p["start_y"],
                    p["end_x"], p["end_y"],
                )
            case ActionType.SET_SLIDER:
                return self._set_slider_via_uia(
                    p.get("name", ""),
                    p.get("value", 50),
                )
            case ActionType.SHELL:
                result: ShellResult = self.shell.run(p["command"])
                return result.output
            case ActionType.OPEN_APP:
                result = self.shell.open_application(p["app_name"])
                time.sleep(1.0)  # Wait for app to start
                return result.output
            case ActionType.FOCUS_WINDOW:
                self.window.focus(p["title"])
            case ActionType.CLOSE_WINDOW:
                self.window.close(p["title"])
            case ActionType.MINIMIZE_WINDOW:
                self.window.minimize(p["title"])
            case ActionType.MAXIMIZE_WINDOW:
                self.window.maximize(p["title"])
            case ActionType.WAIT:
                time.sleep(p.get("seconds", 1.0))
            case ActionType.SCREENSHOT:
                return "[screenshot captured]"
            case _:
                raise ActionError(f"Unknown action type: {action.type}")

        return None

    def _set_slider_via_uia(self, name: str, value: float) -> str:
        """Set a slider value directly via UIA RangeValuePattern.

        This bypasses coordinate-based drag entirely and works reliably
        with WinUI/XAML/UWP sliders (e.g., Windows Quick Settings).

        Args:
            name: Slider name (e.g., 'Brightness', 'Sound output').
                  Matching is case-insensitive and partial (e.g., 'volume' matches 'Sound output').
            value: Target value as a percentage (0-100).

        Returns:
            Status message.

        Raises:
            ActionError: If slider cannot be found or set.
        """
        # Common aliases for slider names
        NAME_ALIASES = {
            "volume": "sound output",
            "sound": "sound output",
            "audio": "sound output",
            "speaker": "sound output",
            "brightness": "brightness",
            "display": "brightness",
            "screen": "brightness",
        }

        # Normalize the search name
        search_name = name.lower().strip()
        canonical = NAME_ALIASES.get(search_name, search_name)

        try:
            from pywinauto import Desktop

            desktop = Desktop(backend="uia")
            slider = None

            # Search all visible windows for the named slider
            for win in desktop.windows():
                try:
                    if not win.is_visible():
                        continue
                    matches = win.descendants(control_type="Slider")
                    for s in matches:
                        s_name = (s.element_info.name or "").lower()
                        # Match by canonical name or original search name
                        if canonical in s_name or search_name in s_name:
                            slider = s
                            break
                    if slider:
                        break
                except Exception:
                    continue

            if not slider:
                raise ActionError(f"Slider '{name}' not found via UIA")

            # Use RangeValuePattern with correct COM property names
            try:
                iface = slider.iface_range_value
                min_val = iface.CurrentMinimum
                max_val = iface.CurrentMaximum
                old_val = iface.CurrentValue
                # Convert percentage to actual range value
                target = min_val + (max_val - min_val) * value / 100.0
                iface.SetValue(target)
                slider_name = slider.element_info.name or name
                return (
                    f"Set '{slider_name}' from {old_val:.0f} to {target:.0f} "
                    f"({value}%, range: {min_val:.0f}-{max_val:.0f})"
                )
            except Exception as e1:
                # Fallback: click at the percentage position on the slider
                try:
                    rect = slider.rectangle()
                    target_x = rect.left + int((rect.right - rect.left) * value / 100.0)
                    target_y = (rect.top + rect.bottom) // 2
                    self.mouse.click(target_x, target_y)
                    return f"Clicked slider '{name}' at {value}% position ({target_x}, {target_y})"
                except Exception as e2:
                    raise ActionError(
                        f"Cannot set slider '{name}': RangeValue failed ({e1}), click failed ({e2})"
                    )
        except ImportError:
            raise ActionError("pywinauto required for set_slider")
        except ActionError:
            raise
        except Exception as e:
            raise ActionError(f"set_slider failed: {e}") from e
