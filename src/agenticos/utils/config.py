"""Configuration management for AgenticOS."""

from __future__ import annotations

import os
from enum import Enum
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class LLMProvider(str, Enum):
    """Supported LLM providers."""
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    OLLAMA = "ollama"
    LITELLM = "litellm"


class GroundingMode(str, Enum):
    """Screen understanding strategy."""
    UIA = "uia"
    VISION = "vision"
    OCR = "ocr"
    HYBRID = "hybrid"


class AgenticOSConfig(BaseSettings):
    """Main configuration for AgenticOS.

    All settings can be overridden via environment variables with the
    AGENTICOS_ prefix (e.g., AGENTICOS_LLM_MODEL=gpt-4o).
    """

    model_config = {"env_prefix": "AGENTICOS_", "env_file": ".env", "extra": "ignore"}

    # LLM Configuration
    llm_provider: LLMProvider = Field(
        default=LLMProvider.LITELLM,
        description="LLM provider to use",
    )
    llm_model: str = Field(
        default="claude-sonnet-4-20250514",
        description="Model name/ID for the LLM",
    )
    llm_api_key: Optional[str] = Field(
        default=None,
        description="API key for the LLM provider (falls back to provider-specific env vars)",
    )
    llm_base_url: Optional[str] = Field(
        default=None,
        description="Base URL for the LLM API (for local models)",
    )
    llm_temperature: float = Field(
        default=0.1,
        description="Temperature for LLM generation",
        ge=0.0,
        le=2.0,
    )
    llm_max_tokens: int = Field(
        default=4096,
        description="Maximum tokens for LLM response",
    )

    # Agent Configuration
    max_steps: int = Field(
        default=15,
        description="Maximum steps per agent task",
    )
    confirm_actions: bool = Field(
        default=True,
        description="Require user confirmation before executing actions",
    )
    auto_record_gif: bool = Field(
        default=True,
        description="Automatically record GIF of agent sessions",
    )
    gif_fps: int = Field(
        default=5,
        description="Frames per second for GIF recording",
    )
    gif_max_duration: int = Field(
        default=60,
        description="Maximum GIF recording duration in seconds",
    )

    # Grounding Configuration
    grounding_mode: GroundingMode = Field(
        default=GroundingMode.HYBRID,
        description="Screen understanding strategy",
    )
    uia_min_elements: int = Field(
        default=3,
        description="Minimum UIA elements before falling back to vision",
    )

    # Screenshot Configuration
    screenshot_scale: float = Field(
        default=1.0,
        description="Scale factor for screenshots (0.5 = half resolution)",
    )
    screenshot_monitor: int = Field(
        default=1,
        description="Monitor index for screenshots (1 = primary)",
    )

    # MCP Configuration
    mcp_transport: str = Field(
        default="stdio",
        description="MCP transport protocol (stdio or streamable-http)",
    )
    mcp_port: int = Field(
        default=8765,
        description="Port for HTTP MCP transport",
    )

    # Safety Configuration
    blocked_commands: list[str] = Field(
        default_factory=lambda: [
            "format",
            "del /s",
            "rmdir /s",
            "reg delete",
            "bcdedit",
            "diskpart",
            "shutdown",
        ],
        description="Shell commands that are blocked for safety",
    )

    # Evaluation
    benchmark_dir: str = Field(
        default="benchmarks",
        description="Directory containing benchmark definitions",
    )
    results_dir: str = Field(
        default="benchmarks/results",
        description="Directory for benchmark results",
    )


def get_config() -> AgenticOSConfig:
    """Load and return the AgenticOS configuration.

    Returns:
        AgenticOSConfig with values from env vars and defaults.
    """
    return AgenticOSConfig()


# Convenience: resolve API key from multiple sources
def resolve_api_key(config: AgenticOSConfig) -> Optional[str]:
    """Resolve the API key from config or well-known environment variables.

    Args:
        config: The AgenticOS configuration.

    Returns:
        The API key string, or None if not found.
    """
    if config.llm_api_key:
        return config.llm_api_key

    env_map = {
        LLMProvider.ANTHROPIC: "ANTHROPIC_API_KEY",
        LLMProvider.OPENAI: "OPENAI_API_KEY",
    }

    env_var = env_map.get(config.llm_provider)
    if env_var:
        return os.environ.get(env_var)

    return None
