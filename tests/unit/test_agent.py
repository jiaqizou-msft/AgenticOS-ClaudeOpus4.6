"""Unit tests for agent modules."""

from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import asdict

import pytest

from agenticos.agent.base import AgentState, AgentStatus, Observation, StepResult
from agenticos.agent.planner import PlanStep, TaskPlan


class TestAgentState:
    """Tests for the AgentState data class."""

    def test_initial_state(self):
        state = AgentState(task="Open Notepad")
        assert state.task == "Open Notepad"
        assert state.steps == []
        assert state.success is None
        assert state.elapsed_seconds == 0.0

    def test_to_summary(self):
        state = AgentState(
            task="Open Notepad",
            steps=[
                StepResult(
                    step=1,
                    thought="I need to open Notepad",
                    action_description="Click Start menu",
                    success=True,
                )
            ],
            success=True,
            elapsed_seconds=5.0,
        )
        summary = state.to_summary()
        assert "Open Notepad" in summary
        assert "5.0" in summary


class TestObservation:
    """Tests for the Observation data class."""

    def test_observation_with_elements(self):
        obs = Observation(
            screenshot=MagicMock(),
            ui_elements=[
                MagicMock(description="Button: OK"),
                MagicMock(description="TextBox: Name"),
            ],
            active_window="Notepad",
        )
        assert obs.active_window == "Notepad"
        assert len(obs.ui_elements) == 2

    def test_elements_summary(self):
        elem1 = MagicMock()
        elem1.description = "Button: OK at (100,200)"
        elem2 = MagicMock()
        elem2.description = "TextBox: Name at (50,50)"

        obs = Observation(
            screenshot=MagicMock(),
            ui_elements=[elem1, elem2],
            active_window="Test",
        )
        summary = obs.elements_summary
        assert "Button" in summary
        assert "TextBox" in summary


class TestStepResult:
    """Tests for the StepResult data class."""

    def test_step_result_success(self):
        step = StepResult(
            step=1,
            thought="Click the OK button",
            action_description="click(100, 200)",
            success=True,
            result_message="Clicked successfully",
        )
        assert step.success
        assert step.step == 1

    def test_step_result_failure(self):
        step = StepResult(
            step=2,
            thought="Type text",
            action_description="type_text('hello')",
            success=False,
            error="Element not found",
        )
        assert not step.success
        assert step.error == "Element not found"


class TestPlanStep:
    """Tests for the PlanStep data class."""

    def test_plan_step(self):
        step = PlanStep(
            description="Open Notepad",
            expected_outcome="Notepad window appears",
        )
        assert step.description == "Open Notepad"
        assert step.completed is False

    def test_plan_step_completion(self):
        step = PlanStep(
            description="Type text",
            expected_outcome="Text appears in editor",
            completed=True,
        )
        assert step.completed


class TestTaskPlan:
    """Tests for the TaskPlan data class."""

    def test_task_plan_progress(self):
        plan = TaskPlan(
            goal="Write a letter",
            steps=[
                PlanStep("Open Notepad", "Notepad opens", completed=True),
                PlanStep("Type letter", "Text appears"),
                PlanStep("Save file", "File saved"),
            ],
        )
        assert plan.progress == 1 / 3

    def test_task_plan_next_step(self):
        plan = TaskPlan(
            goal="Test",
            steps=[
                PlanStep("Step 1", "Done", completed=True),
                PlanStep("Step 2", "Pending"),
            ],
        )
        next_step = plan.next_step
        assert next_step.description == "Step 2"

    def test_task_plan_all_complete(self):
        plan = TaskPlan(
            goal="Test",
            steps=[
                PlanStep("Step 1", "Done", completed=True),
                PlanStep("Step 2", "Done", completed=True),
            ],
        )
        assert plan.next_step is None
        assert plan.progress == 1.0
