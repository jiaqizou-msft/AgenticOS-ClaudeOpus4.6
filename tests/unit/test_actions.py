"""Unit tests for action modules."""

from unittest.mock import MagicMock, patch

import pytest

from agenticos.actions.compositor import Action, ActionCompositor, ActionResult, ActionType
from agenticos.actions.shell import ShellExecutor, ShellResult
from agenticos.utils.exceptions import ActionBlockedError


class TestAction:
    """Tests for the Action data class."""

    def test_click_factory(self):
        action = Action.click(500, 300, "Click button")
        assert action.type == ActionType.CLICK
        assert action.params == {"x": 500, "y": 300}
        assert action.description == "Click button"

    def test_type_text_factory(self):
        action = Action.type_text("Hello", "Type greeting")
        assert action.type == ActionType.TYPE_TEXT
        assert action.params == {"text": "Hello"}

    def test_hotkey_factory(self):
        action = Action.hotkey("ctrl", "s", description="Save")
        assert action.type == ActionType.HOTKEY
        assert action.params == {"keys": ["ctrl", "s"]}

    def test_shell_factory(self):
        action = Action.shell("Get-Date", "Get date")
        assert action.type == ActionType.SHELL
        assert action.params == {"command": "Get-Date"}

    def test_wait_factory(self):
        action = Action.wait(2.0, "Wait for loading")
        assert action.type == ActionType.WAIT
        assert action.params == {"seconds": 2.0}


class TestShellExecutor:
    """Tests for the ShellExecutor."""

    def test_init(self):
        shell = ShellExecutor(blocked_commands=["format", "del /s"])
        assert "format" in shell.blocked_commands

    def test_blocked_command(self):
        shell = ShellExecutor(blocked_commands=["format", "del /s"])
        with pytest.raises(ActionBlockedError):
            shell.run("format c:")

    def test_blocked_command_case_insensitive(self):
        shell = ShellExecutor(blocked_commands=["shutdown"])
        with pytest.raises(ActionBlockedError):
            shell.run("SHUTDOWN /s")

    def test_run_echo(self):
        """Test running a simple echo command."""
        shell = ShellExecutor(blocked_commands=[])
        result = shell.run("echo hello", shell="cmd")
        assert result.success
        assert "hello" in result.stdout.lower()

    def test_run_powershell(self):
        """Test running a PowerShell command."""
        shell = ShellExecutor(blocked_commands=[])
        result = shell.run("Write-Output 'test123'")
        assert result.success
        assert "test123" in result.stdout

    def test_shell_result_properties(self):
        result = ShellResult(
            command="test",
            stdout="output",
            stderr="",
            return_code=0,
            elapsed_ms=100.0,
        )
        assert result.success is True
        assert result.output == "output"

    def test_shell_result_failure(self):
        result = ShellResult(
            command="test",
            stdout="",
            stderr="error msg",
            return_code=1,
            elapsed_ms=50.0,
        )
        assert result.success is False
        assert "error msg" in result.output


class TestActionCompositor:
    """Tests for the ActionCompositor."""

    @patch("agenticos.actions.compositor.ActionCompositor._dispatch")
    def test_execute_success(self, mock_dispatch):
        mock_dispatch.return_value = None
        compositor = ActionCompositor()
        action = Action.click(100, 200)
        result = compositor.execute(action)
        assert result.success
        assert result.retry_count == 0

    @patch("agenticos.actions.compositor.ActionCompositor._dispatch")
    def test_execute_with_retry(self, mock_dispatch):
        from agenticos.utils.exceptions import ActionError
        mock_dispatch.side_effect = [ActionError("fail"), ActionError("fail"), None]
        compositor = ActionCompositor(max_retries=2, retry_delay=0.01)
        action = Action.click(100, 200)
        result = compositor.execute(action)
        assert result.success
        assert result.retry_count == 2

    def test_execute_wait(self):
        compositor = ActionCompositor()
        action = Action.wait(0.01, "Brief wait")
        result = compositor.execute(action)
        assert result.success
