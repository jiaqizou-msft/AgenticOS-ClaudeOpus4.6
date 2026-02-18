"""Demo Optimizer — per-demo amortization and overhead reduction.

Uses human supervision feedback + RL history to tune each demo's
execution parameters over time.  Key design constraint:

    ★ NEVER speed up cursor movement or typing speed. ★

All optimization targets the OVERHEAD surrounding user-visible actions:
  • Fewer LLM calls (via golden-sequence replay)
  • Tighter step/time budgets (from best-rated runs)
  • Smarter prompt hints (from human corrective notes)
  • Skip redundant validation when confidence is high

Persistence:  recordings/supervision/optimizer.json
"""

from __future__ import annotations

import json
import statistics
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from agenticos.agent.human_supervisor import HumanSupervisor, DemoHistory


# ── Data Classes ──

@dataclass
class GoldenSequence:
    """A highly-rated action sequence for a specific demo.

    Captured from runs where the human rated accuracy ≥ 4/5.
    Can be replayed to skip LLM calls on well-understood demos.
    """

    demo_id: int
    actions: list[dict] = field(default_factory=list)  # [{type, params, thought}]
    human_score: float = 0.0
    steps: int = 0
    elapsed: float = 0.0
    created_at: float = field(default_factory=time.time)
    use_count: int = 0
    last_success: bool = True


@dataclass
class DemoProfile:
    """Learned execution profile for a single demo.

    Evolved over time from human feedback — stores the best-known
    parameters for running this demo quickly and accurately.
    """

    demo_id: int
    demo_name: str

    # Tuned parameters (None = use defaults)
    optimal_max_steps: Optional[int] = None
    optimal_timeout: Optional[int] = None
    skip_validation: bool = False  # Skip post-action validation when high confidence
    confidence_level: float = 0.0  # 0-1, from human feedback history

    # Prompt enhancements
    prompt_hints: list[str] = field(default_factory=list)  # From human corrective notes
    speed_notes: list[str] = field(default_factory=list)  # Efficiency tips

    # Golden sequences (best action plans from highest-rated runs)
    golden_sequences: list[GoldenSequence] = field(default_factory=list)

    # Stats
    total_runs: int = 0
    optimized_runs: int = 0  # Runs that used optimization
    avg_score_before_opt: float = 0.0
    avg_score_after_opt: float = 0.0


class DemoOptimizer:
    """Per-demo amortization engine.

    Learns from human feedback to optimize each demo over time:

    1. **Step Budget Tightening**: Uses best-rated runs to set tighter
       max_steps, saving LLM calls (the main time cost).

    2. **Golden Sequence Replay**: When confidence is high, replays the
       exact action sequence from the best run, skipping LLM entirely
       for well-understood demos.

    3. **Prompt Hints**: Injects human corrective notes into the LLM
       prompt so the agent avoids known mistakes.

    4. **Validation Skipping**: For demos with 100% accuracy over 3+
       runs, skips post-action validation (saves ~8s/step).

    ★ Does NOT touch cursor speed, typing speed, or interaction delays. ★
    """

    def __init__(
        self,
        supervisor: HumanSupervisor,
        persist_dir: Optional[str] = None,
    ) -> None:
        self._supervisor = supervisor
        self._persist_dir = Path(persist_dir) if persist_dir else Path("recordings/supervision")
        self._persist_dir.mkdir(parents=True, exist_ok=True)
        self._optimizer_path = self._persist_dir / "optimizer.json"

        # demo_id → DemoProfile
        self._profiles: dict[int, DemoProfile] = {}
        self._load()

    # ── Public API ──

    def get_optimized_config(self, demo_id: int, base_config: dict) -> dict:
        """Return an optimized demo config based on learned profile.

        Merges the base demo config with learned optimizations.
        Does NOT modify cursor/typing speed — only adjusts overhead.

        Args:
            demo_id: Demo number.
            base_config: Original DEMOS[demo_id] dict.

        Returns:
            Optimized config dict (copy of base with adjustments).
        """
        config = dict(base_config)
        profile = self._profiles.get(demo_id)
        if not profile:
            return config

        # 1. Tighten step budget
        if profile.optimal_max_steps and profile.confidence_level >= 0.6:
            # Add 2-step buffer so the agent has room to recover
            optimized_steps = profile.optimal_max_steps + 2
            original_steps = config.get("max_steps", 15)
            if optimized_steps < original_steps:
                config["max_steps"] = optimized_steps
                config["_opt_note"] = (
                    f"max_steps reduced {original_steps}→{optimized_steps} "
                    f"(confidence: {profile.confidence_level:.0%})"
                )

        # 2. Tighten timeout
        if profile.optimal_timeout and profile.confidence_level >= 0.7:
            # Add 30% buffer
            optimized_timeout = int(profile.optimal_timeout * 1.3)
            original_timeout = config.get("timeout", 300)
            if optimized_timeout < original_timeout:
                config["timeout"] = optimized_timeout

        # 3. Skip validation for high-confidence demos
        if profile.skip_validation and profile.confidence_level >= 0.9:
            config["fast_mode"] = True  # Re-uses existing fast_mode skip logic

        return config

    def get_prompt_enhancement(self, demo_id: int) -> str:
        """Get prompt enhancement text from learned profile + human feedback.

        Combines:
        - Human corrective notes (what to do differently)
        - Efficiency tips (reduce wasted steps)
        - Golden sequence hints (what worked best before)
        - Supervisor prompt hints
        """
        parts: list[str] = []

        # From supervisor's feedback history
        sup_hints = self._supervisor.get_prompt_hints(demo_id)
        if sup_hints:
            parts.append(sup_hints)

        # From optimizer profile
        profile = self._profiles.get(demo_id)
        if profile:
            if profile.prompt_hints:
                parts.append("\nOPTIMIZER HINTS (learned from past runs):")
                for h in profile.prompt_hints[-5:]:  # Last 5 hints
                    parts.append(f"  • {h}")

            if profile.speed_notes:
                parts.append("\nSPEED TIPS (from human efficiency feedback):")
                for s in profile.speed_notes[-3:]:
                    parts.append(f"  • {s}")

            # Reference golden sequence (as guidance, not forced replay)
            if profile.golden_sequences and profile.confidence_level >= 0.5:
                best = max(profile.golden_sequences, key=lambda g: g.human_score)
                if best.actions:
                    parts.append(
                        f"\nBEST KNOWN APPROACH ({best.steps} steps, "
                        f"score: {best.human_score:.0%}):"
                    )
                    for i, act in enumerate(best.actions[:8], 1):
                        parts.append(
                            f"  {i}. {act.get('type', '?')}: "
                            f"{act.get('thought', '')[:80]}"
                        )
                    if len(best.actions) > 8:
                        parts.append(f"  ... ({len(best.actions) - 8} more steps)")

        return "\n".join(parts) if parts else ""

    def get_golden_sequence(self, demo_id: int) -> Optional[GoldenSequence]:
        """Get the best golden sequence for replay.

        Only returns a sequence if confidence is very high (≥ 0.85)
        and the sequence has been successful before.
        """
        profile = self._profiles.get(demo_id)
        if not profile or profile.confidence_level < 0.85:
            return None

        candidates = [g for g in profile.golden_sequences if g.last_success]
        if not candidates:
            return None

        return max(candidates, key=lambda g: g.human_score)

    def update_from_feedback(
        self,
        demo_id: int,
        demo_name: str,
        step_log: list[dict],
        feedback_score: float,
        human_notes: str = "",
        correct_approach: str = "",
    ) -> None:
        """Update the optimization profile from human feedback.

        Called after each supervised demo run to learn better parameters.

        Args:
            demo_id: Demo number.
            demo_name: Human-readable demo name.
            step_log: List of step records from the demo run.
            feedback_score: Overall human score (0-1).
            human_notes: Corrective notes from human.
            correct_approach: Human's description of better approach.
        """
        if demo_id not in self._profiles:
            self._profiles[demo_id] = DemoProfile(
                demo_id=demo_id,
                demo_name=demo_name,
            )
        profile = self._profiles[demo_id]
        profile.total_runs += 1

        # Update confidence from supervisor history
        history = self._supervisor.get_history(demo_id)
        if history:
            profile.confidence_level = self._compute_confidence(history)

            # Compute optimal steps/timeout from good runs
            targets = self._supervisor.get_speed_targets(demo_id)
            if targets:
                profile.optimal_max_steps = targets.get("target_steps")
                profile.optimal_timeout = int(targets.get("target_time", 0)) or None

        # Add corrective hints
        if human_notes:
            # Avoid duplicate notes
            if human_notes not in profile.prompt_hints:
                profile.prompt_hints.append(human_notes)
                # Keep only last 10 hints
                profile.prompt_hints = profile.prompt_hints[-10:]

        if correct_approach:
            if correct_approach not in profile.speed_notes:
                profile.speed_notes.append(correct_approach)
                profile.speed_notes = profile.speed_notes[-5:]

        # Store golden sequence if score is high
        if feedback_score >= 0.8 and step_log:
            actions = []
            for s in step_log:
                if s.get("action_type") and s["action_type"] != "done":
                    actions.append({
                        "type": s["action_type"],
                        "params": s.get("action_params", {}),
                        "thought": s.get("thought", ""),
                    })
            if actions:
                golden = GoldenSequence(
                    demo_id=demo_id,
                    actions=actions,
                    human_score=feedback_score,
                    steps=len(step_log),
                    elapsed=sum(1 for _ in step_log),  # Approximate
                )
                profile.golden_sequences.append(golden)
                # Keep only top 3 golden sequences
                profile.golden_sequences.sort(key=lambda g: g.human_score, reverse=True)
                profile.golden_sequences = profile.golden_sequences[:3]

        # Decide if validation can be skipped
        if history and history.attempts >= 3:
            recent = history.feedbacks[-3:]
            if all(f.accuracy >= 4 for f in recent):
                profile.skip_validation = True
            else:
                profile.skip_validation = False

        self._save()

    def get_profile(self, demo_id: int) -> Optional[DemoProfile]:
        """Get the current optimization profile for a demo."""
        return self._profiles.get(demo_id)

    @property
    def stats(self) -> str:
        """Summary string for logging."""
        n_profiles = len(self._profiles)
        n_golden = sum(
            len(p.golden_sequences) for p in self._profiles.values()
        )
        high_conf = sum(
            1 for p in self._profiles.values() if p.confidence_level >= 0.7
        )
        return (
            f"profiles={n_profiles}, golden_seqs={n_golden}, "
            f"high_confidence={high_conf}"
        )

    # ── Private Methods ──

    @staticmethod
    def _compute_confidence(history: DemoHistory) -> float:
        """Compute confidence level from human feedback history.

        Uses exponentially weighted recent feedback (recent matters more).
        """
        if not history.feedbacks:
            return 0.0

        # Weight recent feedback more heavily
        weights = []
        scores = []
        for i, f in enumerate(history.feedbacks):
            w = 1.0 + i * 0.5  # Later feedbacks get higher weight
            weights.append(w)
            scores.append(f.overall_score)

        weighted_sum = sum(s * w for s, w in zip(scores, weights))
        weight_total = sum(weights)
        base = weighted_sum / weight_total if weight_total else 0.5

        # Penalize for too few attempts (need >= 3 for reasonable confidence)
        n = len(history.feedbacks)
        ramp = min(1.0, n / 3.0)

        return base * ramp

    # ── Persistence ──

    def _save(self) -> None:
        """Persist optimizer profiles to JSON."""
        data: dict = {}
        for demo_id, profile in self._profiles.items():
            data[str(demo_id)] = {
                "demo_id": profile.demo_id,
                "demo_name": profile.demo_name,
                "optimal_max_steps": profile.optimal_max_steps,
                "optimal_timeout": profile.optimal_timeout,
                "skip_validation": profile.skip_validation,
                "confidence_level": profile.confidence_level,
                "prompt_hints": profile.prompt_hints,
                "speed_notes": profile.speed_notes,
                "total_runs": profile.total_runs,
                "optimized_runs": profile.optimized_runs,
                "avg_score_before_opt": profile.avg_score_before_opt,
                "avg_score_after_opt": profile.avg_score_after_opt,
                "golden_sequences": [
                    {
                        "demo_id": g.demo_id,
                        "actions": g.actions,
                        "human_score": g.human_score,
                        "steps": g.steps,
                        "elapsed": g.elapsed,
                        "created_at": g.created_at,
                        "use_count": g.use_count,
                        "last_success": g.last_success,
                    }
                    for g in profile.golden_sequences
                ],
            }
        self._optimizer_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _load(self) -> None:
        """Load persisted optimizer profiles from JSON."""
        if not self._optimizer_path.exists():
            return
        try:
            data = json.loads(self._optimizer_path.read_text(encoding="utf-8"))
            for key, p_data in data.items():
                demo_id = p_data["demo_id"]
                profile = DemoProfile(
                    demo_id=demo_id,
                    demo_name=p_data.get("demo_name", f"Demo {demo_id}"),
                    optimal_max_steps=p_data.get("optimal_max_steps"),
                    optimal_timeout=p_data.get("optimal_timeout"),
                    skip_validation=p_data.get("skip_validation", False),
                    confidence_level=p_data.get("confidence_level", 0.0),
                    prompt_hints=p_data.get("prompt_hints", []),
                    speed_notes=p_data.get("speed_notes", []),
                    total_runs=p_data.get("total_runs", 0),
                    optimized_runs=p_data.get("optimized_runs", 0),
                    avg_score_before_opt=p_data.get("avg_score_before_opt", 0.0),
                    avg_score_after_opt=p_data.get("avg_score_after_opt", 0.0),
                )
                for g_data in p_data.get("golden_sequences", []):
                    profile.golden_sequences.append(GoldenSequence(
                        demo_id=g_data.get("demo_id", demo_id),
                        actions=g_data.get("actions", []),
                        human_score=g_data.get("human_score", 0.0),
                        steps=g_data.get("steps", 0),
                        elapsed=g_data.get("elapsed", 0.0),
                        created_at=g_data.get("created_at", 0.0),
                        use_count=g_data.get("use_count", 0),
                        last_success=g_data.get("last_success", True),
                    ))
                self._profiles[demo_id] = profile
        except Exception:
            pass  # Start fresh on corruption
