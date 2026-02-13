"""Shared fixtures for AgenticOS tests."""

import pytest

from agenticos.utils.config import AgenticOSConfig, GroundingMode


@pytest.fixture
def config():
    """A default test config."""
    return AgenticOSConfig(
        max_steps=5,
        confirm_actions=False,
        grounding_mode=GroundingMode.UIA_ONLY,
    )


@pytest.fixture
def mock_screenshot():
    """A mock screenshot for testing."""
    from unittest.mock import MagicMock
    from agenticos.observation.screenshot import Screenshot

    mock = MagicMock(spec=Screenshot)
    mock.width = 1920
    mock.height = 1080
    mock.to_base64.return_value = "base64data"
    return mock
