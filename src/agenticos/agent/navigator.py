"""Navigator agent — the main ReAct loop for OS navigation.

Implements the core observe→think→act loop that drives all OS
automation. Uses hybrid grounding (UIA + vision) and multi-LLM
support via litellm.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Callable, Optional

import litellm

from agenticos.actions.compositor import Action, ActionCompositor, ActionResult, ActionType
from agenticos.agent.base import (
    AgentState,
    AgentStatus,
    BaseAgent,
    Observation,
    StepResult,
)
from agenticos.grounding.accessibility import UIAGrounder, UIElement
from agenticos.observation.recorder import GifRecorder
from agenticos.observation.screenshot import ScreenCapture, Screenshot
from agenticos.utils.config import AgenticOSConfig, GroundingMode, get_config, resolve_api_key
from agenticos.utils.exceptions import LLMError, MaxStepsExceeded

# System prompt for the navigator agent
NAVIGATOR_SYSTEM_PROMPT = """You are AgenticOS, an AI agent that controls a Windows desktop computer.
You can see the screen via screenshots and interact with it using mouse clicks, keyboard input, and shell commands.

Your capabilities:
1. **Click** on UI elements at specific (x, y) coordinates
2. **Type text** into focused fields
3. **Press keys** (enter, tab, escape, etc.) and hotkey combos (ctrl+s, alt+f4, etc.)
4. **Scroll** at specific positions
5. **Run shell commands** via PowerShell
6. **Open applications** by name
7. **Manage windows** (focus, minimize, maximize, close)

## How to respond

Analyze the current screenshot and UI elements, then decide the next action.
Respond with a JSON object:

```json
{
  "thought": "Brief reasoning about what you see and what to do next",
  "action": {
    "type": "click|type_text|press_key|hotkey|scroll|shell|open_app|focus_window|close_window|wait",
    "params": { ... }
  },
  "is_complete": false
}
```

### Action parameter formats:
- click: {"x": 500, "y": 300}
- double_click: {"x": 500, "y": 300}
- right_click: {"x": 500, "y": 300}
- type_text: {"text": "Hello World"}
- press_key: {"key": "enter"}
- hotkey: {"keys": ["ctrl", "s"]}
- scroll: {"x": 500, "y": 300, "clicks": -3}
- shell: {"command": "Get-ChildItem"}
- open_app: {"app_name": "notepad"}
- focus_window: {"title": "Notepad"}
- close_window: {"title": "Notepad"}
- wait: {"seconds": 2}

When the task is fully complete, set "is_complete": true.

## Rules
- Be PRECISE with coordinates — click exactly on the target element
- Use the UI element list to find correct coordinates
- Wait after actions that trigger loading or transitions
- If something doesn't work, try an alternative approach
- For text input, first click on the target field, then type
- Always verify your actions had the expected effect in the next observation
"""


class NavigatorAgent(BaseAgent):
    """Main navigation agent implementing the ReAct loop.

    Orchestrates screen observation, LLM reasoning, and action execution
    to complete user tasks on the Windows desktop.

    Example:
        >>> agent = NavigatorAgent()
        >>> state = await agent.navigate("Open Notepad and type 'Hello World'")
        >>> print(f"Success: {state.success}, Steps: {state.total_steps}")
    """

    def __init__(
        self,
        config: Optional[AgenticOSConfig] = None,
        on_step: Optional[Callable[[StepResult], None]] = None,
        on_status: Optional[Callable[[AgentStatus], None]] = None,
    ) -> None:
        """Initialize the navigator agent.

        Args:
            config: Configuration (uses defaults if None).
            on_step: Callback invoked after each step (for CLI streaming).
            on_status: Callback invoked on status changes.
        """
        self.config = config or get_config()
        self.on_step = on_step
        self.on_status = on_status

        # Initialize components
        self.screen = ScreenCapture(
            monitor=self.config.screenshot_monitor,
            scale=self.config.screenshot_scale,
        )
        self.grounder = UIAGrounder()
        self.compositor = ActionCompositor()
        self.recorder: Optional[GifRecorder] = None

        # Vision grounder (lazy init)
        self._vision_grounder = None

        # API key
        self._api_key = resolve_api_key(self.config)

    def _get_vision_grounder(self):
        """Lazy-initialize vision grounder."""
        if self._vision_grounder is None:
            from agenticos.grounding.visual import VisionGrounder
            self._vision_grounder = VisionGrounder(
                model=self.config.llm_model,
                api_key=self._api_key,
            )
        return self._vision_grounder

    async def observe(self) -> Observation:
        """Capture current screen state with hybrid grounding.

        Returns:
            Observation with screenshot, UI elements, and metadata.
        """
        # Capture screenshot
        screenshot = self.screen.grab()

        # Get UI elements via UIA
        ui_elements: list[UIElement] = []
        active_window = ""

        try:
            ui_elements = self.grounder.detect_focused_window()
            # Get active window title
            from agenticos.actions.window import WindowManager
            wm = WindowManager()
            fg = wm.get_foreground()
            if fg:
                active_window = fg.title
        except Exception:
            pass  # UIA may fail on some windows

        # Hybrid fallback: if UIA found too few elements, use vision
        if (
            self.config.grounding_mode == GroundingMode.HYBRID
            and len(ui_elements) < self.config.uia_min_elements
        ):
            try:
                vision = self._get_vision_grounder()
                vision_elements = await vision.detect(screenshot)
                # Merge: vision elements fill gaps
                if len(vision_elements) > len(ui_elements):
                    ui_elements = vision_elements
            except Exception:
                pass  # Vision fallback is best-effort

        return Observation(
            screenshot=screenshot,
            ui_elements=ui_elements,
            active_window=active_window,
            timestamp=time.time(),
        )

    async def think(
        self,
        observation: Observation,
        task: str,
        history: list[StepResult],
    ) -> tuple[Action, str, bool]:
        """Use LLM to decide the next action.

        Args:
            observation: Current screen observation.
            task: User's task description.
            history: Previous steps.

        Returns:
            Tuple of (action, reasoning, is_complete).

        Raises:
            LLMError: If LLM call fails.
        """
        # Build message with screenshot + UI elements
        messages = self._build_messages(observation, task, history)

        try:
            response = await litellm.acompletion(
                model=self.config.llm_model,
                messages=messages,
                max_tokens=self.config.llm_max_tokens,
                temperature=self.config.llm_temperature,
                api_key=self._api_key,
            )

            content = response.choices[0].message.content
            return self._parse_llm_response(content)

        except Exception as e:
            raise LLMError(f"LLM call failed: {e}") from e

    async def act(self, action: Action) -> ActionResult:
        """Execute an action on the OS.

        Args:
            action: The action to execute.

        Returns:
            ActionResult.
        """
        # Add annotation to GIF recorder
        if self.recorder and self.recorder.is_recording:
            desc = action.description or f"{action.type.value}: {action.params}"
            self.recorder.add_annotation(desc)

        result = self.compositor.execute(action)

        # Clear annotation after action
        if self.recorder and self.recorder.is_recording:
            await asyncio.sleep(0.5)
            self.recorder.clear_annotation()

        return result

    async def navigate(self, task: str) -> AgentState:
        """Execute a complete task using the ReAct loop.

        Args:
            task: Natural language task description.

        Returns:
            AgentState with full execution history.
        """
        state = AgentState(task=task, start_time=time.time())
        self._set_status(state, AgentStatus.OBSERVING)

        # Start GIF recording if enabled
        if self.config.auto_record_gif:
            self.recorder = GifRecorder(
                fps=self.config.gif_fps,
                max_duration=self.config.gif_max_duration,
            )
            self.recorder.start()

        try:
            for step_num in range(1, self.config.max_steps + 1):
                step_start = time.perf_counter()

                # 1. OBSERVE
                self._set_status(state, AgentStatus.OBSERVING)
                observation = await self.observe()

                # 2. THINK
                self._set_status(state, AgentStatus.THINKING)
                action, thought, is_complete = await self.think(
                    observation, task, state.steps
                )

                # 3. Check if complete
                if is_complete:
                    step_result = StepResult(
                        step_number=step_num,
                        observation=observation,
                        thought=thought,
                        is_complete=True,
                        elapsed_ms=(time.perf_counter() - step_start) * 1000,
                    )
                    state.steps.append(step_result)
                    if self.on_step:
                        self.on_step(step_result)
                    break

                # 4. ACT
                self._set_status(state, AgentStatus.ACTING)
                action_result = await self.act(action)

                step_result = StepResult(
                    step_number=step_num,
                    observation=observation,
                    thought=thought,
                    action=action,
                    action_result=action_result,
                    elapsed_ms=(time.perf_counter() - step_start) * 1000,
                )
                state.steps.append(step_result)

                if self.on_step:
                    self.on_step(step_result)

                # Brief pause between steps
                await asyncio.sleep(0.3)

            # Determine final status
            if state.steps and state.steps[-1].is_complete:
                state.success = True
                self._set_status(state, AgentStatus.COMPLETED)
            else:
                state.success = False
                state.error = "Max steps reached without completing the task"
                self._set_status(state, AgentStatus.FAILED)

        except Exception as e:
            state.success = False
            state.error = str(e)
            self._set_status(state, AgentStatus.FAILED)

        finally:
            state.end_time = time.time()
            state.total_steps = len(state.steps)

            # Stop GIF recording
            if self.recorder:
                self.recorder.stop()

        return state

    def save_recording(self, path: str) -> Optional[str]:
        """Save the GIF recording of the last session.

        Args:
            path: Output file path.

        Returns:
            Path to saved GIF, or None if no recording.
        """
        if self.recorder and self.recorder.frame_count > 0:
            return self.recorder.save(path)
        return None

    def _build_messages(
        self,
        observation: Observation,
        task: str,
        history: list[StepResult],
    ) -> list[dict[str, Any]]:
        """Build LLM messages with screenshot and context.

        Args:
            observation: Current observation.
            task: User task.
            history: Step history.

        Returns:
            List of message dicts for litellm.
        """
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": NAVIGATOR_SYSTEM_PROMPT},
        ]

        # Add history summary (last 3 steps to keep context manageable)
        if history:
            recent = history[-3:]
            history_text = "Previous steps:\n"
            for step in recent:
                action_desc = ""
                if step.action:
                    action_desc = f" → {step.action.type.value}({step.action.params})"
                result_desc = ""
                if step.action_result:
                    status = "✓" if step.action_result.success else "✗"
                    result_desc = f" [{status}]"
                history_text += f"  Step {step.step_number}: {step.thought[:100]}{action_desc}{result_desc}\n"

            messages.append({"role": "user", "content": history_text})
            messages.append({"role": "assistant", "content": "Understood. I'll continue with the task."})

        # Build current observation message
        content: list[dict[str, Any]] = []

        # Task description
        task_text = f"Task: {task}\n\n"
        task_text += f"Current step: {len(history) + 1}/{self.config.max_steps}\n"
        task_text += f"Active window: {observation.active_window}\n\n"

        # UI elements
        task_text += observation.elements_summary()
        task_text += "\n\nAnalyze the screenshot and decide the next action."

        content.append({"type": "text", "text": task_text})

        # Add screenshot
        if observation.screenshot:
            base64_img = observation.screenshot.to_base64(max_dimension=1568)
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{base64_img}"},
            })

        messages.append({"role": "user", "content": content})
        return messages

    def _parse_llm_response(self, content: str) -> tuple[Action, str, bool]:
        """Parse LLM JSON response into an Action.

        Args:
            content: Raw LLM response text.

        Returns:
            Tuple of (action, thought, is_complete).
        """
        # Strip markdown code blocks if present
        content = content.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1])

        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            # Try to extract JSON from mixed text
            import re
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                data = json.loads(json_match.group())
            else:
                return (
                    Action.wait(1.0, "Parsing error — waiting"),
                    f"Failed to parse response: {content[:200]}",
                    False,
                )

        thought = data.get("thought", "")
        is_complete = data.get("is_complete", False)

        if is_complete:
            return Action.wait(0, "Task complete"), thought, True

        action_data = data.get("action", {})
        action_type = action_data.get("type", "wait")
        params = action_data.get("params", {})

        try:
            at = ActionType(action_type)
        except ValueError:
            at = ActionType.WAIT
            params = {"seconds": 1.0}

        action = Action(
            type=at,
            params=params,
            description=thought[:100],
        )

        return action, thought, False

    def _set_status(self, state: AgentState, status: AgentStatus) -> None:
        """Update agent status and notify callback.

        Args:
            state: Current agent state.
            status: New status.
        """
        state.status = status
        if self.on_status:
            self.on_status(status)
