"""Step memory and action caching.

Stores successful action sequences keyed by (state_signature, intent).
When a similar situation arises, the agent can replay cached actions
instead of making expensive LLM calls.

This implements a simple episodic memory that learns from experience
and amortizes repeated patterns over time.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class CachedStep:
    """A single memorized step."""
    action_type: str
    action_params: dict
    thought: str
    success: bool
    timestamp: float = 0.0


@dataclass
class Episode:
    """A complete memorized action sequence for a sub-task."""
    intent: str          # What the user/agent wanted to do
    context_key: str     # Hash of (window_title, top_elements)
    steps: list[CachedStep] = field(default_factory=list)
    success: bool = False
    use_count: int = 0
    created_at: float = 0.0
    last_used_at: float = 0.0

    def age_seconds(self) -> float:
        return time.time() - self.created_at


class StepMemory:
    """Episodic memory for agent actions.

    Stores and retrieves successful action sequences, allowing the agent
    to skip LLM calls for known patterns.

    Persistence: optionally saves to a JSON file for cross-session learning.
    """

    def __init__(self, persist_path: Optional[str] = None, max_episodes: int = 200) -> None:
        self._episodes: dict[str, Episode] = {}  # context_key -> Episode
        self._persist_path = Path(persist_path) if persist_path else None
        self._max_episodes = max_episodes
        self._hits = 0
        self._misses = 0

        if self._persist_path and self._persist_path.exists():
            self._load()

    @staticmethod
    def make_context_key(
        window_title: str,
        element_names: list[str],
        intent: str,
    ) -> str:
        """Create a stable hash key from current UI context + intent.

        The key combines the window title, top element names, and intent
        so we only match when in a sufficiently similar state.
        """
        # Normalize
        title_norm = window_title.strip().lower()
        # Use top 5 element names for fingerprinting
        top_elems = sorted(set(n.strip().lower() for n in element_names[:10] if n))[:5]
        intent_norm = intent.strip().lower()

        raw = f"{title_norm}|{'|'.join(top_elems)}|{intent_norm}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def lookup(
        self,
        window_title: str,
        element_names: list[str],
        intent: str,
    ) -> Optional[Episode]:
        """Look up a cached episode for the current context.

        Returns the episode if found and it was previously successful.
        """
        key = self.make_context_key(window_title, element_names, intent)
        ep = self._episodes.get(key)

        if ep and ep.success and ep.steps:
            self._hits += 1
            ep.use_count += 1
            ep.last_used_at = time.time()
            return ep

        self._misses += 1
        return None

    def store(
        self,
        window_title: str,
        element_names: list[str],
        intent: str,
        steps: list[CachedStep],
        success: bool,
    ) -> str:
        """Store a completed episode in memory.

        Returns the context key used for storage.
        """
        key = self.make_context_key(window_title, element_names, intent)

        # Only store successful episodes, or overwrite failed ones
        existing = self._episodes.get(key)
        if existing and existing.success and not success:
            return key  # Don't overwrite success with failure

        self._episodes[key] = Episode(
            intent=intent,
            context_key=key,
            steps=steps,
            success=success,
            use_count=0,
            created_at=time.time(),
            last_used_at=time.time(),
        )

        # Evict oldest if over capacity
        if len(self._episodes) > self._max_episodes:
            self._evict_oldest()

        if self._persist_path:
            self._save()

        return key

    def store_single_step(
        self,
        window_title: str,
        element_names: list[str],
        intent: str,
        action_type: str,
        action_params: dict,
        thought: str,
        success: bool,
    ) -> None:
        """Convenience: store a single-step episode."""
        step = CachedStep(
            action_type=action_type,
            action_params=action_params,
            thought=thought,
            success=success,
            timestamp=time.time(),
        )
        self.store(window_title, element_names, intent, [step], success)

    @property
    def hit_rate(self) -> float:
        total = self._hits + self._misses
        return self._hits / total if total > 0 else 0.0

    @property
    def size(self) -> int:
        return len(self._episodes)

    @property
    def stats(self) -> dict:
        return {
            "size": self.size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": f"{self.hit_rate:.1%}",
        }

    def _evict_oldest(self) -> None:
        """Remove the least-recently-used episode."""
        if not self._episodes:
            return
        oldest_key = min(
            self._episodes,
            key=lambda k: self._episodes[k].last_used_at,
        )
        del self._episodes[oldest_key]

    def _save(self) -> None:
        """Persist episodes to JSON."""
        if not self._persist_path:
            return
        self._persist_path.parent.mkdir(parents=True, exist_ok=True)
        data = {}
        for key, ep in self._episodes.items():
            data[key] = {
                "intent": ep.intent,
                "context_key": ep.context_key,
                "steps": [
                    {
                        "action_type": s.action_type,
                        "action_params": s.action_params,
                        "thought": s.thought,
                        "success": s.success,
                        "timestamp": s.timestamp,
                    }
                    for s in ep.steps
                ],
                "success": ep.success,
                "use_count": ep.use_count,
                "created_at": ep.created_at,
                "last_used_at": ep.last_used_at,
            }
        self._persist_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _load(self) -> None:
        """Load episodes from JSON."""
        if not self._persist_path or not self._persist_path.exists():
            return
        try:
            data = json.loads(self._persist_path.read_text(encoding="utf-8"))
            for key, ep_data in data.items():
                self._episodes[key] = Episode(
                    intent=ep_data["intent"],
                    context_key=ep_data["context_key"],
                    steps=[
                        CachedStep(
                            action_type=s["action_type"],
                            action_params=s["action_params"],
                            thought=s["thought"],
                            success=s["success"],
                            timestamp=s.get("timestamp", 0),
                        )
                        for s in ep_data["steps"]
                    ],
                    success=ep_data["success"],
                    use_count=ep_data.get("use_count", 0),
                    created_at=ep_data.get("created_at", 0),
                    last_used_at=ep_data.get("last_used_at", 0),
                )
        except Exception:
            pass  # Corrupted file, start fresh

    def clear(self) -> None:
        """Clear all memory."""
        self._episodes.clear()
        self._hits = 0
        self._misses = 0
        if self._persist_path and self._persist_path.exists():
            self._persist_path.unlink()
