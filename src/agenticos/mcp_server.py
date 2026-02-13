#!/usr/bin/env python3
"""AgenticOS MCP Server — expose all OS automation tools to VS Code Copilot Chat.

This server implements the Model Context Protocol (MCP) and registers
every AgenticOS capability as a callable tool:

  - screenshot: capture and return a screenshot
  - click/type/press_key/hotkey: direct input actions
  - detect_elements: UIA accessibility tree scan
  - open_app/shell: launch apps and run commands
  - run_task: full agent loop for a natural-language task
  - record_demo: run a task with GIF recording
  - get_memory_stats: inspect the step memory cache

Usage:
    python src/agenticos/mcp_server.py
    # Then configure in .vscode/mcp.json
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import signal
import sys
import time
import threading
from pathlib import Path

# Add src to path
ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent, ImageContent

# Lazy-init singletons
_screen = None
_grounder = None
_compositor = None
_memory = None


def _get_screen():
    global _screen
    if _screen is None:
        from agenticos.observation.screenshot import ScreenCapture
        _screen = ScreenCapture(monitor=1, scale=1.0)
    return _screen


def _get_grounder():
    global _grounder
    if _grounder is None:
        from agenticos.grounding.accessibility import UIAGrounder
        _grounder = UIAGrounder()
    return _grounder


def _get_compositor():
    global _compositor
    if _compositor is None:
        from agenticos.actions.compositor import ActionCompositor
        _compositor = ActionCompositor()
    return _compositor


def _get_memory():
    global _memory
    if _memory is None:
        from agenticos.agent.step_memory import StepMemory
        _memory = StepMemory(
            persist_path=str(ROOT / "recordings" / "step_memory.json")
        )
    return _memory


def _detect_with_timeout(timeout: float = 12.0) -> list:
    """Run UIA detection with a timeout to avoid hangs."""
    elements = []
    done = threading.Event()

    def _detect():
        nonlocal elements
        try:
            elements = _get_grounder().detect()
        except Exception:
            elements = []
        done.set()

    t = threading.Thread(target=_detect, daemon=True)
    t.start()
    done.wait(timeout=timeout)
    return elements


# ─────────────────────────────────────────────────────────────────
# MCP Server Setup
# ─────────────────────────────────────────────────────────────────

app = Server("agenticos")


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="screenshot",
            description="Capture a screenshot of the current screen. Returns a base64-encoded PNG image.",
            inputSchema={
                "type": "object",
                "properties": {
                    "max_dimension": {
                        "type": "integer",
                        "description": "Max pixel dimension (default 1568)",
                        "default": 1568,
                    }
                },
            },
        ),
        Tool(
            name="detect_elements",
            description="Detect all interactive UI elements on screen using Windows UI Automation. Returns element names, types, and coordinates.",
            inputSchema={
                "type": "object",
                "properties": {
                    "window_title": {
                        "type": "string",
                        "description": "Optional: only detect elements in this window",
                    },
                    "max_elements": {
                        "type": "integer",
                        "description": "Maximum elements to return (default 50)",
                        "default": 50,
                    },
                },
            },
        ),
        Tool(
            name="click",
            description="Click at screen coordinates (x, y).",
            inputSchema={
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "description": "X coordinate"},
                    "y": {"type": "integer", "description": "Y coordinate"},
                },
                "required": ["x", "y"],
            },
        ),
        Tool(
            name="double_click",
            description="Double-click at screen coordinates (x, y).",
            inputSchema={
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "description": "X coordinate"},
                    "y": {"type": "integer", "description": "Y coordinate"},
                },
                "required": ["x", "y"],
            },
        ),
        Tool(
            name="right_click",
            description="Right-click at screen coordinates (x, y).",
            inputSchema={
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "description": "X coordinate"},
                    "y": {"type": "integer", "description": "Y coordinate"},
                },
                "required": ["x", "y"],
            },
        ),
        Tool(
            name="type_text",
            description="Type text at the current cursor position. Supports Unicode.",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to type"},
                },
                "required": ["text"],
            },
        ),
        Tool(
            name="press_key",
            description="Press a keyboard key (enter, tab, escape, f1, etc.).",
            inputSchema={
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Key name to press"},
                },
                "required": ["key"],
            },
        ),
        Tool(
            name="hotkey",
            description="Press a keyboard shortcut (e.g. ctrl+c, alt+tab).",
            inputSchema={
                "type": "object",
                "properties": {
                    "keys": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Keys to press simultaneously, e.g. ['ctrl', 'c']",
                    },
                },
                "required": ["keys"],
            },
        ),
        Tool(
            name="scroll",
            description="Scroll the mouse wheel at a position.",
            inputSchema={
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "description": "X coordinate"},
                    "y": {"type": "integer", "description": "Y coordinate"},
                    "clicks": {"type": "integer", "description": "Scroll clicks (negative=down, positive=up)", "default": -3},
                },
                "required": ["x", "y"],
            },
        ),
        Tool(
            name="open_app",
            description="Open a Windows application by name (e.g. 'notepad', 'msedge', 'outlook').",
            inputSchema={
                "type": "object",
                "properties": {
                    "app_name": {"type": "string", "description": "Application name to launch"},
                },
                "required": ["app_name"],
            },
        ),
        Tool(
            name="shell",
            description="Run a PowerShell command and return the output.",
            inputSchema={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "PowerShell command to run"},
                    "timeout": {"type": "integer", "description": "Timeout in seconds (default 30)", "default": 30},
                },
                "required": ["command"],
            },
        ),
        Tool(
            name="focus_window",
            description="Bring a window to the foreground by title.",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Window title (partial match)"},
                },
                "required": ["title"],
            },
        ),
        Tool(
            name="list_windows",
            description="List all visible windows with their titles, handles, and positions.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="run_task",
            description="Run a full agent loop for a natural-language task. The agent will observe the screen, think, and act until the task is done.",
            inputSchema={
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "Natural language description of the task"},
                    "max_steps": {"type": "integer", "description": "Maximum steps (default 15)", "default": 15},
                },
                "required": ["task"],
            },
        ),
        Tool(
            name="record_demo",
            description="Run a task with GIF recording. Returns the path to the saved GIF.",
            inputSchema={
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "Task description"},
                    "output": {"type": "string", "description": "Output GIF path (default recordings/demo.gif)", "default": "recordings/demo.gif"},
                    "max_steps": {"type": "integer", "description": "Max steps (default 15)", "default": 15},
                },
                "required": ["task"],
            },
        ),
        Tool(
            name="get_memory_stats",
            description="Get statistics about the step memory cache (hits, misses, stored episodes).",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="go_back",
            description="Attempt to go back to the previous UI state using common patterns (Escape, Alt+Left, etc.).",
            inputSchema={
                "type": "object",
                "properties": {
                    "strategy": {
                        "type": "string",
                        "description": "Recovery strategy: escape, alt_left, alt_f4, ctrl_z, ctrl_w",
                        "default": "escape",
                    },
                },
            },
        ),
        Tool(
            name="drag",
            description="Drag from one position to another (for sliders, etc.).",
            inputSchema={
                "type": "object",
                "properties": {
                    "start_x": {"type": "integer"},
                    "start_y": {"type": "integer"},
                    "end_x": {"type": "integer"},
                    "end_y": {"type": "integer"},
                },
                "required": ["start_x", "start_y", "end_x", "end_y"],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent | ImageContent]:
    try:
        match name:
            # ── Observation tools ──
            case "screenshot":
                scr = _get_screen()
                shot = scr.grab()
                max_dim = arguments.get("max_dimension", 1568)
                b64 = shot.to_base64(max_dimension=max_dim)
                return [
                    TextContent(type="text", text=f"Screenshot: {shot.width}x{shot.height}"),
                    ImageContent(type="image", data=b64, mimeType="image/png"),
                ]

            case "detect_elements":
                elements = _detect_with_timeout(timeout=12.0)
                max_el = arguments.get("max_elements", 50)
                descs = [el.description() for el in elements[:max_el]]
                if len(elements) > max_el:
                    descs.append(f"... ({len(elements) - max_el} more)")
                return [TextContent(type="text", text=f"Detected {len(elements)} elements:\n" + "\n".join(descs))]

            # ── Input action tools ──
            case "click":
                ok, msg = execute_action_mcp("click", arguments)
                return [TextContent(type="text", text=msg)]

            case "double_click":
                ok, msg = execute_action_mcp("double_click", arguments)
                return [TextContent(type="text", text=msg)]

            case "right_click":
                ok, msg = execute_action_mcp("right_click", arguments)
                return [TextContent(type="text", text=msg)]

            case "type_text":
                ok, msg = execute_action_mcp("type_text", arguments)
                return [TextContent(type="text", text=msg)]

            case "press_key":
                ok, msg = execute_action_mcp("press_key", arguments)
                return [TextContent(type="text", text=msg)]

            case "hotkey":
                ok, msg = execute_action_mcp("hotkey", arguments)
                return [TextContent(type="text", text=msg)]

            case "scroll":
                ok, msg = execute_action_mcp("scroll", arguments)
                return [TextContent(type="text", text=msg)]

            case "drag":
                ok, msg = execute_action_mcp("drag", arguments)
                return [TextContent(type="text", text=msg)]

            # ── App/Window tools ──
            case "open_app":
                ok, msg = execute_action_mcp("open_app", arguments)
                await asyncio.sleep(1.5)
                return [TextContent(type="text", text=msg)]

            case "shell":
                from agenticos.actions.shell import ShellExecutor
                shell = ShellExecutor()
                result = shell.run(
                    arguments["command"],
                    timeout=arguments.get("timeout", 30),
                )
                return [TextContent(type="text", text=f"Exit {result.return_code}:\n{result.output}")]

            case "focus_window":
                from agenticos.actions.window import WindowManager
                wm = WindowManager()
                wm.focus(arguments["title"])
                return [TextContent(type="text", text=f"Focused window matching '{arguments['title']}'")]

            case "list_windows":
                from agenticos.actions.window import WindowManager
                wm = WindowManager()
                windows = wm.list_windows()
                lines = [f"  {w.title} (pid={w.pid}, handle={w.handle})" for w in windows[:30]]
                return [TextContent(type="text", text=f"{len(windows)} windows:\n" + "\n".join(lines))]

            # ── Recovery ──
            case "go_back":
                strategy = arguments.get("strategy", "escape")
                STRATEGY_ACTIONS = {
                    "escape": ("press_key", {"key": "escape"}),
                    "alt_left": ("hotkey", {"keys": ["alt", "left"]}),
                    "alt_f4": ("hotkey", {"keys": ["alt", "F4"]}),
                    "ctrl_z": ("hotkey", {"keys": ["ctrl", "z"]}),
                    "ctrl_w": ("hotkey", {"keys": ["ctrl", "w"]}),
                }
                act_type, act_params = STRATEGY_ACTIONS.get(strategy, ("press_key", {"key": "escape"}))
                ok, msg = execute_action_mcp(act_type, act_params)
                return [TextContent(type="text", text=f"Recovery ({strategy}): {msg}")]

            # ── Memory ──
            case "get_memory_stats":
                mem = _get_memory()
                return [TextContent(type="text", text=json.dumps(mem.stats, indent=2))]

            # ── Agent loop ──
            case "run_task":
                result = await _run_agent_task(
                    task=arguments["task"],
                    max_steps=arguments.get("max_steps", 15),
                )
                return [TextContent(type="text", text=result)]

            case "record_demo":
                result = await _run_agent_task(
                    task=arguments["task"],
                    max_steps=arguments.get("max_steps", 15),
                    record_gif=arguments.get("output", "recordings/demo.gif"),
                )
                return [TextContent(type="text", text=result)]

            case _:
                return [TextContent(type="text", text=f"Unknown tool: {name}")]

    except Exception as e:
        return [TextContent(type="text", text=f"Error: {e}")]


def execute_action_mcp(action_type: str, params: dict) -> tuple[bool, str]:
    """Execute an action via the compositor."""
    from agenticos.actions.compositor import Action, ActionType
    try:
        action = Action(type=ActionType(action_type), params=params)
        result = _get_compositor().execute(action)
        if result.success:
            return True, f"OK: {action_type} executed"
        return False, f"Failed: {result.error}"
    except Exception as e:
        return False, f"Error: {e}"


async def _run_agent_task(
    task: str,
    max_steps: int = 15,
    record_gif: str | None = None,
) -> str:
    """Run the full agent observe-think-act loop."""
    import re
    import litellm
    from agenticos.agent.state_validator import StateValidator
    from agenticos.agent.recovery import RecoveryManager
    from agenticos.observation.recorder import GifRecorder

    # Get Azure AD token
    token = os.environ.get("AZURE_AD_TOKEN", "")
    if not token:
        try:
            from azure.identity import DefaultAzureCredential
            cred = DefaultAzureCredential()
            token = cred.get_token("https://cognitiveservices.azure.com/.default").token
        except Exception as e:
            return f"Error getting Azure AD token: {e}"

    validator = StateValidator()
    recovery_mgr = RecoveryManager()
    memory = _get_memory()
    compositor = _get_compositor()
    screen = _get_screen()
    grounder = _get_grounder()

    recorder = None
    if record_gif:
        recorder = GifRecorder(fps=5, max_duration=180)
        recorder.start()

    log_lines = [f"Task: {task}"]
    steps = []
    success = False

    PROMPT = (
        "You are AgenticOS. Respond with ONLY a JSON object:\n"
        '{"thought": "...", "action": {"type": "<type>", "params": {...}}}\n'
        "Types: click, type_text, press_key, hotkey, open_app, scroll, wait, shell, done"
    )

    for step_num in range(1, max_steps + 1):
        # Observe
        try:
            shot = screen.grab()
            b64 = shot.to_base64()
        except Exception as e:
            log_lines.append(f"Step {step_num}: Screenshot error: {e}")
            break

        elements = _detect_with_timeout(timeout=10.0)
        elem_text = "\n".join(el.description() for el in elements[:40])

        # LLM
        messages = [
            {"role": "system", "content": PROMPT},
            {"role": "user", "content": [
                {"type": "text", "text": f"Task: {task}\n\nUI Elements:\n{elem_text}\n\nNext action?"},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
            ]},
        ]

        try:
            resp = litellm.completion(
                model="azure/gpt-4o",
                messages=messages,
                max_tokens=2048,
                temperature=0.1,
                azure_ad_token=token,
                api_base="https://bugtotest-resource.cognitiveservices.azure.com/",
                api_version="2024-12-01-preview",
            )
            content = resp.choices[0].message.content
        except Exception as e:
            log_lines.append(f"Step {step_num}: LLM error: {e}")
            break

        # Parse
        try:
            m = re.search(r'\{.*"action".*\}', content, re.DOTALL)
            parsed = json.loads(m.group()) if m else json.loads(content)
            act = parsed.get("action", {})
            thought = parsed.get("thought", "")
            action_type = act.get("type", "done")
            params = act.get("params", {})
        except Exception:
            log_lines.append(f"Step {step_num}: Parse error")
            continue

        log_lines.append(f"Step {step_num}: [{action_type}] {thought[:80]}")

        if action_type == "done":
            success = params.get("success", True)
            break

        # Execute
        TYPE_MAP = {"type": "type_text", "key_press": "press_key", "key": "press_key", "open": "open_app"}
        mapped = TYPE_MAP.get(action_type, action_type)
        execute_action_mcp(mapped, params)
        await asyncio.sleep(1.0)

        if recorder:
            try:
                recorder.add_annotation(f"Step {step_num}: {action_type}")
            except Exception:
                pass

    # Save GIF
    gif_msg = ""
    if recorder:
        recorder.stop()
        try:
            gif_path = recorder.save(str(ROOT / record_gif))
            gif_msg = f"\nGIF saved: {gif_path}"
        except Exception as e:
            gif_msg = f"\nGIF error: {e}"

    status = "SUCCESS" if success else "INCOMPLETE"
    return f"{status} ({len(steps)} steps)\n" + "\n".join(log_lines) + gif_msg


async def main():
    """Run the MCP server over stdio."""
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
