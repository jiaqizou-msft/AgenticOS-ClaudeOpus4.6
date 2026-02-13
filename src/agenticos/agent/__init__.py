"""Core agent modules for AgenticOS."""

from agenticos.agent.base import BaseAgent, AgentState, Observation, StepResult
# Lazy-import heavy modules (NavigatorAgent, TaskPlanner) that depend on litellm
# to avoid import errors in lightweight scripts like human_teach.py
try:
    from agenticos.agent.navigator import NavigatorAgent
    from agenticos.agent.planner import TaskPlanner
except ImportError:
    NavigatorAgent = None  # type: ignore[assignment,misc]
    TaskPlanner = None  # type: ignore[assignment,misc]
from agenticos.agent.state_validator import StateValidator, StateSnapshot, ValidationResult
from agenticos.agent.recovery import RecoveryManager, RecoveryStrategy, RecoveryAction
from agenticos.agent.step_memory import StepMemory, CachedStep, Episode
from agenticos.agent.reinforcement import QLearner, RewardSignal, Transition, ActionStats
from agenticos.agent.human_teacher import HumanTeacher, LearnedPattern, DemoRecording, TEACHING_TOPICS

__all__ = [
    "BaseAgent",
    "AgentState",
    "Observation",
    "StepResult",
    "NavigatorAgent",
    "TaskPlanner",
    "StateValidator",
    "StateSnapshot",
    "ValidationResult",
    "RecoveryManager",
    "RecoveryStrategy",
    "RecoveryAction",
    "StepMemory",
    "CachedStep",
    "Episode",
    "QLearner",
    "RewardSignal",
    "Transition",
    "ActionStats",
    "HumanTeacher",
    "LearnedPattern",
    "DemoRecording",
    "TEACHING_TOPICS",
]
