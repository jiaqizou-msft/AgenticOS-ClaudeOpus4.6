"""CLI chat interface for AgenticOS.

Provides a rich terminal interface for interacting with the
NavigatorAgent via natural language chat.
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

from agenticos.agent.base import AgentStatus, StepResult
from agenticos.agent.navigator import NavigatorAgent
from agenticos.utils.config import get_config

# Custom theme
THEME = Theme({
    "agent.thinking": "cyan italic",
    "agent.acting": "yellow bold",
    "agent.success": "green bold",
    "agent.error": "red bold",
    "agent.info": "blue",
    "user.input": "white bold",
})

console = Console(theme=THEME)


def print_banner() -> None:
    """Print the AgenticOS banner."""
    banner = """
╔═══════════════════════════════════════════════════════════════╗
║                                                               ║
║     █████╗  ██████╗ ███████╗███╗   ██╗████████╗██╗ ██████╗   ║
║    ██╔══██╗██╔════╝ ██╔════╝████╗  ██║╚══██╔══╝██║██╔════╝   ║
║    ███████║██║  ███╗█████╗  ██╔██╗ ██║   ██║   ██║██║        ║
║    ██╔══██║██║   ██║██╔══╝  ██║╚██╗██║   ██║   ██║██║        ║
║    ██║  ██║╚██████╔╝███████╗██║ ╚████║   ██║   ██║╚██████╗   ║
║    ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝   ╚═╝  ╚═╝ ╚═════╝   ║
║                          OS                                    ║
║                                                               ║
║   🤖 Your AI-Powered Desktop Navigator                        ║
║   Type a task and watch it happen. Type 'exit' to quit.       ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝
"""
    console.print(banner, style="cyan")


def print_step(step: StepResult) -> None:
    """Print a step result to the console.

    Args:
        step: The step result to display.
    """
    # Step header
    console.print(f"\n[agent.info]─── Step {step.step_number} ───[/]")

    # Thought
    if step.thought:
        console.print(f"  [agent.thinking]💭 {step.thought}[/]")

    # Action
    if step.action:
        action_str = f"{step.action.type.value}"
        if step.action.params:
            params_str = ", ".join(f"{k}={v}" for k, v in step.action.params.items())
            action_str += f"({params_str})"
        console.print(f"  [agent.acting]⚡ {action_str}[/]")

    # Result
    if step.action_result:
        if step.action_result.success:
            console.print(f"  [agent.success]✓ Success[/] ({step.elapsed_ms:.0f}ms)")
            if step.action_result.output:
                console.print(f"  [dim]  Output: {step.action_result.output[:200]}[/]")
        else:
            console.print(f"  [agent.error]✗ Failed: {step.action_result.error}[/]")

    # Completion
    if step.is_complete:
        console.print(f"  [agent.success]🎯 Task marked as complete[/]")


def print_status(status: AgentStatus) -> None:
    """Print status update.

    Args:
        status: Current agent status.
    """
    icons = {
        AgentStatus.OBSERVING: "👁️  Observing screen...",
        AgentStatus.THINKING: "🧠 Thinking...",
        AgentStatus.ACTING: "⚡ Executing action...",
        AgentStatus.COMPLETED: "✅ Task completed!",
        AgentStatus.FAILED: "❌ Task failed.",
    }
    msg = icons.get(status, str(status))
    console.print(f"  [dim]{msg}[/]", end="\r")


async def run_task(task: str, config=None) -> None:
    """Run a single task through the agent.

    Args:
        task: Natural language task description.
        config: Optional configuration override.
    """
    config = config or get_config()
    agent = NavigatorAgent(
        config=config,
        on_step=print_step,
        on_status=print_status,
    )

    console.print(f"\n[user.input]📋 Task: {task}[/]")
    console.print(f"[dim]   Model: {config.llm_model} | Max steps: {config.max_steps}[/]")
    console.print(f"[dim]   Grounding: {config.grounding_mode.value} | Recording: {config.auto_record_gif}[/]")
    console.print()

    start = time.time()
    state = await agent.navigate(task)
    elapsed = time.time() - start

    # Print summary
    console.print()
    if state.success:
        console.print(
            Panel(
                f"[agent.success]✅ Task completed successfully![/]\n"
                f"   Steps: {state.total_steps} | Time: {elapsed:.1f}s",
                title="Result",
                border_style="green",
            )
        )
    else:
        console.print(
            Panel(
                f"[agent.error]❌ Task failed[/]\n"
                f"   Error: {state.error}\n"
                f"   Steps: {state.total_steps} | Time: {elapsed:.1f}s",
                title="Result",
                border_style="red",
            )
        )

    # Save GIF if recorded
    if config.auto_record_gif:
        gif_path = f"recordings/session_{int(time.time())}.gif"
        saved = agent.save_recording(gif_path)
        if saved:
            console.print(f"[dim]📹 Recording saved to: {saved}[/]")


@click.command()
@click.option("--model", "-m", default=None, help="LLM model to use")
@click.option("--max-steps", "-s", default=None, type=int, help="Max steps per task")
@click.option("--no-confirm", "-y", is_flag=True, help="Skip action confirmations")
@click.option("--no-record", is_flag=True, help="Disable GIF recording")
@click.option("--task", "-t", default=None, help="Run a single task and exit")
def main(
    model: Optional[str],
    max_steps: Optional[int],
    no_confirm: bool,
    no_record: bool,
    task: Optional[str],
) -> None:
    """AgenticOS — AI-Powered Desktop Navigator.

    Chat with an AI agent that controls your Windows desktop.
    Type natural language tasks and watch them execute in real time.
    """
    config = get_config()

    # Apply CLI overrides
    if model:
        config.llm_model = model
    if max_steps:
        config.max_steps = max_steps
    if no_confirm:
        config.confirm_actions = False
    if no_record:
        config.auto_record_gif = False

    # Single task mode
    if task:
        asyncio.run(run_task(task, config))
        return

    # Interactive chat mode
    print_banner()
    console.print("[dim]Press Ctrl+C to exit at any time.[/]\n")

    while True:
        try:
            user_input = console.input("[user.input]You → [/]").strip()

            if not user_input:
                continue

            if user_input.lower() in ("exit", "quit", "q"):
                console.print("[dim]Goodbye! 👋[/]")
                break

            if user_input.lower() == "help":
                console.print(
                    Panel(
                        "**Commands:**\n"
                        "- Type any task in natural language\n"
                        "- `exit` / `quit` — Exit the program\n"
                        "- `help` — Show this help\n\n"
                        "**Example tasks:**\n"
                        "- Open Notepad and type 'Hello World'\n"
                        "- Create a folder named 'Reports' on the Desktop\n"
                        "- Open Calculator and compute 42 * 17\n"
                        "- Take a screenshot and save it\n"
                        "- Open File Explorer and navigate to Documents",
                        title="Help",
                        border_style="blue",
                    )
                )
                continue

            asyncio.run(run_task(user_input, config))

        except KeyboardInterrupt:
            console.print("\n[dim]Interrupted. Goodbye! 👋[/]")
            break
        except Exception as e:
            console.print(f"[agent.error]Error: {e}[/]")


if __name__ == "__main__":
    main()
