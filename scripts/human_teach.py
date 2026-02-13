#!/usr/bin/env python3
"""Human Teaching Script — demonstrate UI tasks for AgenticOS to learn.

This script lets the human demonstrate specific UI tasks that AgenticOS
wants to learn. The demonstration is recorded (mouse + key events +
screenshots) and then analyzed to extract generalizable patterns.

Usage:
    python scripts/human_teach.py --list              # List available topics
    python scripts/human_teach.py --topic slider_adjust  # Teach a topic
    python scripts/human_teach.py --stats             # Show learning stats

Workflow:
    1. Run with --topic <id> to start a teaching session
    2. A countdown gives you time to prepare
    3. Perform the UI task while the script records
    4. Press Ctrl+C or wait for timeout to stop recording
    5. The recording is analyzed and patterns are extracted
"""

from __future__ import annotations

import argparse
import signal
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

# Import directly from the module to avoid heavy __init__ imports (litellm, etc.)
from agenticos.agent.human_teacher import HumanTeacher, TEACHING_TOPICS  # noqa: E402


def list_topics(teacher: HumanTeacher) -> None:
    """List all available teaching topics."""
    suggestions = teacher.get_suggested_topics(max_topics=99)
    print("\n" + "=" * 60)
    print("  AgenticOS — Teaching Topics")
    print("=" * 60)

    for i, topic in enumerate(TEACHING_TOPICS, 1):
        tid = topic["id"]
        learned = tid not in [s["id"] for s in suggestions]
        status = "[LEARNED]" if learned else "[UNLEARNED]"
        print(f"\n  {i}. {status} {topic['topic']}")
        print(f"     ID: {tid}")
        print(f"     Category: {topic['category']} | Difficulty: {topic['difficulty']}")
        desc_lines = topic["description"].split(". ")
        for line in desc_lines[:2]:
            print(f"     {line.strip()}.")

    print(f"\n  Total: {len(TEACHING_TOPICS)} topics")
    stats = teacher.get_stats()
    print(f"  Learned: {stats['patterns_learned']} | "
          f"Recordings: {stats['recordings']} | "
          f"Total uses: {stats['total_pattern_uses']}")
    print("=" * 60)


def teach_topic(teacher: HumanTeacher, topic_id: str) -> None:
    """Run a teaching session for a specific topic."""
    # Find the topic
    topic_info = None
    for t in TEACHING_TOPICS:
        if t["id"] == topic_id:
            topic_info = t
            break

    if not topic_info:
        print(f"Unknown topic: {topic_id}")
        print("Available topics:")
        for t in TEACHING_TOPICS:
            print(f"  {t['id']}: {t['topic']}")
        return

    print("\n" + "=" * 60)
    print(f"  Teaching Session: {topic_info['topic']}")
    print("=" * 60)
    print(f"\n  {topic_info['description']}")
    print(f"\n  Difficulty: {topic_info['difficulty']}")
    print("\n  INSTRUCTIONS:")
    print("  1. Get the relevant app/window ready")
    print("  2. Recording starts after the countdown")
    print("  3. Perform the task naturally — I'll watch and learn")
    print("  4. Press Ctrl+C when done, or wait for 60s timeout")
    print()

    # Countdown
    for i in range(5, 0, -1):
        print(f"  Starting in {i}...", flush=True)
        time.sleep(1)

    print("\n  >>> RECORDING STARTED — perform the task now! <<<\n")

    # Start recording
    teacher.start_recording(
        topic=topic_info["topic"],
        description=topic_info["description"],
    )

    # Wait for Ctrl+C or timeout
    stop = False

    def _signal_handler(sig, frame):
        nonlocal stop
        stop = True

    old_handler = signal.signal(signal.SIGINT, _signal_handler)

    try:
        timeout = 60  # seconds
        start = time.time()
        while not stop and (time.time() - start) < timeout:
            elapsed = time.time() - start
            remaining = timeout - elapsed
            print(f"\r  Recording... {elapsed:.0f}s elapsed "
                  f"({remaining:.0f}s remaining) — Press Ctrl+C to stop",
                  end="", flush=True)
            time.sleep(0.5)
    finally:
        signal.signal(signal.SIGINT, old_handler)

    print("\n\n  >>> RECORDING STOPPED <<<")

    # Stop and get recording
    recording = teacher.stop_recording()
    if not recording:
        print("  No recording captured.")
        return

    print(f"  Duration: {recording.duration:.1f}s")
    print(f"  Actions captured: {recording.action_count}")

    # Learn from the recording
    print("\n  Analyzing demonstration...")
    pattern = teacher.learn_from_demo(recording)
    print(f"  Pattern extracted: {len(pattern.action_sequence)} abstract actions")
    print(f"  Source demos: {pattern.source_demos}")
    print(f"  Success rate: {pattern.success_rate:.0%}")

    print("\n  Thank you for teaching me! The pattern has been saved.")
    print(f"  I can now apply this knowledge in similar situations.")
    print("=" * 60)


def show_stats(teacher: HumanTeacher) -> None:
    """Show learning statistics."""
    stats = teacher.get_stats()
    print("\n" + "=" * 60)
    print("  AgenticOS — Learning Statistics")
    print("=" * 60)
    for key, value in stats.items():
        print(f"  {key}: {value}")
    print("=" * 60)


def main() -> None:
    parser = argparse.ArgumentParser(description="AgenticOS Human Teaching")
    parser.add_argument("--list", action="store_true", help="List teaching topics")
    parser.add_argument("--topic", type=str, help="Topic ID to teach")
    parser.add_argument("--stats", action="store_true", help="Show learning stats")
    args = parser.parse_args()

    teacher = HumanTeacher(persist_dir=str(ROOT / "recordings" / "teaching"))

    if args.list:
        list_topics(teacher)
    elif args.topic:
        teach_topic(teacher, args.topic)
    elif args.stats:
        show_stats(teacher)
    else:
        # Default: list topics with suggestions
        list_topics(teacher)
        print("\n  To teach a topic, run:")
        print("    python scripts/human_teach.py --topic <topic_id>")
        print()


if __name__ == "__main__":
    main()
