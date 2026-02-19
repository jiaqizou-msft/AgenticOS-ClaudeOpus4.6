#!/usr/bin/env python3
"""AgenticOS Skill Library — Atomic, reusable, composable skills.

Each skill is a parameterized, self-contained unit of desktop automation
that can be composed into larger workflows. Skills know their preconditions
(expected UI state) and postconditions (expected result), enabling:

1. Amortized replay: cached action sequences skip LLM calls
2. Dynamic composition: natural language → skill chain
3. Staleness detection: re-plan when UI state has drifted
4. Cross-demo transfer: same skill reused across different scenarios

Usage:
    from skill_library import SKILLS, Skill, SkillParam
    skill = SKILLS["set_slider"]
    print(skill.prompt_template.format(name="Brightness", value=100))
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SkillParam:
    """A parameter for an atomic skill."""
    name: str
    description: str
    param_type: str = "str"      # str, int, float, bool
    required: bool = True
    default: Any = None
    examples: list[str] = field(default_factory=list)


@dataclass
class Skill:
    """An atomic, reusable skill for desktop automation.

    Skills are the building blocks of all automation workflows.
    They are small enough to succeed reliably (1-3 LLM steps)
    but composable enough to handle complex tasks.
    """
    id: str                          # Unique identifier, e.g. "open_quick_settings"
    name: str                        # Human-readable name
    description: str                 # What this skill does
    category: str                    # Category: system, browser, office, file, app
    parameters: list[SkillParam] = field(default_factory=list)
    prompt_template: str = ""        # LLM prompt (with {param} placeholders)
    pre_launch: str | None = None    # Shell command to set up state
    precondition: str = ""           # Expected UI state description
    postcondition: str = ""          # Expected result description
    max_steps: int = 3               # Maximum LLM steps allowed
    min_steps: int = 0                # Minimum actions before done is accepted
    timeout: int = 60                # Timeout in seconds
    tags: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)  # Skill IDs this depends on

    def format_prompt(self, **kwargs) -> str:
        """Format the prompt template with parameters.
        
        Auto-derives special formatted variables:
        - keys_formatted: Converts "ctrl+v" or "ctrl,v" → '"ctrl", "v"'
        """
        # Auto-derive keys_formatted for hotkey skills
        if "keys" in kwargs and "keys_formatted" not in kwargs:
            raw = str(kwargs["keys"])
            parts = [k.strip() for k in raw.replace("+", ",").split(",")]
            kwargs["keys_formatted"] = ", ".join(f'"{k}"' for k in parts)
        return self.prompt_template.format(**kwargs)

    def validate_params(self, params: dict) -> tuple[bool, str]:
        """Validate that all required parameters are provided."""
        for p in self.parameters:
            if p.required and p.name not in params:
                return False, f"Missing required parameter: {p.name}"
        return True, "OK"

    def to_catalog_entry(self) -> str:
        """Return a concise catalog entry for LLM skill selection."""
        param_str = ", ".join(
            f"{p.name}: {p.param_type}" + (f" (default={p.default})" if p.default else "")
            for p in self.parameters
        )
        return f"- {self.id}({param_str}): {self.description}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  SKILL DEFINITIONS — Atomic Skills Dictionary
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SKILLS: dict[str, Skill] = {}


def _register(skill: Skill) -> Skill:
    """Register a skill in the global dictionary."""
    SKILLS[skill.id] = skill
    return skill


# ── System Tray & Quick Settings ──────────────────────────────────────────

_register(Skill(
    id="open_quick_settings",
    name="Open Quick Settings",
    description="Open the Windows Quick Settings panel (brightness, volume, WiFi, Bluetooth)",
    category="system",
    prompt_template=(
        "Click on the system tray icons area at the very bottom-right corner of the "
        "taskbar (near the clock, battery, volume, WiFi icons) to open the Quick Settings flyout panel. "
        "Look for the notification area icons and click on them."
    ),
    precondition="Desktop or any window visible with taskbar at bottom",
    postcondition="Quick Settings panel is open showing WiFi, Bluetooth, brightness, volume controls",
    max_steps=2,
    timeout=30,
    tags=["system", "tray", "quick_settings"],
))

_register(Skill(
    id="close_panel",
    name="Close Current Panel/Flyout",
    description="Close any open panel, flyout, or popup by clicking outside or pressing Escape",
    category="system",
    prompt_template=(
        "Close the currently open panel or flyout. Press Escape key to dismiss it. "
        "If that doesn't work, click on an empty area of the desktop."
    ),
    precondition="A panel, flyout, or popup is open",
    postcondition="Panel is closed, desktop or previous window is visible",
    max_steps=2,
    timeout=30,
    tags=["system", "close", "dismiss"],
))

_register(Skill(
    id="set_slider",
    name="Set Slider Value",
    description="Set a slider control (brightness, volume, etc.) to a specific percentage value",
    category="system",
    parameters=[
        SkillParam("name", "Slider name (e.g., Brightness, Volume)", "str",
                   examples=["Brightness", "Volume"]),
        SkillParam("value", "Target value as percentage 0-100", "int",
                   examples=["100", "50", "0", "10"]),
    ],
    prompt_template=(
        'Use set_slider to set the {name} slider to {value}%. '
        'The action is: {{"type": "set_slider", "params": {{"name": "{name}", "value": {value}}}}}'
    ),
    precondition="A panel with slider controls is open (Quick Settings, Settings app, etc.)",
    postcondition="{name} slider is set to {value}%",
    max_steps=1,
    timeout=30,
    tags=["slider", "control", "value"],
))

_register(Skill(
    id="show_desktop",
    name="Show Desktop",
    description="Minimize all windows to show the desktop",
    category="system",
    prompt_template=(
        'Press Win+D to minimize all windows and show the desktop. '
        'The action is: {{"type": "hotkey", "params": {{"keys": ["win", "d"]}}}}'
    ),
    precondition="Any state",
    postcondition="Desktop is visible with all windows minimized",
    max_steps=1,
    timeout=10,
    tags=["system", "desktop", "minimize"],
))

# ── Application Launch ──────────────────────────────────────────────────

_register(Skill(
    id="open_app",
    name="Open Application",
    description="Launch a Windows application by name",
    category="app",
    parameters=[
        SkillParam("app_name", "Application name", "str",
                   examples=["notepad", "calculator", "mspaint", "cmd"]),
    ],
    prompt_template=(
        'Open the {app_name} application. '
        'The action is: {{"type": "open_app", "params": {{"app_name": "{app_name}"}}}}'
    ),
    precondition="Any state",
    postcondition="{app_name} window is open and focused",
    max_steps=2,
    timeout=15,
    tags=["app", "launch", "open"],
))

_register(Skill(
    id="open_settings_page",
    name="Open Settings Page",
    description="Open a specific Windows Settings page using ms-settings: URI",
    category="system",
    parameters=[
        SkillParam("uri", "Settings URI (e.g., ms-settings:display)", "str",
                   examples=["ms-settings:display", "ms-settings:nightlight",
                             "ms-settings:network-wifi", "ms-settings:defaultapps",
                             "ms-settings:powersleep", "ms-settings:about"]),
    ],
    prompt_template=(
        'Open the Windows Settings page: {uri}. '
        'The action is: {{"type": "shell", "params": {{"command": "start {uri}"}}}}'
    ),
    pre_launch="start {uri}",
    precondition="Any state",
    postcondition="Settings page for {uri} is open",
    max_steps=1,
    timeout=15,
    tags=["settings", "system", "launch"],
))

# ── Browser (Edge) ───────────────────────────────────────────────────────

_register(Skill(
    id="open_edge",
    name="Open Microsoft Edge",
    description="Launch Microsoft Edge browser, optionally in private mode",
    category="browser",
    parameters=[
        SkillParam("url", "URL to navigate to", "str", required=False, default="",
                   examples=["https://www.google.com", "https://www.youtube.com"]),
        SkillParam("private", "Open in InPrivate mode", "bool", required=False, default="false"),
    ],
    prompt_template=(
        'Open Microsoft Edge{_private_flag} and navigate to {url}. '
        'Wait for the page to fully load.'
    ),
    precondition="Any state",
    postcondition="Edge browser is open showing the target URL",
    max_steps=3,
    timeout=30,
    tags=["browser", "edge", "navigate"],
))

_register(Skill(
    id="navigate_url",
    name="Navigate to URL",
    description="Navigate to a URL in the currently open browser",
    category="browser",
    parameters=[
        SkillParam("url", "Target URL", "str",
                   examples=["https://www.google.com", "about:settings"]),
    ],
    prompt_template=(
        'Navigate to {url} in the browser. Press Ctrl+L to focus the address bar, '
        'then select all text with Ctrl+A, type the URL "{url}", and press Enter. '
        'Wait for the page to load.'
    ),
    precondition="Browser window is open and focused",
    postcondition="Browser is showing {url}",
    max_steps=3,
    timeout=30,
    tags=["browser", "navigate", "url"],
))

_register(Skill(
    id="browser_new_tab",
    name="Open New Browser Tab",
    description="Open a new tab in the current browser window",
    category="browser",
    prompt_template=(
        'Open a new browser tab. Press Ctrl+T. '
        'The action is: {{"type": "hotkey", "params": {{"keys": ["ctrl", "t"]}}}}'
    ),
    precondition="Browser window is focused",
    postcondition="New empty tab is open and focused",
    max_steps=1,
    timeout=10,
    tags=["browser", "tab"],
))

_register(Skill(
    id="browser_close_tab",
    name="Close Current Browser Tab",
    description="Close the currently active browser tab",
    category="browser",
    prompt_template=(
        'Close the current browser tab. Press Ctrl+W. '
        'The action is: {{"type": "hotkey", "params": {{"keys": ["ctrl", "w"]}}}}'
    ),
    precondition="Browser window is focused with at least one tab",
    postcondition="Current tab is closed",
    max_steps=1,
    timeout=10,
    tags=["browser", "tab", "close"],
))

# ── Text Input ───────────────────────────────────────────────────────────

_register(Skill(
    id="type_text",
    name="Type Text",
    description="Type text into the currently focused text field",
    category="input",
    parameters=[
        SkillParam("text", "Text to type", "str",
                   examples=["Hello World", "test@example.com"]),
    ],
    prompt_template=(
        'Type the following text: "{text}". '
        'The action is: {{"type": "type_text", "params": {{"text": "{text}"}}}}'
    ),
    precondition="A text input field is focused",
    postcondition="Text '{text}' has been typed",
    max_steps=1,
    timeout=10,
    tags=["input", "text", "type"],
))

_register(Skill(
    id="press_hotkey",
    name="Press Hotkey Combination",
    description="Press a keyboard shortcut (e.g., Ctrl+S, Ctrl+C, Alt+F4)",
    category="input",
    parameters=[
        SkillParam("keys", "Key combination as comma-separated list", "str",
                   examples=["ctrl,s", "ctrl,c", "ctrl,v", "alt,f4", "ctrl,a"]),
    ],
    prompt_template=(
        'Press the keyboard shortcut: {keys}. '
        'The action is: {{"type": "hotkey", "params": {{"keys": [{keys_formatted}]}}}}'
    ),
    precondition="Any window is focused",
    postcondition="Hotkey action has been performed",
    max_steps=1,
    timeout=10,
    tags=["input", "hotkey", "keyboard"],
))

_register(Skill(
    id="press_key",
    name="Press Single Key",
    description="Press a single key (Enter, Escape, Tab, F2, etc.)",
    category="input",
    parameters=[
        SkillParam("key", "Key to press", "str",
                   examples=["enter", "escape", "tab", "f2", "delete"]),
    ],
    prompt_template=(
        'Press the {key} key. '
        'The action is: {{"type": "press_key", "params": {{"key": "{key}"}}}}'
    ),
    precondition="Any window is focused",
    postcondition="{key} key has been pressed",
    max_steps=1,
    timeout=10,
    tags=["input", "key", "keyboard"],
))

# ── File Explorer ────────────────────────────────────────────────────────

_register(Skill(
    id="open_explorer",
    name="Open File Explorer",
    description="Open Windows File Explorer",
    category="file",
    prompt_template=(
        'Open File Explorer. Press Win+E. '
        'The action is: {{"type": "hotkey", "params": {{"keys": ["win", "e"]}}}}'
    ),
    precondition="Any state",
    postcondition="File Explorer window is open",
    max_steps=1,
    timeout=15,
    tags=["file", "explorer", "open"],
))

_register(Skill(
    id="create_folder",
    name="Create New Folder",
    description="Create a new folder in the current File Explorer location",
    category="file",
    parameters=[
        SkillParam("name", "Folder name", "str",
                   examples=["NewFolder", "TestFolder", "Documents"]),
    ],
    prompt_template=(
        'Create a new folder named "{name}". '
        'Press Ctrl+Shift+N to create a new folder, then type "{name}" and press Enter.'
    ),
    precondition="File Explorer is open and focused",
    postcondition="A new folder named '{name}' exists in the current directory",
    max_steps=3,
    timeout=20,
    tags=["file", "folder", "create"],
))

_register(Skill(
    id="rename_file",
    name="Rename File or Folder",
    description="Rename a selected file or folder",
    category="file",
    parameters=[
        SkillParam("old_name", "Current file/folder name to select", "str"),
        SkillParam("new_name", "New name for the file/folder", "str"),
    ],
    prompt_template=(
        'Rename "{old_name}" to "{new_name}". '
        'Click on "{old_name}" to select it, then press F2 to enter rename mode. '
        'Select all with Ctrl+A, type "{new_name}", and press Enter.'
    ),
    precondition="File Explorer is open showing a file/folder named '{old_name}'",
    postcondition="File/folder has been renamed to '{new_name}'",
    max_steps=3,
    timeout=20,
    tags=["file", "rename"],
))

# ── Notepad ──────────────────────────────────────────────────────────────

_register(Skill(
    id="open_notepad",
    name="Open Notepad",
    description="Launch a NEW Notepad instance via open_app (never click taskbar)",
    category="app",
    prompt_template=(
        'Launch a NEW Notepad window. '
        'IMPORTANT: Do NOT click the taskbar icon — that shows a picker when multiple windows exist. '
        'Instead use the open_app action which launches a fresh instance. '
        'The EXACT action is: {{"type": "open_app", "params": {{"app_name": "notepad"}}}}'
    ),
    precondition="Any state",
    postcondition="A new Notepad window is open and focused",
    max_steps=1,
    timeout=15,
    tags=["app", "notepad", "text"],
))

_register(Skill(
    id="notepad_new_tab",
    name="New Tab in Notepad",
    description="Create a new blank tab in Notepad (Ctrl+N) to avoid overwriting existing content",
    category="app",
    prompt_template=(
        'Create a new blank tab in Notepad by pressing Ctrl+N. '
        'The action is: {{"type": "hotkey", "params": {{"keys": ["ctrl", "n"]}}}}'
    ),
    precondition="Notepad is open and focused",
    postcondition="A new blank Untitled tab is active in Notepad",
    max_steps=1,
    timeout=10,
    tags=["notepad", "tab", "new"],
    depends_on=["open_notepad"],
))

_register(Skill(
    id="notepad_type",
    name="Type in Notepad",
    description="Type text in the Notepad editor area",
    category="app",
    parameters=[
        SkillParam("text", "Text to type in Notepad", "str"),
    ],
    prompt_template=(
        'Type the following text directly into Notepad (the text area already has focus): "{text}". '
        'Do NOT click anywhere first — just type immediately. '
        'The action is: {{"type": "type_text", "params": {{"text": "{text}"}}}}'
    ),
    precondition="Notepad is open and focused with cursor in text area",
    postcondition="Text '{text}' has been typed in Notepad",
    max_steps=1,
    timeout=15,
    tags=["notepad", "type", "text"],
    depends_on=["open_notepad"],
))

_register(Skill(
    id="notepad_select_all",
    name="Select All Text in Notepad",
    description="Select all text in Notepad using Ctrl+A",
    category="app",
    prompt_template=(
        'Select all text in Notepad. Press Ctrl+A. '
        'The action is: {{"type": "hotkey", "params": {{"keys": ["ctrl", "a"]}}}}'
    ),
    precondition="Notepad is open with some text",
    postcondition="All text in Notepad is selected",
    max_steps=1,
    timeout=10,
    tags=["notepad", "select"],
    depends_on=["open_notepad"],
))

_register(Skill(
    id="notepad_copy",
    name="Copy Selected Text",
    description="Copy currently selected text to clipboard using Ctrl+C",
    category="app",
    prompt_template=(
        'Copy the selected text. Press Ctrl+C. '
        'The action is: {{"type": "hotkey", "params": {{"keys": ["ctrl", "c"]}}}}'
    ),
    precondition="Text is selected in any application",
    postcondition="Selected text has been copied to clipboard",
    max_steps=1,
    timeout=10,
    tags=["clipboard", "copy"],
))

# ── Calculator ───────────────────────────────────────────────────────────

_register(Skill(
    id="open_calculator",
    name="Open Calculator",
    description="Launch Windows Calculator",
    category="app",
    prompt_template=(
        'Open Calculator. '
        'The action is: {{"type": "open_app", "params": {{"app_name": "calculator"}}}}'
    ),
    precondition="Any state",
    postcondition="Calculator window is open and focused",
    max_steps=1,
    timeout=15,
    tags=["app", "calculator"],
))

_register(Skill(
    id="calculator_compute",
    name="Compute Expression",
    description="Type and compute a mathematical expression in Calculator",
    category="app",
    parameters=[
        SkillParam("expression", "Math expression to compute", "str",
                   examples=["123+456", "7*8", "100/4"]),
    ],
    prompt_template=(
        'In Calculator, type the expression: {expression}. '
        'Then press Enter or = to compute the result.'
    ),
    precondition="Calculator is open and focused",
    postcondition="Calculator shows the result of {expression}",
    max_steps=3,
    timeout=20,
    tags=["calculator", "math", "compute"],
    depends_on=["open_calculator"],
))

# ── Window Management ────────────────────────────────────────────────────

_register(Skill(
    id="focus_window",
    name="Focus Window",
    description="Bring a specific window to the foreground",
    category="system",
    parameters=[
        SkillParam("title", "Window title (partial match)", "str",
                   examples=["Notepad", "Edge", "Settings", "Calculator"]),
    ],
    prompt_template=(
        'Bring the window titled "{title}" to the foreground. '
        'Click on its taskbar button or use Alt+Tab to find and focus it.'
    ),
    precondition="Window with title containing '{title}' exists",
    postcondition="Window '{title}' is focused and in the foreground",
    max_steps=2,
    timeout=15,
    tags=["window", "focus"],
))

_register(Skill(
    id="close_window",
    name="Close Current Window",
    description="Close the currently focused window",
    category="system",
    prompt_template=(
        'Close the current window. Press Alt+F4. '
        'The action is: {{"type": "hotkey", "params": {{"keys": ["alt", "f4"]}}}}'
    ),
    precondition="A window is focused",
    postcondition="The window has been closed",
    max_steps=1,
    timeout=10,
    tags=["window", "close"],
))

# ── Wait/Delay ───────────────────────────────────────────────────────────

_register(Skill(
    id="wait",
    name="Wait",
    description="Wait for a specified number of seconds",
    category="system",
    parameters=[
        SkillParam("seconds", "Seconds to wait", "float", required=False, default="2"),
    ],
    prompt_template=(
        'Wait for {seconds} seconds. '
        'The action is: {{"type": "wait", "params": {{"seconds": {seconds}}}}}'
    ),
    precondition="Any state",
    postcondition="Time has passed",
    max_steps=1,
    timeout=30,
    tags=["wait", "delay"],
))

# ── Click at UI Element ──────────────────────────────────────────────────

_register(Skill(
    id="click_element",
    name="Click UI Element",
    description="Click on a named UI element visible on screen",
    category="input",
    parameters=[
        SkillParam("element_name", "Name of the UI element to click", "str",
                   examples=["Start", "Search", "File", "Settings"]),
    ],
    prompt_template=(
        'Find and click on the UI element named "{element_name}". '
        'Look through the UI element tree for an element matching "{element_name}" '
        'and click on its center coordinates.'
    ),
    precondition="UI element '{element_name}' is visible on screen",
    postcondition="Element '{element_name}' has been clicked",
    max_steps=2,
    timeout=15,
    tags=["click", "element", "ui"],
))

_register(Skill(
    id="scroll_down",
    name="Scroll Down",
    description="Scroll down in the current window",
    category="input",
    parameters=[
        SkillParam("clicks", "Number of scroll clicks (positive=up, negative=down)", "int",
                   required=False, default="-3"),
    ],
    prompt_template=(
        'Scroll down in the current window. '
        'The action is: {{"type": "scroll", "params": {{"x": 960, "y": 540, "clicks": {clicks}}}}}'
    ),
    precondition="A scrollable window is focused",
    postcondition="Window content has scrolled",
    max_steps=1,
    timeout=10,
    tags=["scroll", "navigation"],
))


# ── Microsoft Teams ──────────────────────────────────────────────────────

_register(Skill(
    id="open_teams",
    name="Open Microsoft Teams",
    description="Bring Microsoft Teams to the foreground",
    category="app",
    prompt_template=(
        'Verify Microsoft Teams is in the foreground. '
        'If the window title contains "Microsoft Teams" or you can see Teams, '
        'the task is complete. Teams was just activated by a pre-launch command.'
    ),
    precondition="Any state",
    postcondition="Microsoft Teams window is in the foreground and focused",
    pre_launch='powershell -ExecutionPolicy Bypass -File scripts/activate_teams.ps1',
    max_steps=1,
    timeout=20,
    tags=["app", "teams", "communication"],
))

_register(Skill(
    id="teams_call_person",
    name="Call Someone in Teams",
    description="Start a Teams call to a person by name using Graph API + deep link",
    category="app",
    parameters=[
        SkillParam("name", "Person name to call", "str",
                   examples=["Miguel Huerta", "John Smith"]),
        SkillParam("call_type", "Type of call: audio or video", "str",
                   required=False, default="audio",
                   examples=["audio", "video"]),
    ],
    prompt_template=(
        'A Teams {call_type} call to {name} has been initiated via deep link. '
        'Verify that the call screen is visible — you should see the person\'s name '
        'and a ringing/calling indicator. If the call screen is showing, report success.'
    ),
    pre_launch='powershell -ExecutionPolicy Bypass -File scripts/teams_call.ps1 -Name "{name}" -CallType {call_type}',
    precondition="Any state — Teams should be running",
    postcondition="An {call_type} call to {name} is ringing",
    max_steps=2,
    timeout=30,
    tags=["teams", "call", "communication"],
))


# ── Task Manager ─────────────────────────────────────────────────────────

_register(Skill(
    id="open_task_manager",
    name="Open Task Manager",
    description="Open Windows Task Manager",
    category="system",
    prompt_template=(
        'Open Task Manager. Press Ctrl+Shift+Escape. '
        'The action is: {{"type": "hotkey", "params": {{"keys": ["ctrl", "shift", "escape"]}}}}'
    ),
    precondition="Any state",
    postcondition="Task Manager window is open",
    max_steps=1,
    timeout=15,
    tags=["system", "task_manager"],
))

# ── Shell Command ────────────────────────────────────────────────────────

_register(Skill(
    id="run_shell",
    name="Run Shell Command",
    description="Execute a shell command",
    category="system",
    parameters=[
        SkillParam("command", "Shell command to execute", "str",
                   examples=["echo Hello", "dir", "ipconfig"]),
    ],
    prompt_template=(
        'Run the shell command: {command}. '
        'The action is: {{"type": "shell", "params": {{"command": "{command}"}}}}'
    ),
    precondition="Any state",
    postcondition="Command has been executed",
    max_steps=1,
    timeout=30,
    tags=["shell", "command"],
))


def get_skill_catalog() -> str:
    """Return a formatted catalog of all available skills for LLM consumption."""
    lines = ["Available skills:"]
    categories: dict[str, list[Skill]] = {}
    for skill in SKILLS.values():
        categories.setdefault(skill.category, []).append(skill)

    for cat in sorted(categories):
        lines.append(f"\n## {cat.upper()}")
        for s in categories[cat]:
            lines.append(s.to_catalog_entry())
    return "\n".join(lines)


def get_skill_by_tag(tag: str) -> list[Skill]:
    """Find skills matching a tag."""
    return [s for s in SKILLS.values() if tag in s.tags]


def get_skills_by_category(category: str) -> list[Skill]:
    """Find skills in a category."""
    return [s for s in SKILLS.values() if s.category == category]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  COMMON RECIPES — pre-defined skill chains for frequent tasks
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class Recipe:
    """A pre-defined sequence of skills for a common task."""
    id: str
    name: str
    description: str
    skills: list[tuple[str, dict]]  # [(skill_id, params), ...]
    tags: list[str] = field(default_factory=list)


RECIPES: dict[str, Recipe] = {}


def _register_recipe(recipe: Recipe) -> Recipe:
    RECIPES[recipe.id] = recipe
    return recipe


_register_recipe(Recipe(
    id="set_brightness",
    name="Set Display Brightness",
    description="Open Quick Settings and set brightness to a specific value",
    skills=[
        ("open_quick_settings", {}),
        ("set_slider", {"name": "Brightness"}),  # value filled at runtime
        ("close_panel", {}),
    ],
    tags=["brightness", "display", "system"],
))

_register_recipe(Recipe(
    id="set_volume",
    name="Set System Volume",
    description="Open Quick Settings and set volume to a specific value",
    skills=[
        ("open_quick_settings", {}),
        ("set_slider", {"name": "Volume"}),  # value filled at runtime
        ("close_panel", {}),
    ],
    tags=["volume", "sound", "system"],
))

_register_recipe(Recipe(
    id="brightness_and_volume",
    name="Set Brightness and Volume",
    description="Open Quick Settings and set both brightness and volume",
    skills=[
        ("open_quick_settings", {}),
        ("set_slider", {"name": "Brightness"}),
        ("set_slider", {"name": "Volume"}),
        ("close_panel", {}),
    ],
    tags=["brightness", "volume", "system"],
))

_register_recipe(Recipe(
    id="notepad_hello_world",
    name="Open Notepad and Type Hello World",
    description="Launch Notepad, open a new tab, and type a message",
    skills=[
        ("open_notepad", {}),
        ("notepad_new_tab", {}),
        ("notepad_type", {"text": "Hello World"}),
    ],
    tags=["notepad", "text"],
))

_register_recipe(Recipe(
    id="notepad_select_copy",
    name="Select All and Copy in Notepad",
    description="Select all text in Notepad and copy to clipboard",
    skills=[
        ("notepad_select_all", {}),
        ("notepad_copy", {}),
    ],
    tags=["notepad", "clipboard"],
))

_register_recipe(Recipe(
    id="open_settings_about",
    name="Open Settings About Page",
    description="Open the Windows Settings About page",
    skills=[
        ("open_settings_page", {"uri": "ms-settings:about"}),
    ],
    tags=["settings"],
))

_register_recipe(Recipe(
    id="calculator_add",
    name="Calculator Addition",
    description="Open Calculator and compute an addition",
    skills=[
        ("open_calculator", {}),
        ("calculator_compute", {}),  # expression filled at runtime
    ],
    tags=["calculator", "math"],
))

_register_recipe(Recipe(
    id="teams_call",
    name="Call a Contact in Teams",
    description="Start a Teams call to a person by name (uses Graph API + deep link)",
    skills=[
        ("teams_call_person", {}),  # name and call_type filled at runtime
    ],
    tags=["teams", "call", "communication"],
))


if __name__ == "__main__":
    print(f"Skill Library: {len(SKILLS)} atomic skills, {len(RECIPES)} recipes\n")
    print(get_skill_catalog())
    print(f"\n\nRecipes:")
    for r in RECIPES.values():
        chain = " → ".join(f"{sid}({p})" for sid, p in r.skills)
        print(f"  {r.id}: {chain}")
