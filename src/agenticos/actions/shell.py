"""Shell command executor.

Runs PowerShell and CMD commands with safety checks and output capture.
"""

from __future__ import annotations

import asyncio
import subprocess
import time
from dataclasses import dataclass
from typing import Optional

from agenticos.utils.config import get_config
from agenticos.utils.exceptions import ActionBlockedError, ActionError


@dataclass
class ShellResult:
    """Result of a shell command execution.

    Attributes:
        command: The command that was executed.
        stdout: Standard output.
        stderr: Standard error.
        return_code: Process return code.
        elapsed_ms: Execution time in milliseconds.
    """
    command: str
    stdout: str
    stderr: str
    return_code: int
    elapsed_ms: float

    @property
    def success(self) -> bool:
        """Whether the command succeeded (return code 0)."""
        return self.return_code == 0

    @property
    def output(self) -> str:
        """Combined stdout + stderr output."""
        parts = []
        if self.stdout:
            parts.append(self.stdout)
        if self.stderr:
            parts.append(f"STDERR: {self.stderr}")
        return "\n".join(parts)


class ShellExecutor:
    """Executes shell commands with safety checks.

    Supports PowerShell and CMD commands with configurable blocklists,
    timeouts, and output capture.

    Example:
        >>> shell = ShellExecutor()
        >>> result = shell.run("Get-Process | Select-Object -First 5")
        >>> print(result.stdout)
        >>> result = shell.run("echo Hello", shell="cmd")
    """

    def __init__(
        self,
        default_shell: str = "powershell",
        timeout: int = 30,
        blocked_commands: Optional[list[str]] = None,
    ) -> None:
        """Initialize shell executor.

        Args:
            default_shell: Default shell ('powershell' or 'cmd').
            timeout: Default command timeout in seconds.
            blocked_commands: Commands to block (uses config if None).
        """
        self.default_shell = default_shell
        self.timeout = timeout

        if blocked_commands is not None:
            self.blocked_commands = blocked_commands
        else:
            config = get_config()
            self.blocked_commands = config.blocked_commands

    def run(
        self,
        command: str,
        shell: Optional[str] = None,
        timeout: Optional[int] = None,
        cwd: Optional[str] = None,
    ) -> ShellResult:
        """Execute a shell command synchronously.

        Args:
            command: Command string to execute.
            shell: Shell to use ('powershell' or 'cmd'). Defaults to default_shell.
            timeout: Timeout in seconds.
            cwd: Working directory.

        Returns:
            ShellResult with output and status.

        Raises:
            ActionBlockedError: If command matches a blocked pattern.
            ActionError: If execution fails.
        """
        # Safety check
        self._check_blocked(command)

        shell = shell or self.default_shell
        timeout = timeout or self.timeout

        try:
            start = time.perf_counter()

            if shell == "powershell":
                cmd = ["powershell", "-NoProfile", "-Command", command]
            else:
                cmd = ["cmd", "/c", command]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=cwd,
            )

            elapsed_ms = (time.perf_counter() - start) * 1000

            return ShellResult(
                command=command,
                stdout=result.stdout.strip(),
                stderr=result.stderr.strip(),
                return_code=result.returncode,
                elapsed_ms=elapsed_ms,
            )

        except subprocess.TimeoutExpired:
            raise ActionError(
                f"Command timed out after {timeout}s: {command}"
            )
        except Exception as e:
            raise ActionError(f"Failed to execute command: {e}") from e

    async def run_async(
        self,
        command: str,
        shell: Optional[str] = None,
        timeout: Optional[int] = None,
        cwd: Optional[str] = None,
    ) -> ShellResult:
        """Execute a shell command asynchronously.

        Args:
            command: Command string to execute.
            shell: Shell to use.
            timeout: Timeout in seconds.
            cwd: Working directory.

        Returns:
            ShellResult with output and status.
        """
        self._check_blocked(command)

        shell = shell or self.default_shell
        timeout = timeout or self.timeout

        try:
            start = time.perf_counter()

            if shell == "powershell":
                cmd = f"powershell -NoProfile -Command {command}"
            else:
                cmd = f"cmd /c {command}"

            process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout,
            )

            elapsed_ms = (time.perf_counter() - start) * 1000

            return ShellResult(
                command=command,
                stdout=stdout.decode().strip() if stdout else "",
                stderr=stderr.decode().strip() if stderr else "",
                return_code=process.returncode or 0,
                elapsed_ms=elapsed_ms,
            )

        except asyncio.TimeoutError:
            raise ActionError(f"Command timed out after {timeout}s: {command}")
        except Exception as e:
            raise ActionError(f"Failed to execute command: {e}") from e

    def open_application(self, app_name: str) -> ShellResult:
        """Open an application by name.

        Args:
            app_name: Application name or path (e.g., 'notepad', 'calc').

        Returns:
            ShellResult.
        """
        return self.run(f"Start-Process '{app_name}'")

    def _check_blocked(self, command: str) -> None:
        """Check if a command matches any blocked pattern.

        Args:
            command: Command to check.

        Raises:
            ActionBlockedError: If command is blocked.
        """
        cmd_lower = command.lower().strip()
        for blocked in self.blocked_commands:
            if blocked.lower() in cmd_lower:
                raise ActionBlockedError(
                    f"Command blocked by safety policy: '{command}' "
                    f"(matches blocked pattern: '{blocked}')"
                )
