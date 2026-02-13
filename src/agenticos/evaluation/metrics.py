"""Benchmark metrics for evaluating agent performance.

Implements standard OS agent evaluation metrics: success rate,
step efficiency, grounding accuracy, time-to-complete, and cost.
"""

from __future__ import annotations

import json
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class TaskResult:
    """Result of a single benchmark task evaluation.

    Attributes:
        task_id: Unique task identifier.
        task_name: Human-readable task name.
        category: Task category (basic, intermediate, advanced).
        success: Whether the task was completed successfully.
        steps_taken: Number of agent steps used.
        optimal_steps: Known optimal number of steps.
        elapsed_seconds: Total wall-clock time.
        grounding_accuracy: Fraction of correct element identifications.
        error: Error description if failed.
        error_category: Classified error type.
        llm_calls: Number of LLM API calls made.
        cost_usd: Estimated API cost in USD.
    """
    task_id: str
    task_name: str
    category: str = "basic"
    success: bool = False
    steps_taken: int = 0
    optimal_steps: int = 1
    elapsed_seconds: float = 0.0
    grounding_accuracy: float = 0.0
    error: Optional[str] = None
    error_category: Optional[str] = None  # grounding_error, action_error, planning_error
    llm_calls: int = 0
    cost_usd: float = 0.0

    @property
    def step_efficiency(self) -> float:
        """Step efficiency ratio (optimal / actual). 1.0 = perfect."""
        if self.steps_taken == 0:
            return 0.0
        return min(1.0, self.optimal_steps / self.steps_taken)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON export."""
        return {
            "task_id": self.task_id,
            "task_name": self.task_name,
            "category": self.category,
            "success": self.success,
            "steps_taken": self.steps_taken,
            "optimal_steps": self.optimal_steps,
            "step_efficiency": round(self.step_efficiency, 3),
            "elapsed_seconds": round(self.elapsed_seconds, 2),
            "grounding_accuracy": round(self.grounding_accuracy, 3),
            "error": self.error,
            "error_category": self.error_category,
            "llm_calls": self.llm_calls,
            "cost_usd": round(self.cost_usd, 4),
        }


@dataclass
class BenchmarkMetrics:
    """Aggregated benchmark metrics across multiple tasks.

    Computes standard evaluation metrics used in OS agent papers
    (OSWorld, WAA, AgentBench).

    Example:
        >>> metrics = BenchmarkMetrics()
        >>> metrics.add_result(TaskResult("t1", "Open Notepad", success=True, steps_taken=2))
        >>> metrics.add_result(TaskResult("t2", "Save file", success=False, steps_taken=5))
        >>> print(metrics.summary())
    """
    results: list[TaskResult] = field(default_factory=list)
    model_name: str = ""
    benchmark_name: str = ""
    timestamp: float = field(default_factory=time.time)

    def add_result(self, result: TaskResult) -> None:
        """Add a task result to the metrics."""
        self.results.append(result)

    # ── Core Metrics ─────────────────────────────────────────────────

    @property
    def success_rate(self) -> float:
        """Overall success rate (primary metric)."""
        if not self.results:
            return 0.0
        return sum(1 for r in self.results if r.success) / len(self.results)

    @property
    def mean_step_efficiency(self) -> float:
        """Mean step efficiency across successful tasks."""
        successful = [r for r in self.results if r.success]
        if not successful:
            return 0.0
        return statistics.mean(r.step_efficiency for r in successful)

    @property
    def mean_time(self) -> float:
        """Mean time-to-complete in seconds."""
        if not self.results:
            return 0.0
        return statistics.mean(r.elapsed_seconds for r in self.results)

    @property
    def mean_grounding_accuracy(self) -> float:
        """Mean grounding accuracy."""
        accuracies = [r.grounding_accuracy for r in self.results if r.grounding_accuracy > 0]
        if not accuracies:
            return 0.0
        return statistics.mean(accuracies)

    @property
    def total_cost(self) -> float:
        """Total API cost in USD."""
        return sum(r.cost_usd for r in self.results)

    @property
    def mean_steps(self) -> float:
        """Mean steps per task."""
        if not self.results:
            return 0.0
        return statistics.mean(r.steps_taken for r in self.results)

    # ── Category Breakdown ───────────────────────────────────────────

    def success_rate_by_category(self) -> dict[str, float]:
        """Success rate broken down by task category."""
        categories: dict[str, list[bool]] = {}
        for r in self.results:
            categories.setdefault(r.category, []).append(r.success)

        return {
            cat: sum(results) / len(results)
            for cat, results in categories.items()
        }

    def error_analysis(self) -> dict[str, int]:
        """Count errors by category."""
        errors: dict[str, int] = {}
        for r in self.results:
            if not r.success and r.error_category:
                errors[r.error_category] = errors.get(r.error_category, 0) + 1
        return errors

    # ── Reporting ────────────────────────────────────────────────────

    def summary(self) -> str:
        """Generate a text summary of benchmark results."""
        lines = [
            f"═══ Benchmark Results: {self.benchmark_name} ═══",
            f"Model: {self.model_name}",
            f"Tasks: {len(self.results)}",
            f"",
            f"── Core Metrics ──",
            f"  Success Rate:       {self.success_rate:.1%}",
            f"  Mean Steps:         {self.mean_steps:.1f}",
            f"  Step Efficiency:    {self.mean_step_efficiency:.1%}",
            f"  Mean Time:          {self.mean_time:.1f}s",
            f"  Grounding Accuracy: {self.mean_grounding_accuracy:.1%}",
            f"  Total Cost:         ${self.total_cost:.2f}",
        ]

        # Category breakdown
        categories = self.success_rate_by_category()
        if categories:
            lines.append(f"\n── By Category ──")
            for cat, rate in sorted(categories.items()):
                count = sum(1 for r in self.results if r.category == cat)
                lines.append(f"  {cat:20s}: {rate:.1%} ({count} tasks)")

        # Error analysis
        errors = self.error_analysis()
        if errors:
            lines.append(f"\n── Error Analysis ──")
            for error_type, count in sorted(errors.items(), key=lambda x: -x[1]):
                lines.append(f"  {error_type:20s}: {count}")

        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Export all metrics as a dictionary."""
        return {
            "benchmark_name": self.benchmark_name,
            "model_name": self.model_name,
            "timestamp": self.timestamp,
            "summary": {
                "total_tasks": len(self.results),
                "success_rate": round(self.success_rate, 4),
                "mean_steps": round(self.mean_steps, 2),
                "mean_step_efficiency": round(self.mean_step_efficiency, 4),
                "mean_time_seconds": round(self.mean_time, 2),
                "mean_grounding_accuracy": round(self.mean_grounding_accuracy, 4),
                "total_cost_usd": round(self.total_cost, 4),
            },
            "by_category": {
                cat: round(rate, 4)
                for cat, rate in self.success_rate_by_category().items()
            },
            "error_analysis": self.error_analysis(),
            "results": [r.to_dict() for r in self.results],
        }

    def save_json(self, path: str) -> str:
        """Save metrics to a JSON file.

        Args:
            path: Output file path.

        Returns:
            Path to saved file.
        """
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        with open(output, "w") as f:
            json.dump(self.to_dict(), f, indent=2)
        return str(output)

    def to_markdown_table(self) -> str:
        """Generate a markdown comparison table."""
        lines = [
            "| Metric | Value |",
            "|--------|-------|",
            f"| Success Rate | {self.success_rate:.1%} |",
            f"| Mean Steps | {self.mean_steps:.1f} |",
            f"| Step Efficiency | {self.mean_step_efficiency:.1%} |",
            f"| Mean Time | {self.mean_time:.1f}s |",
            f"| Grounding Accuracy | {self.mean_grounding_accuracy:.1%} |",
            f"| Total Cost | ${self.total_cost:.2f} |",
        ]
        return "\n".join(lines)

    @staticmethod
    def comparison_table(results: dict[str, "BenchmarkMetrics"]) -> str:
        """Generate a comparison table across multiple agents/models.

        Args:
            results: Dict mapping agent name to its metrics.

        Returns:
            Markdown table string.
        """
        agents = list(results.keys())
        header = "| Metric | " + " | ".join(agents) + " |"
        separator = "|--------|" + "|".join(["-------"] * len(agents)) + "|"

        rows = [
            ("Success Rate", lambda m: f"{m.success_rate:.1%}"),
            ("Mean Steps", lambda m: f"{m.mean_steps:.1f}"),
            ("Step Efficiency", lambda m: f"{m.mean_step_efficiency:.1%}"),
            ("Mean Time (s)", lambda m: f"{m.mean_time:.1f}"),
            ("Grounding Acc.", lambda m: f"{m.mean_grounding_accuracy:.1%}"),
            ("Cost (USD)", lambda m: f"${m.total_cost:.2f}"),
        ]

        lines = [header, separator]
        for metric_name, formatter in rows:
            values = " | ".join(formatter(results[a]) for a in agents)
            lines.append(f"| {metric_name} | {values} |")

        return "\n".join(lines)
