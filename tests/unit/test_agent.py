"""Unit tests for agent modules."""

from unittest.mock import MagicMock

import pytest

from agenticos.agent.base import AgentState, AgentStatus, Observation, StepResult
from agenticos.agent.planner import PlanStep, TaskPlan


class TestAgentState:
    """Tests for the AgentState data class."""

    def test_initial_state(self):
        state = AgentState(task="Open Notepad")
        assert state.task == "Open Notepad"
        assert state.steps == []
        assert state.success is False
        assert state.total_steps == 0

    def test_to_summary(self):
        state = AgentState(
            task="Open Notepad",
            steps=[],
            success=True,
            start_time=100.0,
            end_time=105.0,
            total_steps=3,
        )
        summary = state.to_summary()
        assert summary["task"] == "Open Notepad"
        assert summary["success"] is True
        assert summary["total_steps"] == 3
        assert summary["elapsed_seconds"] == 5.0


class TestObservation:
    """Tests for the Observation data class."""

    def test_observation_with_elements(self):
        from agenticos.grounding.accessibility import UIElement

        elem1 = UIElement(name="OK", control_type="Button", idx=0)
        elem2 = UIElement(name="Name", control_type="Edit", idx=1)

        obs = Observation(
            screenshot=MagicMock(),
            ui_elements=[elem1, elem2],
            active_window="Notepad",
        )
        assert obs.active_window == "Notepad"
        assert len(obs.ui_elements) == 2

    def test_elements_summary(self):
        from agenticos.grounding.accessibility import UIElement

        elem1 = UIElement(name="OK", control_type="Button", idx=0, center=(100, 200))
        elem2 = UIElement(name="Name", control_type="Edit", idx=1, center=(50, 50))

        obs = Observation(
            screenshot=MagicMock(),
            ui_elements=[elem1, elem2],
            active_window="Test",
        )
        summary = obs.elements_summary()
        assert "Button" in summary
        assert "Edit" in summary


class TestStepResult:
    """Tests for the StepResult data class."""

    def test_step_result_defaults(self):
        step = StepResult(
            step_number=1,
            observation=Observation(),
            thought="Click the OK button",
        )
        assert step.step_number == 1
        assert step.thought == "Click the OK button"
        assert step.is_complete is False

    def test_step_result_with_error(self):
        step = StepResult(
            step_number=2,
            observation=Observation(),
            thought="Type text",
            error="Element not found",
        )
        assert step.error == "Element not found"


class TestPlanStep:
    """Tests for the PlanStep data class."""

    def test_plan_step(self):
        step = PlanStep(
            step_number=1,
            description="Open Notepad",
            expected_state="Notepad window appears",
        )
        assert step.description == "Open Notepad"
        assert step.completed is False

    def test_plan_step_completion(self):
        step = PlanStep(
            step_number=1,
            description="Type text",
            expected_state="Text appears in editor",
            completed=True,
        )
        assert step.completed


class TestTaskPlan:
    """Tests for the TaskPlan data class."""

    def test_task_plan_progress(self):
        plan = TaskPlan(
            original_task="Write a letter",
            steps=[
                PlanStep(1, "Open Notepad", expected_state="Notepad opens", completed=True),
                PlanStep(2, "Type letter", expected_state="Text appears"),
                PlanStep(3, "Save file", expected_state="File saved"),
            ],
        )
        assert plan.progress == pytest.approx(1 / 3)

    def test_task_plan_current_step(self):
        plan = TaskPlan(
            original_task="Test",
            steps=[
                PlanStep(1, "Step 1", expected_state="Done", completed=True),
                PlanStep(2, "Step 2", expected_state="Pending"),
            ],
        )
        current = plan.current_step
        assert current.description == "Step 2"

    def test_task_plan_all_complete(self):
        plan = TaskPlan(
            original_task="Test",
            steps=[
                PlanStep(1, "Step 1", expected_state="Done", completed=True),
                PlanStep(2, "Step 2", expected_state="Done", completed=True),
            ],
        )
        assert plan.current_step is None
        assert plan.progress == pytest.approx(1.0)
        assert plan.is_complete is True

    def test_mark_current_complete(self):
        plan = TaskPlan(
            original_task="Test",
            steps=[
                PlanStep(1, "Step 1", expected_state="Done"),
                PlanStep(2, "Step 2", expected_state="Done"),
            ],
        )
        plan.mark_current_complete()
        assert plan.steps[0].completed is True
        assert plan.steps[1].completed is False
