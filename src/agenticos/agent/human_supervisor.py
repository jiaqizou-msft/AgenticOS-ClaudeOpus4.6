"""Human Supervisor — post-demo review & feedback for RL-guided improvement.

Unlike HumanTeacher (which records human demonstrations FOR the agent),
HumanSupervisor lets a human WATCH the agent work and then rate its
performance.  Feedback flows into:
  • RL reward signal  (weighted heavily — human signal is high quality)
  • DemoOptimizer     (per-demo parameter tuning over time)
  • Prompt hints      (corrective notes injected into future LLM calls)

The interaction is non-blocking: the agent runs a demo, records a GIF,
then pauses and asks the human to rate the result.

Persistence:  recordings/supervision/feedback.json
"""

from __future__ import annotations

import json
import os
import statistics
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


# ── Data Classes ──

@dataclass
class DemoFeedback:
    """Human feedback for a single demo execution."""

    demo_id: int
    demo_name: str
    timestamp: float = field(default_factory=time.time)

    # Ratings (1-5 scale, 0 = skipped / not rated)
    accuracy: int = 0        # Did it achieve the right outcome?
    completeness: int = 0    # Were ALL parts of the task finished?
    efficiency: int = 0      # Was it done without wasted steps?

    # Free-form
    notes: str = ""          # Corrective hints, e.g. "should use hotkey instead"
    correct_approach: str = ""  # What should it have done differently?

    # Auto-captured context
    steps: int = 0
    elapsed: float = 0.0
    success: bool = False
    gif_path: str = ""

    @property
    def overall_score(self) -> float:
        """Weighted average of non-zero ratings (0-1 scale)."""
        rated = [v for v in (self.accuracy, self.completeness, self.efficiency) if v > 0]
        if not rated:
            return 0.5  # neutral if no ratings given
        # Accuracy counts 2x because it matters most
        weights = {"accuracy": 2.0, "completeness": 1.0, "efficiency": 1.0}
        total_w = 0.0
        total_v = 0.0
        for name, w in weights.items():
            val = getattr(self, name)
            if val > 0:
                total_v += (val / 5.0) * w
                total_w += w
        return total_v / total_w if total_w > 0 else 0.5

    @property
    def rl_reward(self) -> float:
        """Convert human score to an RL reward signal in [-2, +3].

        Scaled wider than automated rewards so human feedback dominates
        when present, but doesn't destabilize Q-values.
        """
        s = self.overall_score  # 0-1
        # Map: 0.0 → -2.0,  0.5 → 0.0,  1.0 → +3.0
        if s >= 0.5:
            return (s - 0.5) * 6.0  # 0 to +3
        else:
            return (s - 0.5) * 4.0  # -2 to 0


@dataclass
class DemoHistory:
    """Aggregated history of human feedback for one demo."""

    demo_id: int
    demo_name: str
    feedbacks: list[DemoFeedback] = field(default_factory=list)

    @property
    def attempts(self) -> int:
        return len(self.feedbacks)

    @property
    def avg_accuracy(self) -> float:
        rated = [f.accuracy for f in self.feedbacks if f.accuracy > 0]
        return statistics.mean(rated) if rated else 0.0

    @property
    def avg_completeness(self) -> float:
        rated = [f.completeness for f in self.feedbacks if f.completeness > 0]
        return statistics.mean(rated) if rated else 0.0

    @property
    def avg_efficiency(self) -> float:
        rated = [f.efficiency for f in self.feedbacks if f.efficiency > 0]
        return statistics.mean(rated) if rated else 0.0

    @property
    def avg_score(self) -> float:
        scores = [f.overall_score for f in self.feedbacks]
        return statistics.mean(scores) if scores else 0.5

    @property
    def success_rate(self) -> float:
        if not self.feedbacks:
            return 0.0
        return sum(1 for f in self.feedbacks if f.success) / len(self.feedbacks)

    @property
    def avg_steps(self) -> float:
        steps = [f.steps for f in self.feedbacks if f.steps > 0]
        return statistics.mean(steps) if steps else 0.0

    @property
    def avg_elapsed(self) -> float:
        times = [f.elapsed for f in self.feedbacks if f.elapsed > 0]
        return statistics.mean(times) if times else 0.0

    def trend(self, window: int = 5) -> str:
        """Score trend over last N attempts: improving / declining / stable."""
        if len(self.feedbacks) < 3:
            return "insufficient_data"
        recent = self.feedbacks[-window:]
        if len(recent) < 2:
            return "insufficient_data"
        first_half = recent[: len(recent) // 2]
        second_half = recent[len(recent) // 2 :]
        avg_first = statistics.mean(f.overall_score for f in first_half)
        avg_second = statistics.mean(f.overall_score for f in second_half)
        diff = avg_second - avg_first
        if diff > 0.1:
            return "improving"
        elif diff < -0.1:
            return "declining"
        return "stable"

    def latest_corrective_notes(self, n: int = 3) -> list[str]:
        """Get the most recent non-empty corrective notes."""
        notes = []
        for f in reversed(self.feedbacks):
            if f.notes.strip():
                notes.append(f.notes.strip())
            if f.correct_approach.strip():
                notes.append(f"Better approach: {f.correct_approach.strip()}")
            if len(notes) >= n:
                break
        return notes


# ── Supervisor ──

class HumanSupervisor:
    """Manages human review of agent demo executions.

    After each demo run, the supervisor:
    1. Shows the human the GIF path and step summary
    2. Collects ratings (accuracy, completeness, efficiency) on 1-5 scale
    3. Collects optional free-text corrective notes
    4. Persists everything to disk
    5. Returns an RL-compatible reward signal
    """

    def __init__(self, persist_dir: Optional[str] = None) -> None:
        self._persist_dir = Path(persist_dir) if persist_dir else Path("recordings/supervision")
        self._persist_dir.mkdir(parents=True, exist_ok=True)
        self._feedback_path = self._persist_dir / "feedback.json"

        # demo_id → DemoHistory
        self._history: dict[int, DemoHistory] = {}
        self._load()

    # ── Public API ──

    def collect_feedback(
        self,
        demo_id: int,
        demo_name: str,
        success: bool,
        steps: int,
        elapsed: float,
        gif_path: str | None = None,
        step_log: list[dict] | None = None,
    ) -> DemoFeedback:
        """Interactively collect human feedback for a demo run.

        Blocks until the human finishes rating.  Returns the feedback
        with computed RL reward.
        """
        print()
        print("=" * 64)
        print("  HUMAN SUPERVISION — Review Demo Result")
        print("=" * 64)
        print(f"  Demo:    {demo_name}")
        print(f"  Status:  {'✓ SUCCESS' if success else '✗ INCOMPLETE'}")
        print(f"  Steps:   {steps}")
        print(f"  Time:    {elapsed:.1f}s")
        if gif_path and os.path.exists(gif_path):
            print(f"  GIF:     {gif_path}")
            print(f"           (open this file to review the agent's actions)")
        if step_log:
            print()
            print("  Step Log (last 10):")
            for s in step_log[-10:]:
                drift_tag = " ⚠DRIFT" if s.get("drift") else ""
                print(f"    {s.get('step', '?'):>2}. [{s.get('action_type', '?')}] "
                      f"{s.get('thought', '')[:60]}{drift_tag}")
        print()

        # Collect ratings
        accuracy = self._ask_rating("Accuracy (did it achieve the right outcome?)")
        completeness = self._ask_rating("Completeness (were ALL parts finished?)")
        efficiency = self._ask_rating("Efficiency (no wasted/repeated steps?)")

        # Collect notes
        notes = self._ask_text("Any corrective notes? (what went wrong, or press Enter to skip)")
        correct_approach = ""
        if accuracy < 4 or completeness < 4:
            correct_approach = self._ask_text(
                "What should it have done differently? (or Enter to skip)"
            )

        feedback = DemoFeedback(
            demo_id=demo_id,
            demo_name=demo_name,
            accuracy=accuracy,
            completeness=completeness,
            efficiency=efficiency,
            notes=notes,
            correct_approach=correct_approach,
            steps=steps,
            elapsed=elapsed,
            success=success,
            gif_path=gif_path or "",
        )

        # Store
        self._record(feedback)
        self._save()

        # Show summary
        print()
        print(f"  → Score: {feedback.overall_score:.0%}  |  RL reward: {feedback.rl_reward:+.2f}")
        history = self._history.get(demo_id)
        if history and history.attempts > 1:
            print(f"  → History: {history.attempts} attempts, "
                  f"avg score {history.avg_score:.0%}, "
                  f"trend: {history.trend()}")
            corrective = history.latest_corrective_notes(2)
            if corrective:
                print(f"  → Active corrections: {'; '.join(corrective[:2])}")
        print("=" * 64)
        print()

        return feedback

    def get_history(self, demo_id: int) -> Optional[DemoHistory]:
        """Get the full feedback history for a demo."""
        return self._history.get(demo_id)

    def get_all_histories(self) -> dict[int, DemoHistory]:
        """Get all demo histories."""
        return dict(self._history)

    def get_prompt_hints(self, demo_id: int) -> str:
        """Generate LLM prompt hints from past human feedback.

        Returns a string to inject into the system prompt with corrective
        guidance based on what the human said in previous reviews.
        """
        history = self._history.get(demo_id)
        if not history or history.attempts == 0:
            return ""

        hints: list[str] = []

        # Corrective notes from human
        notes = history.latest_corrective_notes(3)
        if notes:
            hints.append("HUMAN SUPERVISOR NOTES (from reviewing your previous attempts):")
            for n in notes:
                hints.append(f"  • {n}")

        # Performance issues
        if history.avg_efficiency < 3.0 and history.attempts >= 2:
            hints.append(
                f"⚠ EFFICIENCY WARNING: Average efficiency rating is "
                f"{history.avg_efficiency:.1f}/5. Reduce unnecessary steps."
            )
        if history.avg_accuracy < 3.0 and history.attempts >= 2:
            hints.append(
                f"⚠ ACCURACY WARNING: Average accuracy rating is "
                f"{history.avg_accuracy:.1f}/5. Double-check your actions match the task."
            )

        # Best run reference
        if history.feedbacks:
            best = max(history.feedbacks, key=lambda f: f.overall_score)
            if best.overall_score > 0.7 and best.steps > 0:
                hints.append(
                    f"Your best run completed in {best.steps} steps / {best.elapsed:.0f}s "
                    f"(score: {best.overall_score:.0%}). Try to match or beat that."
                )

        if hints:
            return "\n\n" + "\n".join(hints) + "\n"
        return ""

    def get_speed_targets(self, demo_id: int) -> dict:
        """Get speed optimization targets based on human feedback.

        Returns target steps/time from the best-rated runs, which the
        optimizer can use to set tighter budgets without sacrificing
        accuracy.

        Note: These targets adjust OVERHEAD (LLM calls, validation, UIA),
        NOT cursor movement or typing speed.
        """
        history = self._history.get(demo_id)
        if not history or len(history.feedbacks) < 2:
            return {}

        # Use runs rated >= 4/5 accuracy as the reference
        good_runs = [f for f in history.feedbacks if f.accuracy >= 4 and f.success]
        if not good_runs:
            return {}

        return {
            "target_steps": int(statistics.median(f.steps for f in good_runs)),
            "target_time": statistics.median(f.elapsed for f in good_runs),
            "best_steps": min(f.steps for f in good_runs),
            "best_time": min(f.elapsed for f in good_runs),
        }

    @property
    def stats(self) -> str:
        """Summary string for logging."""
        total = sum(h.attempts for h in self._history.values())
        demos = len(self._history)
        return f"supervised={total} across {demos} demos"

    # ── Interactive Input Helpers ──

    @staticmethod
    def _ask_rating(prompt: str) -> int:
        """Ask for a 1-5 rating (0 to skip)."""
        while True:
            try:
                raw = input(f"  {prompt} [1-5, Enter=skip]: ").strip()
                if not raw:
                    return 0
                val = int(raw)
                if 1 <= val <= 5:
                    return val
                print("    Please enter 1-5 or press Enter to skip.")
            except (ValueError, EOFError):
                return 0

    @staticmethod
    def _ask_text(prompt: str) -> str:
        """Ask for free-form text input."""
        try:
            return input(f"  {prompt}\n  > ").strip()
        except EOFError:
            return ""

    # ── Persistence ──

    def _record(self, feedback: DemoFeedback) -> None:
        """Record feedback into in-memory history."""
        if feedback.demo_id not in self._history:
            self._history[feedback.demo_id] = DemoHistory(
                demo_id=feedback.demo_id,
                demo_name=feedback.demo_name,
            )
        self._history[feedback.demo_id].feedbacks.append(feedback)

    def _save(self) -> None:
        """Persist all feedback to JSON."""
        data: dict = {}
        for demo_id, history in self._history.items():
            data[str(demo_id)] = {
                "demo_id": history.demo_id,
                "demo_name": history.demo_name,
                "feedbacks": [asdict(f) for f in history.feedbacks],
            }
        self._feedback_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _load(self) -> None:
        """Load persisted feedback from JSON."""
        if not self._feedback_path.exists():
            return
        try:
            data = json.loads(self._feedback_path.read_text(encoding="utf-8"))
            for key, hist_data in data.items():
                demo_id = hist_data["demo_id"]
                history = DemoHistory(
                    demo_id=demo_id,
                    demo_name=hist_data.get("demo_name", f"Demo {demo_id}"),
                )
                for f_data in hist_data.get("feedbacks", []):
                    history.feedbacks.append(DemoFeedback(
                        demo_id=f_data.get("demo_id", demo_id),
                        demo_name=f_data.get("demo_name", ""),
                        timestamp=f_data.get("timestamp", 0),
                        accuracy=f_data.get("accuracy", 0),
                        completeness=f_data.get("completeness", 0),
                        efficiency=f_data.get("efficiency", 0),
                        notes=f_data.get("notes", ""),
                        correct_approach=f_data.get("correct_approach", ""),
                        steps=f_data.get("steps", 0),
                        elapsed=f_data.get("elapsed", 0.0),
                        success=f_data.get("success", False),
                        gif_path=f_data.get("gif_path", ""),
                    ))
                self._history[demo_id] = history
        except Exception:
            pass  # Start fresh on corruption
