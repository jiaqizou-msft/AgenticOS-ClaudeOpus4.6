"""Unit tests for utility modules."""

import pytest

from agenticos.utils.config import AgenticOSConfig, GroundingMode, LLMProvider
from agenticos.utils.exceptions import (
    ActionBlockedError,
    ActionError,
    AgenticOSError,
    GroundingError,
    LLMError,
    MaxStepsExceeded,
    ScreenCaptureError,
)


class TestConfig:
    """Tests for the AgenticOSConfig."""

    def test_defaults(self):
        config = AgenticOSConfig()
        assert config.max_steps == 15
        assert config.grounding_mode == GroundingMode.HYBRID
        assert config.llm_provider == LLMProvider.ANTHROPIC
        assert config.confirm_actions is True

    def test_custom_config(self):
        config = AgenticOSConfig(
            max_steps=25,
            grounding_mode=GroundingMode.UIA_ONLY,
            confirm_actions=False,
        )
        assert config.max_steps == 25
        assert config.grounding_mode == GroundingMode.UIA_ONLY
        assert config.confirm_actions is False


class TestExceptions:
    """Tests for custom exceptions."""

    def test_hierarchy(self):
        assert issubclass(GroundingError, AgenticOSError)
        assert issubclass(ActionError, AgenticOSError)
        assert issubclass(ActionBlockedError, ActionError)
        assert issubclass(LLMError, AgenticOSError)
        assert issubclass(MaxStepsExceeded, AgenticOSError)
        assert issubclass(ScreenCaptureError, AgenticOSError)

    def test_raise_blocked(self):
        with pytest.raises(ActionBlockedError):
            raise ActionBlockedError("shutdown is blocked")

    def test_max_steps(self):
        with pytest.raises(MaxStepsExceeded):
            raise MaxStepsExceeded("Exceeded 15 steps")
