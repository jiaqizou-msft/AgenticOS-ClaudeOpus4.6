#!/usr/bin/env python3
"""Benchmark runner for AgenticOS.

Usage:
    python scripts/run_benchmark.py --dry-run
    python scripts/run_benchmark.py --category basic --output results.json
    python scripts/run_benchmark.py --all --output results.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agenticos.evaluation.metrics import BenchmarkMetrics, TaskResult
from agenticos.evaluation.tasks import BenchmarkSuite, BenchmarkTask
from agenticos.utils.config import AgenticOSConfig


def run_task_dry(task: BenchmarkTask) -> TaskResult:
    """Simulate running a task (dry run mode)."""
    import random

    success = random.random() > 0.3
    steps = random.randint(1, task.max_steps)
    elapsed = random.uniform(2.0, 30.0)
    accuracy = random.uniform(0.5, 1.0) if success else random.uniform(0.1, 0.5)
    cost = steps * 0.005

    return TaskResult(
        task_id=task.task_id,
        task_name=task.name,
        category=task.category,
        success=success,
        steps_taken=steps,
        max_steps=task.max_steps,
        elapsed_seconds=round(elapsed, 2),
        grounding_accuracy=round(accuracy, 3),
        cost_usd=round(cost, 4),
        error=None if success else "Simulated failure",
    )


async def run_task_live(task: BenchmarkTask, config: AgenticOSConfig) -> TaskResult:
    """Run a task with the actual agent."""
    from agenticos.agent.navigator import NavigatorAgent

    agent = NavigatorAgent(config=config)
    start = time.time()

    try:
        state = await agent.navigate(
            task=task.instruction,
            max_steps=task.max_steps,
        )
        elapsed = time.time() - start

        return TaskResult(
            task_id=task.task_id,
            task_name=task.name,
            category=task.category,
            success=state.success or False,
            steps_taken=len(state.steps),
            max_steps=task.max_steps,
            elapsed_seconds=round(elapsed, 2),
            grounding_accuracy=0.0,  # TODO: compute from grounding hits
            cost_usd=0.0,  # TODO: track via litellm callbacks
            error=state.steps[-1].error if state.steps and not state.success else None,
        )
    except Exception as e:
        elapsed = time.time() - start
        return TaskResult(
            task_id=task.task_id,
            task_name=task.name,
            category=task.category,
            success=False,
            steps_taken=0,
            max_steps=task.max_steps,
            elapsed_seconds=round(elapsed, 2),
            error=str(e),
        )


def main():
    parser = argparse.ArgumentParser(description="AgenticOS Benchmark Runner")
    parser.add_argument(
        "--category",
        choices=["basic", "intermediate", "advanced", "all"],
        default="all",
        help="Task category to run",
    )
    parser.add_argument("--dry-run", action="store_true", help="Simulate tasks")
    parser.add_argument("--output", type=str, default="benchmark_results.json")
    parser.add_argument("--model", type=str, default=None, help="LLM model override")
    args = parser.parse_args()

    # Get tasks
    if args.category == "basic":
        tasks = BenchmarkSuite.builtin_basic()
    elif args.category == "intermediate":
        tasks = BenchmarkSuite.builtin_intermediate()
    elif args.category == "advanced":
        tasks = BenchmarkSuite.builtin_advanced()
    else:
        tasks = BenchmarkSuite.builtin_all()

    print(f"🏁 AgenticOS Benchmark Runner")
    print(f"   Tasks: {len(tasks)} ({args.category})")
    print(f"   Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    print(f"   Output: {args.output}")
    print()

    results: list[TaskResult] = []

    for i, task in enumerate(tasks, 1):
        print(f"  [{i}/{len(tasks)}] {task.name}...", end=" ", flush=True)

        if args.dry_run:
            result = run_task_dry(task)
        else:
            import asyncio

            config = AgenticOSConfig()
            if args.model:
                config.llm_model = args.model
            result = asyncio.run(run_task_live(task, config))

        status = "✅" if result.success else "❌"
        print(f"{status} ({result.elapsed_seconds:.1f}s, {result.steps_taken} steps)")
        results.append(result)

    # Compute metrics
    metrics = BenchmarkMetrics(results)
    summary = metrics.summary()

    print()
    print("=" * 60)
    print("📊 BENCHMARK RESULTS")
    print("=" * 60)
    print(f"  Total tasks:    {summary['total_tasks']}")
    print(f"  Success rate:   {summary['success_rate']:.1%}")
    print(f"  Mean time:      {summary['mean_time_seconds']:.1f}s")
    print(f"  Mean efficiency: {summary['mean_step_efficiency']:.2f}")
    print(f"  Total cost:     ${summary['total_cost_usd']:.4f}")
    print()

    by_cat = metrics.success_rate_by_category
    for cat, rate in by_cat.items():
        print(f"  {cat:15s}: {rate:.1%}")

    # Save
    output_path = Path(args.output)
    metrics.save_json(output_path)
    print(f"\n💾 Results saved to {output_path}")

    # Also save markdown table
    md_path = output_path.with_suffix(".md")
    md_path.write_text(metrics.to_markdown_table())
    print(f"📝 Markdown table saved to {md_path}")


if __name__ == "__main__":
    main()
