"""Mouse action executor.

Handles mouse movement, clicking, scrolling, and dragging via pyautogui.
"""

from __future__ import annotations

import time
from typing import Optional

import pyautogui

from agenticos.utils.exceptions import ActionError


class MouseExecutor:
    """Executes mouse actions on the OS.

    Provides precise mouse control for clicking, moving, scrolling,
    and dragging operations.

    Example:
        >>> mouse = MouseExecutor()
        >>> mouse.click(500, 300)
        >>> mouse.double_click(500, 300)
        >>> mouse.scroll(0, -3)  # scroll down 3 clicks
    """

    def __init__(self, move_duration: float = 0.5) -> None:
        """Initialize mouse executor.

        Args:
            move_duration: Duration of mouse movement animation in seconds.
                          Default 0.5s for visible real-time cursor movement.
        """
        self.move_duration = move_duration

    def click(
        self,
        x: int,
        y: int,
        button: str = "left",
        clicks: int = 1,
    ) -> None:
        """Click at screen coordinates.

        Args:
            x: X coordinate.
            y: Y coordinate.
            button: Mouse button ('left', 'right', 'middle').
            clicks: Number of clicks.

        Raises:
            ActionError: If click fails.
        """
        try:
            # Smooth move to target first so user sees cursor travel
            pyautogui.moveTo(x, y, duration=self.move_duration)
            time.sleep(0.05)  # Brief settle before click
            pyautogui.click(
                x=x,
                y=y,
                button=button,
                clicks=clicks,
                _pause=True,
            )
        except Exception as e:
            raise ActionError(f"Failed to click at ({x}, {y}): {e}") from e

    def double_click(self, x: int, y: int) -> None:
        """Double-click at screen coordinates.

        Args:
            x: X coordinate.
            y: Y coordinate.
        """
        self.click(x, y, clicks=2)

    def right_click(self, x: int, y: int) -> None:
        """Right-click at screen coordinates.

        Args:
            x: X coordinate.
            y: Y coordinate.
        """
        self.click(x, y, button="right")

    def move_to(self, x: int, y: int, duration: Optional[float] = None) -> None:
        """Move mouse to screen coordinates.

        Args:
            x: Target X coordinate.
            y: Target Y coordinate.
            duration: Movement duration override.

        Raises:
            ActionError: If movement fails.
        """
        try:
            pyautogui.moveTo(
                x=x,
                y=y,
                duration=duration or self.move_duration,
            )
        except Exception as e:
            raise ActionError(f"Failed to move to ({x}, {y}): {e}") from e

    def scroll(self, x: int, y: int, clicks: int = -3) -> None:
        """Scroll at a specific position.

        Args:
            x: X coordinate to scroll at.
            y: Y coordinate to scroll at.
            clicks: Number of scroll clicks (negative = down, positive = up).

        Raises:
            ActionError: If scroll fails.
        """
        try:
            # Move to position first so user sees where we're scrolling
            pyautogui.moveTo(x, y, duration=self.move_duration * 0.5)
            time.sleep(0.05)
            pyautogui.scroll(clicks, x=x, y=y)
        except Exception as e:
            raise ActionError(f"Failed to scroll at ({x}, {y}): {e}") from e

    def drag(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        duration: float = 0.8,
        button: str = "left",
    ) -> None:
        """Drag from one position to another.

        Uses explicit mouseDown → moveTo → mouseUp instead of pyautogui.drag()
        because pyautogui.drag() sends synthetic relative mouse events that
        WinUI/XAML/UWP controls (like Quick Settings sliders) often ignore.

        Args:
            start_x: Start X coordinate.
            start_y: Start Y coordinate.
            end_x: End X coordinate.
            end_y: End Y coordinate.
            duration: Drag duration in seconds (default 0.8s for visible drag).
            button: Mouse button to use.

        Raises:
            ActionError: If drag fails.
        """
        try:
            # 1. Move cursor visibly to start position
            pyautogui.moveTo(start_x, start_y, duration=self.move_duration)
            time.sleep(0.15)  # Settle at start

            # 2. Explicit mouseDown → moveTo → mouseUp sequence
            #    This works with WinUI/XAML sliders that ignore pyautogui.drag()
            pyautogui.mouseDown(x=start_x, y=start_y, button=button)
            time.sleep(0.05)  # Brief hold before moving

            # 3. Move to end position with visible duration
            pyautogui.moveTo(end_x, end_y, duration=duration)
            time.sleep(0.05)  # Brief hold at end before release

            # 4. Release
            pyautogui.mouseUp(x=end_x, y=end_y, button=button)
            time.sleep(0.1)  # Settle after release
        except Exception as e:
            # Safety: always try to release mouse button
            try:
                pyautogui.mouseUp(button=button)
            except Exception:
                pass
            raise ActionError(
                f"Failed to drag from ({start_x},{start_y}) to ({end_x},{end_y}): {e}"
            ) from e

    def get_position(self) -> tuple[int, int]:
        """Get current mouse position.

        Returns:
            Tuple of (x, y) coordinates.
        """
        pos = pyautogui.position()
        return (pos[0], pos[1])

    def hover(self, x: int, y: int, duration: float = 1.0) -> None:
        """Move to coordinates and hover.

        Args:
            x: X coordinate.
            y: Y coordinate.
            duration: How long to hover in seconds.
        """
        self.move_to(x, y)
        time.sleep(duration)
