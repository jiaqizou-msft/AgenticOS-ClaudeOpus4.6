"""Keyboard action executor.

Handles text typing, key presses, hotkey combinations via pyautogui.
"""

from __future__ import annotations

import time
from typing import Optional

import pyautogui

from agenticos.utils.exceptions import ActionError

# Safety: disable pyautogui's fail-safe only when explicitly asked
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.05


class KeyboardExecutor:
    """Executes keyboard actions on the OS.

    Provides methods for typing text, pressing individual keys,
    and executing hotkey combinations.

    Example:
        >>> kb = KeyboardExecutor()
        >>> kb.type_text("Hello, World!")
        >>> kb.hotkey("ctrl", "s")
        >>> kb.press("enter")
    """

    def __init__(self, typing_interval: float = 0.06) -> None:
        """Initialize keyboard executor.

        Args:
            typing_interval: Delay between keystrokes in seconds.
                           Default 0.06s for visible real-time typing.
        """
        self.typing_interval = typing_interval

    def type_text(self, text: str, interval: Optional[float] = None) -> None:
        """Type text character by character.

        Args:
            text: Text to type.
            interval: Override default typing interval.

        Raises:
            ActionError: If typing fails.
        """
        try:
            pyautogui.typewrite(
                text,
                interval=interval or self.typing_interval,
            )
        except Exception as e:
            # Fallback: use write for unicode support
            try:
                pyautogui.write(text)
            except Exception:
                raise ActionError(f"Failed to type text: {e}") from e

    def type_unicode(self, text: str) -> None:
        """Type text with full Unicode support using keyboard module.

        Args:
            text: Unicode text to type.

        Raises:
            ActionError: If typing fails.
        """
        try:
            import keyboard as kb
            kb.write(text, delay=self.typing_interval)
        except ImportError:
            # Fallback to pyperclip + paste
            try:
                import subprocess
                process = subprocess.Popen(
                    ["clip.exe"],
                    stdin=subprocess.PIPE,
                )
                process.communicate(text.encode("utf-16-le"))
                pyautogui.hotkey("ctrl", "v")
            except Exception as e:
                raise ActionError(f"Failed to type unicode text: {e}") from e
        except Exception as e:
            raise ActionError(f"Failed to type unicode text: {e}") from e

    def press(self, key: str) -> None:
        """Press and release a single key.

        Args:
            key: Key name (e.g., 'enter', 'tab', 'escape', 'f1').

        Raises:
            ActionError: If key press fails.
        """
        try:
            pyautogui.press(key)
            time.sleep(0.1)  # Brief pause so user sees key effect
        except Exception as e:
            raise ActionError(f"Failed to press key '{key}': {e}") from e

    def hotkey(self, *keys: str) -> None:
        """Press a hotkey combination.

        Args:
            *keys: Key names to press simultaneously (e.g., 'ctrl', 's').

        Raises:
            ActionError: If hotkey fails.
        """
        try:
            pyautogui.hotkey(*keys, interval=0.08)
            time.sleep(0.15)  # Brief pause so user sees hotkey effect
        except Exception as e:
            raise ActionError(
                f"Failed to press hotkey {'+'.join(keys)}: {e}"
            ) from e

    def key_down(self, key: str) -> None:
        """Hold a key down (without releasing).

        Args:
            key: Key name to hold.
        """
        try:
            pyautogui.keyDown(key)
        except Exception as e:
            raise ActionError(f"Failed to hold key '{key}': {e}") from e

    def key_up(self, key: str) -> None:
        """Release a held key.

        Args:
            key: Key name to release.
        """
        try:
            pyautogui.keyUp(key)
        except Exception as e:
            raise ActionError(f"Failed to release key '{key}': {e}") from e

    def press_sequence(self, keys: list[str], delay: float = 0.1) -> None:
        """Press a sequence of keys with delays.

        Args:
            keys: List of key names to press in order.
            delay: Delay between each key press.
        """
        for key in keys:
            self.press(key)
            time.sleep(delay)
