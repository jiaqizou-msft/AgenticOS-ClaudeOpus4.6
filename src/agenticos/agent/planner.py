"""Task planner — decomposes complex tasks into atomic steps.

Uses LLM to break down high-level user requests into a sequence
of concrete, executable sub-tasks.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional

import litellm

from agenticos.utils.config import AgenticOSConfig, get_config, resolve_api_key
from agenticos.utils.exceptions import LLMError

PLANNER_SYSTEM_PROMPT = """You are a task planner for a Windows desktop automation agent.
Given a high-level user request, decompose it into a sequence of concrete, atomic steps
that can be executed on the Windows OS.

Each step should be specific enough to be completed in 1-3 agent actions.
Include application names, menu paths, and expected UI states.

Respond with a JSON object:
```json
{
  "plan": [
    {"step": 1, "description": "Open Notepad application", "app": "notepad", "expected_state": "Notepad window is open"},
    {"step": 2, "description": "Type the text 'Hello World'", "app": "notepad", "expected_state": "Text appears in editor"},
    {"step": 3, "description": "Save the file as test.txt", "app": "notepad", "expected_state": "File save dialog appears"}
  ],
  "estimated_total_actions": 8,
  "complexity": "simple"
}
```

Complexity levels: simple (1-3 steps), moderate (4-7 steps), complex (8+ steps).
"""


@dataclass
class PlanStep:
    """A single step in a task plan.

    Attributes:
        step_number: Sequential step number.
        description: What to do in this step.
        app: Target application (if any).
        expected_state: What the screen should look like after this step.
        completed: Whether this step has been completed.
    """
    step_number: int
    description: str
    app: str = ""
    expected_state: str = ""
    completed: bool = False


@dataclass
class TaskPlan:
    """A decomposed task plan.

    Attributes:
        original_task: The user's original request.
        steps: Ordered list of plan steps.
        estimated_actions: Estimated total agent actions needed.
        complexity: Task complexity level.
    """
    original_task: str
    steps: list[PlanStep] = field(default_factory=list)
    estimated_actions: int = 0
    complexity: str = "simple"

    @property
    def current_step(self) -> Optional[PlanStep]:
        """Get the next uncompleted step."""
        for step in self.steps:
            if not step.completed:
                return step
        return None

    @property
    def progress(self) -> float:
        """Completion progress as a fraction (0-1)."""
        if not self.steps:
            return 0.0
        completed = sum(1 for s in self.steps if s.completed)
        return completed / len(self.steps)

    @property
    def is_complete(self) -> bool:
        """Whether all steps are completed."""
        return all(s.completed for s in self.steps)

    def mark_current_complete(self) -> None:
        """Mark the current step as completed."""
        step = self.current_step
        if step:
            step.completed = True

    def summary(self) -> str:
        """Get a text summary of the plan."""
        lines = [f"Task: {self.original_task}"]
        lines.append(f"Complexity: {self.complexity} ({self.estimated_actions} est. actions)")
        lines.append(f"Progress: {self.progress:.0%}")
        lines.append("")
        for step in self.steps:
            status = "✓" if step.completed else "○"
            lines.append(f"  {status} Step {step.step_number}: {step.description}")
        return "\n".join(lines)


class TaskPlanner:
    """Decomposes complex tasks into executable plans.

    Uses LLM to analyze a user request and produce a structured
    sequence of atomic steps.

    Example:
        >>> planner = TaskPlanner()
        >>> plan = await planner.plan("Create a Word document with a table")
        >>> print(plan.summary())
    """

    def __init__(self, config: Optional[AgenticOSConfig] = None) -> None:
        """Initialize task planner.

        Args:
            config: Configuration (uses defaults if None).
        """
        self.config = config or get_config()
        self._api_key = resolve_api_key(self.config)

    async def plan(self, task: str) -> TaskPlan:
        """Create a plan for a task.

        Args:
            task: Natural language task description.

        Returns:
            TaskPlan with decomposed steps.

        Raises:
            LLMError: If planning fails.
        """
        try:
            response = await litellm.acompletion(
                model=self.config.llm_model,
                messages=[
                    {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
                    {"role": "user", "content": f"Plan this task: {task}"},
                ],
                max_tokens=2048,
                temperature=0.1,
                api_key=self._api_key,
            )

            content = response.choices[0].message.content
            return self._parse_plan(task, content)

        except Exception as e:
            raise LLMError(f"Task planning failed: {e}") from e

    def _parse_plan(self, task: str, content: str) -> TaskPlan:
        """Parse LLM response into a TaskPlan.

        Args:
            task: Original task.
            content: LLM response text.

        Returns:
            Parsed TaskPlan.
        """
        content = content.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1])

        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            # Fallback: single-step plan
            return TaskPlan(
                original_task=task,
                steps=[PlanStep(1, task)],
                estimated_actions=5,
                complexity="simple",
            )

        steps = []
        for step_data in data.get("plan", []):
            steps.append(
                PlanStep(
                    step_number=step_data.get("step", len(steps) + 1),
                    description=step_data.get("description", ""),
                    app=step_data.get("app", ""),
                    expected_state=step_data.get("expected_state", ""),
                )
            )

        return TaskPlan(
            original_task=task,
            steps=steps,
            estimated_actions=data.get("estimated_total_actions", len(steps) * 3),
            complexity=data.get("complexity", "simple"),
        )
