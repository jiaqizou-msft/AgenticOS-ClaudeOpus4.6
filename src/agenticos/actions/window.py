"""Window management actions.

Controls window focus, positioning, resizing, minimize/maximize/restore
using pywinauto and Win32 API.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

from agenticos.utils.exceptions import ActionError


@dataclass
class WindowInfo:
    """Information about a window.

    Attributes:
        title: Window title.
        handle: Window handle (HWND).
        pid: Process ID.
        bbox: Window bounding box (left, top, right, bottom).
        is_visible: Whether the window is visible.
        is_minimized: Whether the window is minimized.
        is_maximized: Whether the window is maximized.
        class_name: Window class name.
    """
    title: str
    handle: int
    pid: int
    bbox: tuple[int, int, int, int]
    is_visible: bool
    is_minimized: bool
    is_maximized: bool
    class_name: str = ""


class WindowManager:
    """Manages windows — focus, position, resize, minimize/maximize.

    Uses pywinauto for reliable cross-app window management on Windows.

    Example:
        >>> wm = WindowManager()
        >>> windows = wm.list_windows()
        >>> wm.focus("Notepad")
        >>> wm.maximize("Notepad")
    """

    def list_windows(self, visible_only: bool = True) -> list[WindowInfo]:
        """List all open windows.

        Args:
            visible_only: Only include visible windows.

        Returns:
            List of WindowInfo objects.
        """
        try:
            from pywinauto import Desktop

            desktop = Desktop(backend="uia")
            windows: list[WindowInfo] = []

            for win in desktop.windows():
                try:
                    if visible_only and not win.is_visible():
                        continue

                    rect = win.rectangle()
                    info = win.element_info

                    windows.append(
                        WindowInfo(
                            title=win.window_text() or "",
                            handle=getattr(info, "handle", 0) or 0,
                            pid=getattr(info, "process_id", 0) or 0,
                            bbox=(rect.left, rect.top, rect.right, rect.bottom),
                            is_visible=win.is_visible(),
                            is_minimized=win.is_minimized(),
                            is_maximized=win.is_maximized(),
                            class_name=getattr(info, "class_name", "") or "",
                        )
                    )
                except Exception:
                    continue

            return windows

        except ImportError:
            raise ActionError("pywinauto is required for window management")
        except Exception as e:
            raise ActionError(f"Failed to list windows: {e}") from e

    def focus(self, title: str) -> bool:
        """Bring a window to the foreground by title.

        Args:
            title: Window title (partial match supported).

        Returns:
            True if window was found and focused.

        Raises:
            ActionError: If focus fails.
        """
        try:
            from pywinauto.application import Application

            app = Application(backend="uia").connect(title_re=f".*{title}.*", timeout=5)
            window = app.top_window()
            window.set_focus()
            time.sleep(0.3)
            return True

        except Exception as e:
            raise ActionError(f"Failed to focus window '{title}': {e}") from e

    def minimize(self, title: str) -> None:
        """Minimize a window.

        Args:
            title: Window title.
        """
        try:
            from pywinauto.application import Application

            app = Application(backend="uia").connect(title_re=f".*{title}.*", timeout=5)
            app.top_window().minimize()
        except Exception as e:
            raise ActionError(f"Failed to minimize '{title}': {e}") from e

    def maximize(self, title: str) -> None:
        """Maximize a window.

        Args:
            title: Window title.
        """
        try:
            from pywinauto.application import Application

            app = Application(backend="uia").connect(title_re=f".*{title}.*", timeout=5)
            app.top_window().maximize()
        except Exception as e:
            raise ActionError(f"Failed to maximize '{title}': {e}") from e

    def restore(self, title: str) -> None:
        """Restore a minimized/maximized window.

        Args:
            title: Window title.
        """
        try:
            from pywinauto.application import Application

            app = Application(backend="uia").connect(title_re=f".*{title}.*", timeout=5)
            app.top_window().restore()
        except Exception as e:
            raise ActionError(f"Failed to restore '{title}': {e}") from e

    def close(self, title: str) -> None:
        """Close a window.

        Args:
            title: Window title.
        """
        try:
            from pywinauto.application import Application

            app = Application(backend="uia").connect(title_re=f".*{title}.*", timeout=5)
            app.top_window().close()
        except Exception as e:
            raise ActionError(f"Failed to close '{title}': {e}") from e

    def resize(
        self, title: str, width: int, height: int
    ) -> None:
        """Resize a window.

        Args:
            title: Window title.
            width: New width in pixels.
            height: New height in pixels.
        """
        try:
            from pywinauto.application import Application

            app = Application(backend="uia").connect(title_re=f".*{title}.*", timeout=5)
            window = app.top_window()
            rect = window.rectangle()
            window.move_window(rect.left, rect.top, width, height)
        except Exception as e:
            raise ActionError(f"Failed to resize '{title}': {e}") from e

    def move(self, title: str, x: int, y: int) -> None:
        """Move a window to new coordinates.

        Args:
            title: Window title.
            x: New X position.
            y: New Y position.
        """
        try:
            from pywinauto.application import Application

            app = Application(backend="uia").connect(title_re=f".*{title}.*", timeout=5)
            window = app.top_window()
            rect = window.rectangle()
            w = rect.right - rect.left
            h = rect.bottom - rect.top
            window.move_window(x, y, w, h)
        except Exception as e:
            raise ActionError(f"Failed to move '{title}': {e}") from e

    def get_foreground(self) -> Optional[WindowInfo]:
        """Get info about the currently focused window.

        Returns:
            WindowInfo of the foreground window, or None.
        """
        try:
            import win32gui  # type: ignore[import]
            import win32process  # type: ignore[import]

            hwnd = win32gui.GetForegroundWindow()
            title = win32gui.GetWindowText(hwnd)
            rect = win32gui.GetWindowRect(hwnd)
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            class_name = win32gui.GetClassName(hwnd)

            return WindowInfo(
                title=title,
                handle=hwnd,
                pid=pid,
                bbox=rect,
                is_visible=True,
                is_minimized=False,
                is_maximized=False,
                class_name=class_name,
            )
        except Exception:
            return None
