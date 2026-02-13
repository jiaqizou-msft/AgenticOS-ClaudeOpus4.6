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
            max_steps=10,
            elapsed_seconds=5.5,
            grounding_accuracy=0.85,
            cost_usd=0.02,
        )
        assert result.success
        assert result.step_efficiency == pytest.approx(3 / 10)

    def test_failure_result(self):
        result = TaskResult(
            task_id="advanced_multi_app",
            task_name="Multi-app workflow",
            category="advanced",
            success=False,
            steps_taken=10,
            max_steps=10,
            elapsed_seconds=30.0,
            error="Max steps exceeded",
        )
        assert not result.success
        assert result.error == "Max steps exceeded"


class TestBenchmarkMetrics:
    """Tests for BenchmarkMetrics."""

    def _sample_results(self):
        return [
            TaskResult("t1", "Task 1", "basic", True, 3, 10, 5.0, 0.9, 0.01),
            TaskResult("t2", "Task 2", "basic", True, 5, 10, 8.0, 0.8, 0.02),
            TaskResult("t3", "Task 3", "intermediate", False, 10, 10, 30.0, 0.6, 0.05, error="Failed"),
            TaskResult("t4", "Task 4", "advanced", True, 7, 15, 20.0, 0.75, 0.03),
        ]

    def test_success_rate(self):
        metrics = BenchmarkMetrics(self._sample_results())
        assert metrics.success_rate == pytest.approx(0.75)

    def test_success_rate_by_category(self):
        metrics = BenchmarkMetrics(self._sample_results())
        by_cat = metrics.success_rate_by_category
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
        errors = metrics.error_analysis
        assert len(errors) == 1
        assert errors[0]["task_id"] == "t3"

    def test_summary(self):
        metrics = BenchmarkMetrics(self._sample_results())
        summary = metrics.summary()
        assert "success_rate" in summary
        assert "total_tasks" in summary

    def test_save_json(self):
        metrics = BenchmarkMetrics(self._sample_results())
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "results.json"
            metrics.save_json(path)
            assert path.exists()
            data = json.loads(path.read_text())
            assert "summary" in data

    def test_to_markdown_table(self):
        metrics = BenchmarkMetrics(self._sample_results())
        md = metrics.to_markdown_table()
        assert "| Task" in md
        assert "basic" in md


class TestBenchmarkTask:
    """Tests for BenchmarkTask."""

    def test_task_creation(self):
        task = BenchmarkTask(
            task_id="test_001",
            name="Test Task",
            category="basic",
            description="A test task",
            instruction="Do something",
            expected_outcome="Something happens",
            max_steps=10,
        )
        assert task.task_id == "test_001"
        assert task.max_steps == 10


class TestBenchmarkSuite:
    """Tests for BenchmarkSuite."""

    def test_builtin_basic(self):
        tasks = BenchmarkSuite.builtin_basic()
        assert len(tasks) >= 10
        assert all(t.category == "basic" for t in tasks)

    def test_builtin_intermediate(self):
        tasks = BenchmarkSuite.builtin_intermediate()
        assert len(tasks) >= 5
        assert all(t.category == "intermediate" for t in tasks)

    def test_builtin_advanced(self):
        tasks = BenchmarkSuite.builtin_advanced()
        assert len(tasks) >= 3
        assert all(t.category == "advanced" for t in tasks)

    def test_builtin_all(self):
        all_tasks = BenchmarkSuite.builtin_all()
        basic = BenchmarkSuite.builtin_basic()
        intermediate = BenchmarkSuite.builtin_intermediate()
        advanced = BenchmarkSuite.builtin_advanced()
        assert len(all_tasks) == len(basic) + len(intermediate) + len(advanced)

    def test_unique_task_ids(self):
        all_tasks = BenchmarkSuite.builtin_all()
        ids = [t.task_id for t in all_tasks]
        assert len(ids) == len(set(ids)), "Task IDs must be unique"
