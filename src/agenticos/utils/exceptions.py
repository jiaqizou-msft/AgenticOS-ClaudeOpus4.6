"""Custom exceptions for AgenticOS."""

from __future__ import annotations


class AgenticOSError(Exception):
    """Base exception for AgenticOS."""


class GroundingError(AgenticOSError):
    """Failed to detect UI elements on screen."""


class ActionError(AgenticOSError):
    """Failed to execute an OS action."""


class ActionBlockedError(ActionError):
    """Action was blocked by safety gate."""


class LLMError(AgenticOSError):
    """Error communicating with the LLM."""


class MaxStepsExceeded(AgenticOSError):
    """Agent exceeded maximum allowed steps."""


class ScreenCaptureError(AgenticOSError):
    """Failed to capture screen."""


class MCPError(AgenticOSError):
    """MCP server/client error."""
