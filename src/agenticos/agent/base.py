"""Base agent interface and data structures.

Defines the abstract Agent interface and shared data types used
across all agent implementations.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from agenticos.actions.compositor import Action, ActionResult
from agenticos.grounding.accessibility import UIElement
from agenticos.observation.screenshot import Screenshot


class AgentStatus(str, Enum):
    """Current status of the agent."""
    IDLE = "idle"
    OBSERVING = "observing"
    THINKING = "thinking"
    ACTING = "acting"
    WAITING_CONFIRMATION = "waiting_confirmation"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Observation:
    """Complete observation of the current screen state.

    Attributes:
        screenshot: Current screenshot.
        ui_elements: Detected UI elements.
        active_window: Title of the active/foreground window.
        screen_text: OCR-extracted text from screen.
        timestamp: When the observation was taken.
    """
    screenshot: Optional[Screenshot] = None
    ui_elements: list[UIElement] = field(default_factory=list)
    active_window: str = ""
    screen_text: str = ""
    timestamp: float = field(default_factory=time.time)

    def elements_summary(self) -> str:
        """Get a text summary of detected UI elements for LLM.

        Returns:
            Formatted string listing all elements.
        """
        if not self.ui_elements:
            return "No interactive UI elements detected."

        lines = [f"Active window: {self.active_window}"]
        lines.append(f"Detected {len(self.ui_elements)} interactive elements:")
        for elem in self.ui_elements:
            lines.append(f"  {elem.description()}")
        return "\n".join(lines)


@dataclass
class StepResult:
    """Result of one observe→think→act cycle.

    Attributes:
        step_number: Sequential step number.
        observation: What the agent observed.
        thought: Agent's reasoning (LLM output).
        action: The action decided upon.
        action_result: Result of executing the action.
        elapsed_ms: Total step time in milliseconds.
        is_complete: Whether the agent considers the task complete.
        error: Error message if the step failed.
    """
    step_number: int
    observation: Observation
    thought: str = ""
    action: Optional[Action] = None
    action_result: Optional[ActionResult] = None
    elapsed_ms: float = 0.0
    is_complete: bool = False
    error: Optional[str] = None


@dataclass
class AgentState:
    """Full state of an agent task execution.

    Attributes:
        task: The original user task/request.
        status: Current agent status.
        steps: History of all steps taken.
        start_time: When the task started.
        end_time: When the task ended.
        total_steps: Total number of steps taken.
        success: Whether the task was completed successfully.
        error: Final error message if failed.
    """
    task: str
    status: AgentStatus = AgentStatus.IDLE
    steps: list[StepResult] = field(default_factory=list)
    start_time: float = 0.0
    end_time: float = 0.0
    total_steps: int = 0
    success: bool = False
    error: Optional[str] = None

    @property
    def elapsed_seconds(self) -> float:
        """Total elapsed time in seconds."""
        if self.end_time > 0:
            return self.end_time - self.start_time
        if self.start_time > 0:
            return time.time() - self.start_time
        return 0.0

    def to_summary(self) -> dict[str, Any]:
        """Generate a summary dict for reporting.

        Returns:
            Summary with key metrics.
        """
        return {
            "task": self.task,
            "status": self.status.value,
            "total_steps": self.total_steps,
            "success": self.success,
            "elapsed_seconds": round(self.elapsed_seconds, 2),
            "error": self.error,
        }


class BaseAgent(ABC):
    """Abstract base class for AgenticOS agents.

    Defines the observe→think→act interface that all agent
    implementations must follow.
    """

    @abstractmethod
    async def observe(self) -> Observation:
        """Capture the current screen state.

        Returns:
            Observation with screenshot, UI elements, etc.
        """
        ...

    @abstractmethod
    async def think(
        self, observation: Observation, task: str, history: list[StepResult]
    ) -> tuple[Action, str, bool]:
        """Decide what action to take based on observation.

        Args:
            observation: Current screen state.
            task: The user's task description.
            history: Previous step results.

        Returns:
            Tuple of (action, reasoning_text, is_task_complete).
        """
        ...

    @abstractmethod
    async def act(self, action: Action) -> ActionResult:
        """Execute an action on the OS.

        Args:
            action: The action to execute.

        Returns:
            ActionResult with success/failure.
        """
        ...

    @abstractmethod
    async def navigate(self, task: str) -> AgentState:
        """Execute a complete task using the ReAct loop.

        Args:
            task: Natural language task description.

        Returns:
            AgentState with full execution history.
        """
        ...
