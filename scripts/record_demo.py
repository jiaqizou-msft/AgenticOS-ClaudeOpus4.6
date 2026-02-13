#!/usr/bin/env python3
"""Record a GIF demo of AgenticOS performing a task.

Usage:
    python scripts/record_demo.py "Open Notepad and type Hello World" --output demo.gif
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


async def record(task: str, output: str, model: str | None = None, max_steps: int = 10):
    """Record a demo GIF of an agent performing a task."""
    from agenticos.agent.navigator import NavigatorAgent
    from agenticos.utils.config import AgenticOSConfig

    config = AgenticOSConfig(
        confirm_actions=False,
        record_gif=True,
        recording_dir=str(Path(output).parent),
    )
    if model:
        config.llm_model = model

    agent = NavigatorAgent(config=config)

    print(f"🎬 Recording demo: {task}")
    print(f"   Output: {output}")
    print(f"   Model: {config.llm_model}")
    print()

    state = await agent.navigate(task=task, max_steps=max_steps)

    status = "✅ Success" if state.success else "❌ Failed"
    print(f"\n{status} in {len(state.steps)} steps ({state.elapsed_seconds:.1f}s)")

    # The navigator auto-saves GIF to recording_dir
    print(f"🎬 GIF saved to {config.recording_dir}/")


def main():
    parser = argparse.ArgumentParser(description="Record AgenticOS Demo GIF")
    parser.add_argument("task", help="Task to perform")
    parser.add_argument("--output", default="recordings/demo.gif", help="Output GIF path")
    parser.add_argument("--model", default=None, help="LLM model override")
    parser.add_argument("--max-steps", type=int, default=10, help="Max steps")
    args = parser.parse_args()

    asyncio.run(record(args.task, args.output, args.model, args.max_steps))


if __name__ == "__main__":
    main()
