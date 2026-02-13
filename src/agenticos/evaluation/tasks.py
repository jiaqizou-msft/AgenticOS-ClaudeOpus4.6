"""Benchmark task definitions and suite management.

Defines the task format and provides built-in benchmark suites
for evaluating AgenticOS performance.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional


@dataclass
class BenchmarkTask:
    """A single benchmark task for evaluation.

    Attributes:
        task_id: Unique identifier (e.g., 'basic_001').
        name: Human-readable task name.
        description: Natural language task instruction (what the agent receives).
        category: Task category (basic, intermediate, advanced).
        domain: Application domain (notepad, explorer, calculator, etc.).
        optimal_steps: Known optimal number of steps.
        max_steps: Maximum allowed steps for this task.
        setup_commands: Shell commands to run before the task.
        cleanup_commands: Shell commands to run after the task.
        verification: How to verify task completion.
        verification_func: Optional programmatic verification function.
        tags: Additional tags for filtering.
    """
    task_id: str
    name: str
    description: str
    category: str = "basic"
    domain: str = "general"
    optimal_steps: int = 3
    max_steps: int = 15
    setup_commands: list[str] = field(default_factory=list)
    cleanup_commands: list[str] = field(default_factory=list)
    verification: str = ""
    verification_func: Optional[Callable[[], bool]] = field(default=None, repr=False)
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary (excluding callables)."""
        return {
            "task_id": self.task_id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "domain": self.domain,
            "optimal_steps": self.optimal_steps,
            "max_steps": self.max_steps,
            "setup_commands": self.setup_commands,
            "cleanup_commands": self.cleanup_commands,
            "verification": self.verification,
            "tags": self.tags,
        }


@dataclass
class BenchmarkSuite:
    """A collection of benchmark tasks.

    Provides built-in task suites (basic, intermediate, advanced) and
    supports loading custom tasks from JSON files.

    Example:
        >>> suite = BenchmarkSuite.builtin_basic()
        >>> print(f"{len(suite.tasks)} tasks in {suite.name}")
        >>> for task in suite.tasks:
        ...     print(f"  {task.task_id}: {task.name}")
    """
    name: str
    description: str
    tasks: list[BenchmarkTask] = field(default_factory=list)

    def filter_by_category(self, category: str) -> list[BenchmarkTask]:
        """Filter tasks by category."""
        return [t for t in self.tasks if t.category == category]

    def filter_by_domain(self, domain: str) -> list[BenchmarkTask]:
        """Filter tasks by application domain."""
        return [t for t in self.tasks if t.domain == domain]

    def save_json(self, path: str) -> str:
        """Save suite to JSON file."""
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "name": self.name,
            "description": self.description,
            "tasks": [t.to_dict() for t in self.tasks],
        }
        with open(output, "w") as f:
            json.dump(data, f, indent=2)
        return str(output)

    @classmethod
    def from_json(cls, path: str) -> "BenchmarkSuite":
        """Load suite from JSON file."""
        with open(path) as f:
            data = json.load(f)

        tasks = [
            BenchmarkTask(**{k: v for k, v in t.items() if k != "verification_func"})
            for t in data.get("tasks", [])
        ]

        return cls(
            name=data.get("name", "Custom"),
            description=data.get("description", ""),
            tasks=tasks,
        )

    # ── Built-in Suites ──────────────────────────────────────────────

    @classmethod
    def builtin_basic(cls) -> "BenchmarkSuite":
        """Basic single-app tasks (15 tasks)."""
        tasks = [
            BenchmarkTask(
                task_id="basic_001",
                name="Open Notepad",
                description="Open the Notepad application.",
                category="basic",
                domain="notepad",
                optimal_steps=1,
                cleanup_commands=["taskkill /im notepad.exe /f 2>$null"],
                verification="Notepad window is visible",
            ),
            BenchmarkTask(
                task_id="basic_002",
                name="Type in Notepad",
                description="Open Notepad and type 'Hello AgenticOS'.",
                category="basic",
                domain="notepad",
                optimal_steps=2,
                cleanup_commands=["taskkill /im notepad.exe /f 2>$null"],
                verification="Text 'Hello AgenticOS' appears in Notepad",
            ),
            BenchmarkTask(
                task_id="basic_003",
                name="Save file in Notepad",
                description="Open Notepad, type 'Test content', and save as 'agenticos_test.txt' on the Desktop.",
                category="basic",
                domain="notepad",
                optimal_steps=5,
                cleanup_commands=[
                    "taskkill /im notepad.exe /f 2>$null",
                    "Remove-Item $env:USERPROFILE\\Desktop\\agenticos_test.txt -Force 2>$null",
                ],
                verification="File agenticos_test.txt exists on Desktop with content 'Test content'",
            ),
            BenchmarkTask(
                task_id="basic_004",
                name="Open Calculator",
                description="Open the Windows Calculator application.",
                category="basic",
                domain="calculator",
                optimal_steps=1,
                cleanup_commands=["taskkill /im CalculatorApp.exe /f 2>$null"],
                verification="Calculator window is visible",
            ),
            BenchmarkTask(
                task_id="basic_005",
                name="Calculate sum",
                description="Open Calculator and compute 42 + 58.",
                category="basic",
                domain="calculator",
                optimal_steps=4,
                cleanup_commands=["taskkill /im CalculatorApp.exe /f 2>$null"],
                verification="Calculator shows result 100",
            ),
            BenchmarkTask(
                task_id="basic_006",
                name="Open File Explorer",
                description="Open File Explorer.",
                category="basic",
                domain="explorer",
                optimal_steps=1,
                cleanup_commands=["taskkill /im explorer.exe /f 2>$null; Start-Process explorer.exe"],
                verification="File Explorer window is visible",
            ),
            BenchmarkTask(
                task_id="basic_007",
                name="Navigate to Documents",
                description="Open File Explorer and navigate to the Documents folder.",
                category="basic",
                domain="explorer",
                optimal_steps=2,
                verification="File Explorer shows Documents folder",
            ),
            BenchmarkTask(
                task_id="basic_008",
                name="Open Settings",
                description="Open Windows Settings.",
                category="basic",
                domain="settings",
                optimal_steps=1,
                cleanup_commands=["taskkill /im SystemSettings.exe /f 2>$null"],
                verification="Settings window is visible",
            ),
            BenchmarkTask(
                task_id="basic_009",
                name="Open Paint",
                description="Open the Paint application.",
                category="basic",
                domain="paint",
                optimal_steps=1,
                cleanup_commands=["taskkill /im mspaint.exe /f 2>$null"],
                verification="Paint window is visible",
            ),
            BenchmarkTask(
                task_id="basic_010",
                name="Create Desktop folder",
                description="Create a new folder named 'AgenticOS_Test' on the Desktop using File Explorer.",
                category="basic",
                domain="explorer",
                optimal_steps=4,
                cleanup_commands=[
                    "Remove-Item $env:USERPROFILE\\Desktop\\AgenticOS_Test -Force -Recurse 2>$null"
                ],
                verification="Folder 'AgenticOS_Test' exists on Desktop",
            ),
            BenchmarkTask(
                task_id="basic_011",
                name="Maximize window",
                description="Open Notepad and maximize its window.",
                category="basic",
                domain="notepad",
                optimal_steps=2,
                cleanup_commands=["taskkill /im notepad.exe /f 2>$null"],
                verification="Notepad window is maximized",
            ),
            BenchmarkTask(
                task_id="basic_012",
                name="Use search",
                description="Open Windows search and search for 'notepad'.",
                category="basic",
                domain="system",
                optimal_steps=2,
                verification="Search results show Notepad",
            ),
            BenchmarkTask(
                task_id="basic_013",
                name="Close application",
                description="Open Notepad and then close it.",
                category="basic",
                domain="notepad",
                optimal_steps=2,
                verification="Notepad is no longer running",
            ),
            BenchmarkTask(
                task_id="basic_014",
                name="Check system info",
                description="Open Settings and navigate to the 'About' page to see system information.",
                category="basic",
                domain="settings",
                optimal_steps=3,
                cleanup_commands=["taskkill /im SystemSettings.exe /f 2>$null"],
                verification="About page is displayed in Settings",
            ),
            BenchmarkTask(
                task_id="basic_015",
                name="Run PowerShell command",
                description="Open PowerShell and run the command 'Get-Date' to display the current date.",
                category="basic",
                domain="shell",
                optimal_steps=2,
                verification="Current date is displayed in PowerShell",
            ),
        ]

        return cls(
            name="AgenticOS Basic",
            description="15 single-application tasks testing fundamental OS navigation",
            tasks=tasks,
        )

    @classmethod
    def builtin_intermediate(cls) -> "BenchmarkSuite":
        """Intermediate multi-app tasks (10 tasks)."""
        tasks = [
            BenchmarkTask(
                task_id="inter_001",
                name="Copy text between apps",
                description="Open Notepad, type 'Cross-app test', select all text, copy it, open WordPad, and paste the text.",
                category="intermediate",
                domain="multi-app",
                optimal_steps=7,
                cleanup_commands=[
                    "taskkill /im notepad.exe /f 2>$null",
                    "taskkill /im wordpad.exe /f 2>$null",
                ],
            ),
            BenchmarkTask(
                task_id="inter_002",
                name="Create and organize files",
                description="Create a folder 'Reports' on Desktop, create two text files inside it named 'report1.txt' and 'report2.txt' with content 'Report 1' and 'Report 2' respectively.",
                category="intermediate",
                domain="explorer",
                optimal_steps=10,
                cleanup_commands=[
                    "Remove-Item $env:USERPROFILE\\Desktop\\Reports -Force -Recurse 2>$null"
                ],
            ),
            BenchmarkTask(
                task_id="inter_003",
                name="Screenshot and save",
                description="Take a screenshot of the desktop and save it as 'screenshot.png' on the Desktop using the Snipping Tool.",
                category="intermediate",
                domain="snipping",
                optimal_steps=4,
                cleanup_commands=[
                    "Remove-Item $env:USERPROFILE\\Desktop\\screenshot.png -Force 2>$null"
                ],
            ),
            BenchmarkTask(
                task_id="inter_004",
                name="Navigate settings deeply",
                description="Open Settings, navigate to System > Display and check the current screen resolution.",
                category="intermediate",
                domain="settings",
                optimal_steps=4,
                cleanup_commands=["taskkill /im SystemSettings.exe /f 2>$null"],
            ),
            BenchmarkTask(
                task_id="inter_005",
                name="Multi-window management",
                description="Open Notepad, Calculator, and Paint side by side. Arrange Notepad on the left half and Calculator on the right half of the screen.",
                category="intermediate",
                domain="multi-app",
                optimal_steps=6,
                cleanup_commands=[
                    "taskkill /im notepad.exe /f 2>$null",
                    "taskkill /im CalculatorApp.exe /f 2>$null",
                    "taskkill /im mspaint.exe /f 2>$null",
                ],
            ),
            BenchmarkTask(
                task_id="inter_006",
                name="Find and open file",
                description="Use File Explorer to navigate to the Windows directory (C:\\Windows) and find the 'notepad.exe' file.",
                category="intermediate",
                domain="explorer",
                optimal_steps=4,
            ),
            BenchmarkTask(
                task_id="inter_007",
                name="Change desktop background",
                description="Open Settings, go to Personalization > Background, and change the background to a solid color.",
                category="intermediate",
                domain="settings",
                optimal_steps=5,
                cleanup_commands=["taskkill /im SystemSettings.exe /f 2>$null"],
            ),
            BenchmarkTask(
                task_id="inter_008",
                name="Create scheduled task",
                description="Open PowerShell and create a text file listing all running processes, sorted by memory usage (top 10), saved as 'processes.txt' on the Desktop.",
                category="intermediate",
                domain="shell",
                optimal_steps=3,
                cleanup_commands=[
                    "Remove-Item $env:USERPROFILE\\Desktop\\processes.txt -Force 2>$null"
                ],
            ),
            BenchmarkTask(
                task_id="inter_009",
                name="Pin app to taskbar",
                description="Search for 'Paint' in the Start menu and pin it to the taskbar.",
                category="intermediate",
                domain="system",
                optimal_steps=4,
            ),
            BenchmarkTask(
                task_id="inter_010",
                name="File rename batch",
                description="Create three text files on the Desktop named 'file1.txt', 'file2.txt', 'file3.txt' using PowerShell, then rename 'file1.txt' to 'renamed_file.txt' using File Explorer.",
                category="intermediate",
                domain="multi-app",
                optimal_steps=6,
                cleanup_commands=[
                    "Remove-Item $env:USERPROFILE\\Desktop\\file*.txt -Force 2>$null",
                    "Remove-Item $env:USERPROFILE\\Desktop\\renamed_file.txt -Force 2>$null",
                ],
            ),
        ]

        return cls(
            name="AgenticOS Intermediate",
            description="10 multi-application tasks testing cross-app workflows",
            tasks=tasks,
        )

    @classmethod
    def builtin_advanced(cls) -> "BenchmarkSuite":
        """Advanced complex workflow tasks (5 tasks)."""
        tasks = [
            BenchmarkTask(
                task_id="adv_001",
                name="Full document workflow",
                description="Open Notepad, write a short 3-line memo (To: Team, Subject: Meeting, Body: Meeting at 3pm tomorrow), save it as 'memo.txt' on Desktop, then open it with WordPad to verify the content.",
                category="advanced",
                domain="multi-app",
                optimal_steps=10,
                cleanup_commands=[
                    "taskkill /im notepad.exe /f 2>$null",
                    "taskkill /im wordpad.exe /f 2>$null",
                    "Remove-Item $env:USERPROFILE\\Desktop\\memo.txt -Force 2>$null",
                ],
            ),
            BenchmarkTask(
                task_id="adv_002",
                name="System diagnostics",
                description="Open PowerShell, get the computer name, IP address, and OS version. Save all information to a file 'system_info.txt' on the Desktop.",
                category="advanced",
                domain="shell",
                optimal_steps=5,
                cleanup_commands=[
                    "Remove-Item $env:USERPROFILE\\Desktop\\system_info.txt -Force 2>$null"
                ],
            ),
            BenchmarkTask(
                task_id="adv_003",
                name="File organization workflow",
                description="Create a folder structure on Desktop: 'Project/docs', 'Project/src', 'Project/tests'. Create a README.txt in 'Project/' with the text 'AgenticOS Project'. Create a main.txt in 'Project/src/' with 'print hello'.",
                category="advanced",
                domain="multi-app",
                optimal_steps=12,
                cleanup_commands=[
                    "Remove-Item $env:USERPROFILE\\Desktop\\Project -Force -Recurse 2>$null"
                ],
            ),
            BenchmarkTask(
                task_id="adv_004",
                name="App install verification",
                description="Use PowerShell to check if Python is installed (run 'python --version'), then check if Git is installed (run 'git --version'). Save the results to 'installed_apps.txt' on the Desktop.",
                category="advanced",
                domain="shell",
                optimal_steps=5,
                cleanup_commands=[
                    "Remove-Item $env:USERPROFILE\\Desktop\\installed_apps.txt -Force 2>$null"
                ],
            ),
            BenchmarkTask(
                task_id="adv_005",
                name="Complex calculation workflow",
                description="Open Calculator, compute (123 + 456) * 2, note the result, open Notepad, type 'Calculation result: [the result]' and save as 'calc_result.txt' on Desktop.",
                category="advanced",
                domain="multi-app",
                optimal_steps=12,
                cleanup_commands=[
                    "taskkill /im notepad.exe /f 2>$null",
                    "taskkill /im CalculatorApp.exe /f 2>$null",
                    "Remove-Item $env:USERPROFILE\\Desktop\\calc_result.txt -Force 2>$null",
                ],
            ),
        ]

        return cls(
            name="AgenticOS Advanced",
            description="5 complex multi-step workflows testing end-to-end automation",
            tasks=tasks,
        )

    @classmethod
    def builtin_all(cls) -> "BenchmarkSuite":
        """Combined suite with all built-in tasks (30 tasks)."""
        basic = cls.builtin_basic()
        intermediate = cls.builtin_intermediate()
        advanced = cls.builtin_advanced()

        return cls(
            name="AgenticOS Full Suite",
            description="30 tasks across basic, intermediate, and advanced categories",
            tasks=basic.tasks + intermediate.tasks + advanced.tasks,
        )
