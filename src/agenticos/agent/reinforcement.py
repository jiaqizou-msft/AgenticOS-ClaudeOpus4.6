"""Reinforcement learning for action optimization.

Implements a lightweight RL approach with:
- Reward signals from state validation (success/drift/no-op/recovery)
- Q-value tracking per (state_context, action_type) pair
- Policy optimization: prefer actions with higher historical reward
- Exploration vs exploitation via epsilon-greedy on action coordinates
- Persistent learning across sessions via JSON storage

The RL layer sits between the LLM output and action execution, adjusting
confidence in LLM suggestions based on accumulated experience.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ── Reward constants ──
REWARD_SUCCESS = 1.0          # Action achieved goal state
REWARD_STATE_CHANGED = 0.3    # Action produced visible change (good sign)
REWARD_NO_CHANGE = -0.3       # Action had no effect
REWARD_DRIFT = -0.7           # Action caused unexpected drift
REWARD_RECOVERY_NEEDED = -1.0 # Action required recovery intervention
REWARD_DONE_SUCCESS = 2.0     # Task completed successfully
REWARD_DONE_FAIL = -1.5       # Task ended in failure
REWARD_PARSE_FAIL = -0.2      # LLM output couldn't be parsed


@dataclass
class Transition:
    """A single (state, action, reward, next_state) transition."""
    state_key: str           # Hash of UI context before action
    action_type: str         # e.g. "click", "drag", "type_text"
    action_key: str          # Hash of specific action params
    reward: float
    next_state_key: str      # Hash of UI context after action
    timestamp: float = 0.0

    @property
    def sa_key(self) -> str:
        """State-action key for Q-table lookup."""
        return f"{self.state_key}:{self.action_type}"


@dataclass
class ActionStats:
    """Statistics for a (state, action_type) pair."""
    total_reward: float = 0.0
    count: int = 0
    successes: int = 0
    failures: int = 0
    last_reward: float = 0.0
    avg_reward: float = 0.0

    def update(self, reward: float) -> None:
        self.count += 1
        self.total_reward += reward
        self.last_reward = reward
        self.avg_reward = self.total_reward / self.count
        if reward > 0:
            self.successes += 1
        elif reward < -0.5:
            self.failures += 1


class RewardSignal:
    """Computes reward from state validation results."""

    @staticmethod
    def compute(
        action_type: str,
        exec_success: bool,
        state_changed: bool,
        drift_detected: bool,
        recovery_needed: bool,
        task_done: bool = False,
        task_success: bool = False,
    ) -> float:
        """Compute scalar reward from post-action signals.

        Args:
            action_type: The type of action executed.
            exec_success: Whether the action executor reported success.
            state_changed: Whether UI state visibly changed.
            drift_detected: Whether state validation detected drift.
            recovery_needed: Whether recovery was triggered.
            task_done: Whether the task is now complete.
            task_success: Whether the task was successful.

        Returns:
            Scalar reward value.
        """
        if task_done:
            return REWARD_DONE_SUCCESS if task_success else REWARD_DONE_FAIL

        if not exec_success:
            return REWARD_DRIFT

        reward = 0.0

        if recovery_needed:
            reward += REWARD_RECOVERY_NEEDED
        elif drift_detected:
            reward += REWARD_DRIFT
        elif state_changed:
            reward += REWARD_STATE_CHANGED
            # Bonus for expected actions that produced change
            if action_type in ("click", "type_text", "drag", "open_app"):
                reward += 0.2  # Extra credit — these should produce change
        else:
            # No change — might be OK for wait/scroll, bad for click
            if action_type in ("click", "type_text", "drag"):
                reward += REWARD_NO_CHANGE
            else:
                reward += 0.0  # Neutral for wait/press_key

        return max(-2.0, min(2.0, reward))  # Clamp to [-2, 2]


class QLearner:
    """Tabular Q-learning for action-type preferences per context.

    Tracks Q(state_context, action_type) values and uses them to:
    - Warn when LLM suggests an action that historically fails in this context
    - Suggest alternative action types when current approach keeps failing
    - Provide confidence scores for action selection

    This is NOT replacing the LLM — it's a lightweight overlay that
    nudges the LLM's decisions based on accumulated experience.
    """

    def __init__(
        self,
        learning_rate: float = 0.15,
        discount_factor: float = 0.9,
        persist_path: Optional[str] = None,
    ) -> None:
        """Initialize Q-learner.

        Args:
            learning_rate: Alpha — how much new info overrides old.
            discount_factor: Gamma — importance of future rewards.
            persist_path: Path to save/load Q-table JSON.
        """
        self.alpha = learning_rate
        self.gamma = discount_factor
        self._persist_path = Path(persist_path) if persist_path else None

        # Q-table: state_key -> {action_type -> Q-value}
        self._q_table: dict[str, dict[str, float]] = defaultdict(
            lambda: defaultdict(float)
        )
        # Stats: sa_key -> ActionStats
        self._stats: dict[str, ActionStats] = defaultdict(ActionStats)
        # Transition history (last N for analysis)
        self._history: list[Transition] = []
        self._max_history = 500
        # Cumulative metrics
        self._total_reward = 0.0
        self._episode_rewards: list[float] = []  # Per-task cumulative reward

        if self._persist_path and self._persist_path.exists():
            self._load()

    @staticmethod
    def make_state_key(window_title: str, element_names: list[str]) -> str:
        """Create a stable state key from UI context (intent-agnostic)."""
        title = window_title.strip().lower()
        elems = sorted(set(n.strip().lower() for n in element_names[:8] if n))[:5]
        raw = f"{title}|{'|'.join(elems)}"
        return hashlib.sha256(raw.encode()).hexdigest()[:12]

    def get_q_value(self, state_key: str, action_type: str) -> float:
        """Get Q(state, action_type)."""
        return self._q_table[state_key].get(action_type, 0.0)

    def get_best_action_type(self, state_key: str) -> Optional[str]:
        """Get the action type with highest Q-value for this state."""
        actions = self._q_table.get(state_key, {})
        if not actions:
            return None
        return max(actions, key=actions.get)

    def get_action_confidence(self, state_key: str, action_type: str) -> float:
        """Get confidence score [0, 1] for an action in this state.

        High confidence = historically successful, low = historically bad.
        """
        q = self.get_q_value(state_key, action_type)
        # Sigmoid to map Q-value to [0, 1]
        return 1.0 / (1.0 + math.exp(-q))

    def should_warn(self, state_key: str, action_type: str) -> tuple[bool, str]:
        """Check if the LLM's proposed action has a bad track record here.

        Returns:
            (should_warn, warning_message)
        """
        sa_key = f"{state_key}:{action_type}"
        stats = self._stats.get(sa_key)
        if not stats or stats.count < 2:
            return False, ""

        if stats.avg_reward < -0.3 and stats.count >= 3:
            best = self.get_best_action_type(state_key)
            alt = f" Consider '{best}' instead." if best and best != action_type else ""
            return True, (
                f"RL WARNING: '{action_type}' has avg reward {stats.avg_reward:.2f} "
                f"in this context ({stats.failures}/{stats.count} failures).{alt}"
            )
        return False, ""

    def update(self, transition: Transition) -> None:
        """Update Q-table with a new transition (TD-learning).

        Q(s,a) ← Q(s,a) + α * [r + γ * max_a' Q(s',a') - Q(s,a)]
        """
        s, a = transition.state_key, transition.action_type
        r = transition.reward
        s_next = transition.next_state_key

        # Current Q
        q_current = self._q_table[s].get(a, 0.0)

        # Best future Q
        next_actions = self._q_table.get(s_next, {})
        q_next_max = max(next_actions.values()) if next_actions else 0.0

        # TD update
        td_target = r + self.gamma * q_next_max
        q_new = q_current + self.alpha * (td_target - q_current)
        self._q_table[s][a] = q_new

        # Update stats
        sa_key = transition.sa_key
        self._stats[sa_key].update(r)

        # Track history
        self._history.append(transition)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        self._total_reward += r

        # Auto-save periodically
        if self._persist_path and len(self._history) % 10 == 0:
            self._save()

    def end_episode(self, total_reward: float) -> None:
        """Mark end of a task episode for tracking."""
        self._episode_rewards.append(total_reward)
        if self._persist_path:
            self._save()

    @property
    def stats(self) -> dict:
        """Summary statistics."""
        return {
            "q_table_size": sum(len(v) for v in self._q_table.values()),
            "states_seen": len(self._q_table),
            "total_transitions": len(self._history),
            "total_reward": round(self._total_reward, 2),
            "episodes": len(self._episode_rewards),
            "avg_episode_reward": (
                round(sum(self._episode_rewards) / len(self._episode_rewards), 2)
                if self._episode_rewards else 0.0
            ),
        }

    def get_improvement_trend(self, window: int = 5) -> str:
        """Check if performance is improving over recent episodes."""
        if len(self._episode_rewards) < window * 2:
            return "insufficient_data"
        recent = self._episode_rewards[-window:]
        older = self._episode_rewards[-window * 2:-window]
        avg_recent = sum(recent) / len(recent)
        avg_older = sum(older) / len(older)
        if avg_recent > avg_older + 0.5:
            return "improving"
        elif avg_recent < avg_older - 0.5:
            return "declining"
        return "stable"

    def _save(self) -> None:
        """Persist Q-table and stats to JSON."""
        if not self._persist_path:
            return
        self._persist_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "q_table": {
                s: dict(actions) for s, actions in self._q_table.items()
            },
            "stats": {
                k: {
                    "total_reward": v.total_reward,
                    "count": v.count,
                    "successes": v.successes,
                    "failures": v.failures,
                    "avg_reward": v.avg_reward,
                }
                for k, v in self._stats.items()
            },
            "episode_rewards": self._episode_rewards,
            "total_reward": self._total_reward,
        }
        self._persist_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _load(self) -> None:
        """Load Q-table from JSON."""
        if not self._persist_path or not self._persist_path.exists():
            return
        try:
            data = json.loads(self._persist_path.read_text(encoding="utf-8"))
            for s, actions in data.get("q_table", {}).items():
                for a, q in actions.items():
                    self._q_table[s][a] = q
            for k, v in data.get("stats", {}).items():
                st = ActionStats()
                st.total_reward = v.get("total_reward", 0)
                st.count = v.get("count", 0)
                st.successes = v.get("successes", 0)
                st.failures = v.get("failures", 0)
                st.avg_reward = v.get("avg_reward", 0)
                self._stats[k] = st
            self._episode_rewards = data.get("episode_rewards", [])
            self._total_reward = data.get("total_reward", 0.0)
        except Exception:
            pass  # Start fresh on corrupt data
