#!/usr/bin/env python3
"""AgenticOS Skill Cache — Amortized replay of learned action sequences.

When a skill executes successfully via LLM, the exact action sequence is cached
with a UI state fingerprint. On subsequent calls, if the fingerprint matches,
the cached sequence is replayed directly WITHOUT calling the LLM — saving
tokens, time, and providing deterministic execution.

Staleness detection: If the UI state has drifted (fingerprint mismatch beyond
threshold), the cache entry is invalidated and a fresh LLM execution is triggered.
The new sequence then replaces the stale cache entry.

Persistence: Cache is saved to data/skill_cache.json for cross-session reuse.

Usage:
    from skill_cache import SkillCache
    cache = SkillCache()
    
    # Check for cached sequence
    entry = cache.lookup("set_slider", {"name": "Brightness", "value": 100}, fingerprint)
    if entry:
        replay(entry.actions)  # Direct replay, no LLM
    else:
        actions = run_with_llm(...)  # LLM-guided execution
        cache.store("set_slider", {"name": "Brightness", "value": 100}, fingerprint, actions)
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


@dataclass
class CachedAction:
    """A single action from a cached skill execution."""
    action_type: str
    params: dict[str, Any]
    thought: str = ""
    step_index: int = 0
    exec_time: float = 0.0


@dataclass
class UIFingerprint:
    """A fingerprint of the UI state for staleness detection.
    
    Uses fuzzy matching: window title must match exactly, but element count
    only needs to be within ±tolerance (default 20%). Top element names are
    compared with set intersection — if >60% overlap, considered a match.
    """
    window_title: str
    element_count: int
    top_elements: list[str]    # First N element names
    timestamp: float = 0.0

    def matches(self, other: "UIFingerprint", tolerance: float = 0.20) -> bool:
        """Check if two fingerprints match within tolerance."""
        # Window title must match (case-insensitive)
        if self.window_title.lower() != other.window_title.lower():
            return False

        # Element count within tolerance
        if self.element_count == 0 and other.element_count == 0:
            count_ok = True
        elif self.element_count == 0 or other.element_count == 0:
            count_ok = False
        else:
            ratio = abs(self.element_count - other.element_count) / max(self.element_count, other.element_count)
            count_ok = ratio <= tolerance

        if not count_ok:
            return False

        # Top elements overlap (set intersection)
        if not self.top_elements and not other.top_elements:
            return True
        if not self.top_elements or not other.top_elements:
            return count_ok  # If one side has no elements, rely on count match
        
        set_a = set(self.top_elements)
        set_b = set(other.top_elements)
        intersection = len(set_a & set_b)
        union = len(set_a | set_b)
        overlap = intersection / union if union > 0 else 0
        return overlap >= 0.6

    @classmethod
    def from_state(cls, window_title: str, elements: list, max_elements: int = 15) -> "UIFingerprint":
        """Create a fingerprint from current UI state."""
        elem_names = [getattr(el, 'name', str(el)) for el in elements[:max_elements]]
        return cls(
            window_title=window_title,
            element_count=len(elements),
            top_elements=elem_names,
            timestamp=time.time(),
        )

    def to_dict(self) -> dict:
        return {
            "window_title": self.window_title,
            "element_count": self.element_count,
            "top_elements": self.top_elements,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "UIFingerprint":
        return cls(**d)


@dataclass
class CacheEntry:
    """A cached skill execution with its action sequence and metadata."""
    skill_id: str
    params: dict[str, Any]
    actions: list[CachedAction]
    pre_fingerprint: UIFingerprint
    post_fingerprint: UIFingerprint | None = None
    success: bool = True
    total_time: float = 0.0
    llm_tokens_saved: int = 0      # Estimated tokens saved on replay
    replay_count: int = 0          # How many times this has been replayed
    created_at: float = 0.0
    last_used: float = 0.0
    last_validated: float = 0.0    # Last time the fingerprint was validated

    def cache_key(self) -> str:
        """Generate a unique cache key for this skill+params combo."""
        param_str = json.dumps(self.params, sort_keys=True)
        raw = f"{self.skill_id}:{param_str}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def to_dict(self) -> dict:
        return {
            "skill_id": self.skill_id,
            "params": self.params,
            "actions": [
                {"action_type": a.action_type, "params": a.params,
                 "thought": a.thought, "step_index": a.step_index, "exec_time": a.exec_time}
                for a in self.actions
            ],
            "pre_fingerprint": self.pre_fingerprint.to_dict(),
            "post_fingerprint": self.post_fingerprint.to_dict() if self.post_fingerprint else None,
            "success": self.success,
            "total_time": self.total_time,
            "llm_tokens_saved": self.llm_tokens_saved,
            "replay_count": self.replay_count,
            "created_at": self.created_at,
            "last_used": self.last_used,
            "last_validated": self.last_validated,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CacheEntry":
        actions = [CachedAction(**a) for a in d.get("actions", [])]
        pre_fp = UIFingerprint.from_dict(d["pre_fingerprint"])
        post_fp = UIFingerprint.from_dict(d["post_fingerprint"]) if d.get("post_fingerprint") else None
        return cls(
            skill_id=d["skill_id"],
            params=d["params"],
            actions=actions,
            pre_fingerprint=pre_fp,
            post_fingerprint=post_fp,
            success=d.get("success", True),
            total_time=d.get("total_time", 0.0),
            llm_tokens_saved=d.get("llm_tokens_saved", 0),
            replay_count=d.get("replay_count", 0),
            created_at=d.get("created_at", 0.0),
            last_used=d.get("last_used", 0.0),
            last_validated=d.get("last_validated", 0.0),
        )


class SkillCache:
    """Persistent cache for amortized skill execution.
    
    Stores successful action sequences indexed by skill_id + params.
    On lookup, validates UI fingerprint for staleness.
    """

    def __init__(self, persist_path: str | None = None, tolerance: float = 0.20):
        self._cache: dict[str, CacheEntry] = {}
        self._tolerance = tolerance
        self._persist_path = Path(persist_path) if persist_path else None
        self._stats = {"hits": 0, "misses": 0, "stale": 0, "stores": 0, "replays": 0}
        
        if self._persist_path:
            self._load()

    def _load(self):
        """Load cache from disk."""
        if self._persist_path and self._persist_path.exists():
            try:
                data = json.loads(self._persist_path.read_text(encoding="utf-8"))
                for key, entry_dict in data.get("cache", {}).items():
                    self._cache[key] = CacheEntry.from_dict(entry_dict)
                self._stats = data.get("stats", self._stats)
            except Exception as e:
                print(f"[SkillCache] Load error: {e}")

    def _save(self):
        """Save cache to disk."""
        if not self._persist_path:
            return
        self._persist_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "cache": {k: v.to_dict() for k, v in self._cache.items()},
            "stats": self._stats,
            "saved_at": time.time(),
        }
        try:
            self._persist_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as e:
            print(f"[SkillCache] Save error: {e}")

    def lookup(self, skill_id: str, params: dict, current_fingerprint: UIFingerprint) -> CacheEntry | None:
        """Look up a cached skill execution.
        
        Returns the CacheEntry if found and the fingerprint matches.
        Returns None if not cached or if the UI state has drifted (stale).
        """
        # Build cache key
        param_str = json.dumps(params, sort_keys=True)
        raw = f"{skill_id}:{param_str}"
        key = hashlib.sha256(raw.encode()).hexdigest()[:16]

        entry = self._cache.get(key)
        if not entry:
            self._stats["misses"] += 1
            return None

        if not entry.success:
            self._stats["misses"] += 1
            return None

        # Reject no-op entries (only 'done' actions — not replayable)
        real_actions = [a for a in entry.actions if a.action_type != "done"]
        if not real_actions:
            self._stats["misses"] += 1
            # Auto-invalidate the bad entry
            del self._cache[key]
            self._save()
            print(f"[SkillCache] Purged no-op cache for {entry.skill_id}")
            return None

        # Check fingerprint staleness
        if entry.pre_fingerprint.matches(current_fingerprint, self._tolerance):
            self._stats["hits"] += 1
            entry.replay_count += 1
            entry.last_used = time.time()
            entry.last_validated = time.time()
            self._save()
            return entry
        else:
            self._stats["stale"] += 1
            # Don't delete — it might match again later (transient UI change)
            return None

    def store(self, skill_id: str, params: dict, actions: list[CachedAction],
              pre_fingerprint: UIFingerprint, post_fingerprint: UIFingerprint | None = None,
              success: bool = True, total_time: float = 0.0, llm_tokens: int = 0) -> str:
        """Store a successful skill execution in the cache.
        
        Returns the cache key, or empty string if not cached.
        
        NOTE: Entries where the only action is 'done' are NOT cached because
        they represent state-dependent observations ("already done") that are
        not replayable — the state may be different on the next invocation.
        """
        # Refuse to cache no-op entries (only 'done' actions, no real UI interaction)
        real_actions = [a for a in actions if a.action_type != "done"]
        if not real_actions:
            print(f"[SkillCache] Skipping cache for {skill_id}: no-op (only 'done' actions)")
            return ""

        param_str = json.dumps(params, sort_keys=True)
        raw = f"{skill_id}:{param_str}"
        key = hashlib.sha256(raw.encode()).hexdigest()[:16]

        entry = CacheEntry(
            skill_id=skill_id,
            params=params,
            actions=actions,
            pre_fingerprint=pre_fingerprint,
            post_fingerprint=post_fingerprint,
            success=success,
            total_time=total_time,
            llm_tokens_saved=llm_tokens,
            replay_count=0,
            created_at=time.time(),
            last_used=time.time(),
            last_validated=time.time(),
        )

        self._cache[key] = entry
        self._stats["stores"] += 1
        self._save()
        return key

    def invalidate(self, skill_id: str, params: dict):
        """Invalidate (remove) a cache entry."""
        param_str = json.dumps(params, sort_keys=True)
        raw = f"{skill_id}:{param_str}"
        key = hashlib.sha256(raw.encode()).hexdigest()[:16]
        self._cache.pop(key, None)
        self._save()

    def clear(self):
        """Clear all cache entries."""
        self._cache.clear()
        self._save()

    @property
    def stats(self) -> dict:
        """Return cache statistics."""
        total_replays = sum(e.replay_count for e in self._cache.values())
        total_tokens_saved = sum(e.llm_tokens_saved * e.replay_count for e in self._cache.values())
        return {
            **self._stats,
            "entries": len(self._cache),
            "total_replays": total_replays,
            "est_tokens_saved": total_tokens_saved,
        }

    @property
    def size(self) -> int:
        return len(self._cache)

    def get_all_entries(self) -> list[CacheEntry]:
        """Return all cache entries sorted by last used."""
        return sorted(self._cache.values(), key=lambda e: e.last_used, reverse=True)

    def summary(self) -> str:
        """Human-readable cache summary."""
        s = self.stats
        hit_rate = s["hits"] / max(s["hits"] + s["misses"] + s["stale"], 1) * 100
        return (
            f"SkillCache: {s['entries']} entries, "
            f"{s['hits']} hits / {s['misses']} misses / {s['stale']} stale "
            f"({hit_rate:.0f}% hit rate), "
            f"~{s['est_tokens_saved']} tokens saved"
        )
