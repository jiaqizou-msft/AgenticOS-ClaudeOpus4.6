"""MCP Server exposing AgenticOS capabilities as tools.

Provides a FastMCP server that can be used by any MCP-compatible
host (Claude Desktop, VS Code, etc.) to control the Windows desktop.
"""

from __future__ import annotations

import asyncio
import base64
import json
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP

from agenticos.actions.compositor import Action, ActionCompositor
from agenticos.actions.shell import ShellExecutor
from agenticos.actions.window import WindowManager
from agenticos.grounding.accessibility import UIAGrounder
from agenticos.observation.screenshot import ScreenCapture


def create_mcp_server() -> FastMCP:
    """Create and configure the AgenticOS MCP server.

    Returns:
        Configured FastMCP server instance with all tools registered.
    """
    mcp = FastMCP(
        "AgenticOS",
        version="0.1.0",
        description="AI-powered Windows desktop automation via MCP",
    )

    # Shared instances
    screen = ScreenCapture()
    grounder = UIAGrounder()
    compositor = ActionCompositor()
    shell = ShellExecutor()
    window_mgr = WindowManager()

    # ── Screenshot Tool ──────────────────────────────────────────────

    @mcp.tool()
    def take_screenshot(
        monitor: int = 1,
        max_dimension: int = 1568,
    ) -> str:
        """Capture a screenshot of the current screen.

        Args:
            monitor: Monitor index (1 = primary).
            max_dimension: Max pixel dimension for the returned image.

        Returns:
            Base64-encoded PNG screenshot.
        """
        capture = ScreenCapture(monitor=monitor)
        screenshot = capture.grab()
        return screenshot.to_base64(max_dimension=max_dimension)

    # ── Click Tool ───────────────────────────────────────────────────

    @mcp.tool()
    def click(x: int, y: int, button: str = "left", clicks: int = 1) -> str:
        """Click at screen coordinates.

        Args:
            x: X pixel coordinate.
            y: Y pixel coordinate.
            button: Mouse button (left, right, middle).
            clicks: Number of clicks (2 for double-click).

        Returns:
            Success message.
        """
        action = Action.click(x, y, f"Click at ({x}, {y})")
        if clicks == 2:
            action = Action.double_click(x, y, f"Double-click at ({x}, {y})")
        elif button == "right":
            action = Action.right_click(x, y, f"Right-click at ({x}, {y})")

        result = compositor.execute(action)
        if result.success:
            return f"Clicked at ({x}, {y}) successfully"
        return f"Click failed: {result.error}"

    # ── Type Text Tool ───────────────────────────────────────────────

    @mcp.tool()
    def type_text(text: str) -> str:
        """Type text into the currently focused element.

        Args:
            text: Text to type.

        Returns:
            Success message.
        """
        action = Action.type_text(text, f"Type: {text[:50]}")
        result = compositor.execute(action)
        if result.success:
            return f"Typed '{text[:50]}' successfully"
        return f"Typing failed: {result.error}"

    # ── Press Key Tool ───────────────────────────────────────────────

    @mcp.tool()
    def press_key(key: str) -> str:
        """Press a keyboard key.

        Args:
            key: Key name (e.g., 'enter', 'tab', 'escape', 'f1', 'delete').

        Returns:
            Success message.
        """
        action = Action.press_key(key, f"Press {key}")
        result = compositor.execute(action)
        if result.success:
            return f"Pressed '{key}' successfully"
        return f"Key press failed: {result.error}"

    # ── Hotkey Tool ──────────────────────────────────────────────────

    @mcp.tool()
    def hotkey(keys: str) -> str:
        """Press a hotkey combination.

        Args:
            keys: Comma-separated key names (e.g., 'ctrl,s' or 'alt,f4').

        Returns:
            Success message.
        """
        key_list = [k.strip() for k in keys.split(",")]
        action = Action.hotkey(*key_list, description=f"Hotkey: {'+'.join(key_list)}")
        result = compositor.execute(action)
        if result.success:
            return f"Pressed {'+'.join(key_list)} successfully"
        return f"Hotkey failed: {result.error}"

    # ── Scroll Tool ──────────────────────────────────────────────────

    @mcp.tool()
    def scroll(x: int, y: int, direction: str = "down", amount: int = 3) -> str:
        """Scroll at a specific position.

        Args:
            x: X coordinate to scroll at.
            y: Y coordinate to scroll at.
            direction: Scroll direction ('up' or 'down').
            amount: Number of scroll clicks.

        Returns:
            Success message.
        """
        clicks = -amount if direction == "down" else amount
        action = Action.scroll(x, y, clicks, f"Scroll {direction} at ({x}, {y})")
        result = compositor.execute(action)
        if result.success:
            return f"Scrolled {direction} at ({x}, {y})"
        return f"Scroll failed: {result.error}"

    # ── Get UI Tree Tool ─────────────────────────────────────────────

    @mcp.tool()
    def get_ui_tree(window_title: Optional[str] = None) -> str:
        """Get the accessibility tree of UI elements on screen.

        Args:
            window_title: Optional window to scope to (partial match).

        Returns:
            JSON array of detected UI elements with names, types, and coordinates.
        """
        elements = grounder.detect(window_title=window_title)
        return json.dumps([e.to_dict() for e in elements], indent=2)

    # ── Run Shell Command Tool ───────────────────────────────────────

    @mcp.tool()
    def run_shell(command: str, shell_type: str = "powershell") -> str:
        """Execute a shell command.

        Args:
            command: Command to execute.
            shell_type: Shell to use ('powershell' or 'cmd').

        Returns:
            Command output.
        """
        result = shell.run(command, shell=shell_type)
        return f"Exit code: {result.return_code}\n{result.output}"

    # ── Open Application Tool ────────────────────────────────────────

    @mcp.tool()
    def open_app(app_name: str) -> str:
        """Open an application by name.

        Args:
            app_name: Application name or path (e.g., 'notepad', 'calc', 'explorer').

        Returns:
            Success message.
        """
        result = shell.open_application(app_name)
        if result.success:
            return f"Opened '{app_name}' successfully"
        return f"Failed to open '{app_name}': {result.output}"

    # ── List Windows Tool ────────────────────────────────────────────

    @mcp.tool()
    def list_windows() -> str:
        """List all visible windows.

        Returns:
            JSON array of window information.
        """
        windows = window_mgr.list_windows()
        data = [
            {
                "title": w.title,
                "pid": w.pid,
                "bbox": list(w.bbox),
                "is_minimized": w.is_minimized,
            }
            for w in windows
            if w.title  # Only include windows with titles
        ]
        return json.dumps(data, indent=2)

    # ── Focus Window Tool ────────────────────────────────────────────

    @mcp.tool()
    def focus_window(title: str) -> str:
        """Bring a window to the foreground.

        Args:
            title: Window title (partial match supported).

        Returns:
            Success message.
        """
        try:
            window_mgr.focus(title)
            return f"Focused window matching '{title}'"
        except Exception as e:
            return f"Failed to focus window: {e}"

    # ── Get Screen Text Tool ─────────────────────────────────────────

    @mcp.tool()
    def get_screen_text() -> str:
        """Extract all visible text from the current screen using OCR.

        Returns:
            All detected text from the screen.
        """
        try:
            from agenticos.grounding.ocr import OCRGrounder
            ocr = OCRGrounder()
            screenshot = screen.grab()
            return ocr.get_all_text(screenshot)
        except Exception as e:
            return f"OCR failed: {e}"

    return mcp


def run_server(transport: str = "stdio") -> None:
    """Run the MCP server.

    Args:
        transport: Transport protocol ('stdio' or 'streamable-http').
    """
    server = create_mcp_server()
    server.run(transport=transport)


if __name__ == "__main__":
    run_server()
