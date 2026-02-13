"""Unit tests for evaluation modules."""

import json
import tempfile
from pathlib import Path

import pytest

from agenticos.evaluation.metrics import BenchmarkMetrics, TaskResult
from agenticos.evaluation.tasks import BenchmarkSuite, BenchmarkTask


class TestTaskResult:
    """Tests for TaskResult data class."""

    def test_success_result(self):
        result = TaskResult(
            task_id="basic_notepad_open",
            task_name="Open Notepad",
            category="basic",
            success=True,
            steps_taken=3,
            optimal_steps=2,
            elapsed_seconds=5.5,
            grounding_accuracy=0.85,
            cost_usd=0.02,
        )
        assert result.success
        assert result.step_efficiency == pytest.approx(2 / 3)

    def test_failure_result(self):
        result = TaskResult(
            task_id="advanced_multi_app",
            task_name="Multi-app workflow",
            category="advanced",
            success=False,
            steps_taken=10,
            optimal_steps=5,
            elapsed_seconds=30.0,
            error="Max steps exceeded",
        )
        assert not result.success
        assert result.error == "Max steps exceeded"

    def test_zero_steps_efficiency(self):
        result = TaskResult(task_id="t", task_name="t", steps_taken=0)
        assert result.step_efficiency == 0.0


class TestBenchmarkMetrics:
    """Tests for BenchmarkMetrics."""

    def _sample_results(self):
        return [
            TaskResult(task_id="t1", task_name="Task 1", category="basic", success=True, steps_taken=3, optimal_steps=2, elapsed_seconds=5.0, grounding_accuracy=0.9, cost_usd=0.01),
            TaskResult(task_id="t2", task_name="Task 2", category="basic", success=True, steps_taken=5, optimal_steps=3, elapsed_seconds=8.0, grounding_accuracy=0.8, cost_usd=0.02),
            TaskResult(task_id="t3", task_name="Task 3", category="intermediate", success=False, steps_taken=10, optimal_steps=5, elapsed_seconds=30.0, grounding_accuracy=0.6, cost_usd=0.05, error="Failed", error_category="grounding_error"),
            TaskResult(task_id="t4", task_name="Task 4", category="advanced", success=True, steps_taken=7, optimal_steps=4, elapsed_seconds=20.0, grounding_accuracy=0.75, cost_usd=0.03),
        ]

    def test_success_rate(self):
        metrics = BenchmarkMetrics(self._sample_results())
        assert metrics.success_rate == pytest.approx(0.75)

    def test_success_rate_by_category(self):
        metrics = BenchmarkMetrics(self._sample_results())
        by_cat = metrics.success_rate_by_category()  # it's a method
        assert by_cat["basic"] == pytest.approx(1.0)
        assert by_cat["intermediate"] == pytest.approx(0.0)
        assert by_cat["advanced"] == pytest.approx(1.0)

    def test_mean_step_efficiency(self):
        metrics = BenchmarkMetrics(self._sample_results())
        eff = metrics.mean_step_efficiency
        assert 0.0 < eff <= 1.0

    def test_mean_time(self):
        metrics = BenchmarkMetrics(self._sample_results())
        assert metrics.mean_time > 0

    def test_total_cost(self):
        metrics = BenchmarkMetrics(self._sample_results())
        assert metrics.total_cost == pytest.approx(0.11)

    def test_error_analysis(self):
        metrics = BenchmarkMetrics(self._sample_results())
        errors = metrics.error_analysis()  # it's a method returning dict[str, int]
        assert "grounding_error" in errors
        assert errors["grounding_error"] == 1

    def test_summary_is_string(self):
        metrics = BenchmarkMetrics(self._sample_results())
        summary = metrics.summary()
        assert isinstance(summary, str)
        assert "Success Rate" in summary
        assert "75.0%" in summary

    def test_save_json(self):
        metrics = BenchmarkMetrics(self._sample_results())
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "results.json"
            metrics.save_json(path)
            assert path.exists()
            data = json.loads(path.read_text())
            assert "summary" in data or "results" in data

    def test_to_markdown_table(self):
        metrics = BenchmarkMetrics(self._sample_results())
        md = metrics.to_markdown_table()
        assert "| Metric" in md or "|" in md
        assert "Success Rate" in md


class TestBenchmarkTask:
    """Tests for BenchmarkTask."""

    def test_task_creation(self):
        task = BenchmarkTask(
            task_id="test_001",
            name="Test Task",
            description="A test task",
            category="basic",
            max_steps=10,
        )
        assert task.task_id == "test_001"
        assert task.max_steps == 10


class TestBenchmarkSuite:
    """Tests for BenchmarkSuite."""

    def test_builtin_basic(self):
        suite = BenchmarkSuite.builtin_basic()
        assert len(suite.tasks) >= 10
        assert all(t.category == "basic" for t in suite.tasks)

    def test_builtin_intermediate(self):
        suite = BenchmarkSuite.builtin_intermediate()
        assert len(suite.tasks) >= 5
        assert all(t.category == "intermediate" for t in suite.tasks)

    def test_builtin_advanced(self):
        suite = BenchmarkSuite.builtin_advanced()
        assert len(suite.tasks) >= 3
        assert all(t.category == "advanced" for t in suite.tasks)

    def test_builtin_all(self):
        all_suite = BenchmarkSuite.builtin_all()
        basic = BenchmarkSuite.builtin_basic()
        intermediate = BenchmarkSuite.builtin_intermediate()
        advanced = BenchmarkSuite.builtin_advanced()
        assert len(all_suite.tasks) == len(basic.tasks) + len(intermediate.tasks) + len(advanced.tasks)

    def test_unique_task_ids(self):
        all_suite = BenchmarkSuite.builtin_all()
        ids = [t.task_id for t in all_suite.tasks]
        assert len(ids) == len(set(ids)), "Task IDs must be unique"
