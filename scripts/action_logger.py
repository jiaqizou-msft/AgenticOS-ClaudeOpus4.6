#!/usr/bin/env python3
"""AgenticOS Action Logger — Structured logging of all skill executions.

Appends one JSON line per skill execution to data/action_log.jsonl.
Each entry records: timestamp, skill_id, parameters, actions taken,
whether cached, duration, result, UI state before/after.

This provides a full audit trail for debugging, analysis, and
performance tracking.

Usage:
    from action_logger import ActionLogger, ActionLogEntry
    logger = ActionLogger("data/action_log.jsonl")
    logger.log(ActionLogEntry(skill_id="set_slider", params={...}, ...))
    
    # Read recent entries
    entries = logger.read_recent(10)
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


@dataclass
class ActionLogEntry:
    """A single action log entry."""
    skill_id: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    actions: list = field(default_factory=list)  # list[CachedAction] serialized
    cached: bool = False
    success: bool = False
    duration: float = 0.0
    tokens_used: int = 0
    pre_fingerprint: dict = field(default_factory=dict)
    post_fingerprint: dict = field(default_factory=dict)
    error: str = ""
    plan_source: str = ""
    plan_intent: str = ""


class ActionLogger:
    """Append-only JSONL logger for skill executions."""

    def __init__(self, log_path: str):
        self._path = Path(log_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, entry: ActionLogEntry):
        """Append an entry to the log file."""
        record = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "epoch": time.time(),
            "skill_id": entry.skill_id,
            "params": entry.params,
            "actions": [
                {"action_type": a.action_type, "params": a.params, "thought": a.thought}
                if hasattr(a, 'action_type') else (a if isinstance(a, dict) else str(a))
                for a in entry.actions
            ],
            "cached": entry.cached,
            "success": entry.success,
            "duration": round(entry.duration, 2),
            "tokens_used": entry.tokens_used,
            "pre_fingerprint": entry.pre_fingerprint,
            "post_fingerprint": entry.post_fingerprint,
            "error": entry.error,
            "plan_source": entry.plan_source,
            "plan_intent": entry.plan_intent,
        }
        try:
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"[ActionLogger] Write error: {e}")

    def read_recent(self, n: int = 20) -> list[dict]:
        """Read the N most recent log entries."""
        if not self._path.exists():
            return []

        entries = []
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entries.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
        except Exception:
            pass

        return entries[-n:]

    def read_all(self) -> list[dict]:
        """Read all log entries."""
        return self.read_recent(n=999999)

    def get_skill_stats(self) -> dict[str, dict]:
        """Get aggregated stats per skill."""
        entries = self.read_all()
        stats: dict[str, dict] = {}
        for e in entries:
            sid = e.get("skill_id", "unknown")
            if sid not in stats:
                stats[sid] = {
                    "total": 0, "success": 0, "cached": 0,
                    "total_time": 0.0, "total_tokens": 0,
                }
            s = stats[sid]
            s["total"] += 1
            if e.get("success"):
                s["success"] += 1
            if e.get("cached"):
                s["cached"] += 1
            s["total_time"] += e.get("duration", 0)
            s["total_tokens"] += e.get("tokens_used", 0)

        return stats

    def summary(self) -> str:
        """Human-readable log summary."""
        entries = self.read_all()
        if not entries:
            return "ActionLog: empty"

        total = len(entries)
        successes = sum(1 for e in entries if e.get("success"))
        cached = sum(1 for e in entries if e.get("cached"))
        total_tokens = sum(e.get("tokens_used", 0) for e in entries)
        total_time = sum(e.get("duration", 0) for e in entries)

        return (
            f"ActionLog: {total} entries, {successes}/{total} success "
            f"({cached} cached), {total_time:.1f}s total, {total_tokens} tokens"
        )

    @property
    def size(self) -> int:
        entries = self.read_all()
        return len(entries)
