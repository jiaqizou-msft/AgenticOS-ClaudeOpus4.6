"""Human-in-the-loop teaching and demonstration learning.

Allows AgenticOS to:
1. ASK the human to demonstrate specific UI tasks it struggles with
2. RECORD the human's mouse/keyboard actions with screenshots
3. LEARN action patterns from the demonstration
4. GENERALIZE the learned pattern to similar contexts
5. AMORTIZE future actions by replaying learned demonstrations

This implements a "learning from demonstration" (LfD) approach where
the agent identifies its own weaknesses and requests targeted teaching.
"""

from __future__ import annotations

import json
import hashlib
import time
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Callable

from agenticos.utils.exceptions import ActionError


@dataclass
class DemoAction:
    """A single action captured during human demonstration."""
    timestamp: float
    action_type: str       # "mouse_move", "click", "key_press", "drag", "scroll"
    params: dict           # Action-specific parameters
    window_title: str = ""
    element_at_cursor: str = ""   # Name of UI element under cursor
    screenshot_hash: str = ""     # For state context


@dataclass
class DemoRecording:
    """A complete human demonstration recording."""
    topic: str                # What was being demonstrated
    description: str          # Detailed description
    actions: list[DemoAction] = field(default_factory=list)
    start_time: float = 0.0
    end_time: float = 0.0
    success: bool = False
    context_key: str = ""     # Hashed context for lookup
    generalized: bool = False # Whether patterns have been extracted

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time

    @property
    def action_count(self) -> int:
        return len(self.actions)


@dataclass
class LearnedPattern:
    """An abstracted pattern extracted from demonstrations.

    Generalized from specific coordinates to relative positions,
    element-based targeting, and action sequences.
    """
    topic: str
    trigger_context: str     # When to apply this pattern
    action_sequence: list[dict]  # Sequence of abstract actions
    source_demos: int = 0    # How many demos this was learned from
    success_rate: float = 0.0
    use_count: int = 0
    created_at: float = 0.0


# ── Topics the agent may want to learn from humans ──
# Each topic describes a UI task the agent can request demonstration for.
TEACHING_TOPICS = [
    {
        "id": "slider_adjust",
        "topic": "Adjusting a slider control",
        "description": (
            "Please demonstrate how to drag a slider to a specific value. "
            "Open the Windows Quick Settings (click the system tray icons at bottom-right), "
            "then drag the brightness or volume slider to change it. "
            "I want to learn the precise mouse movement pattern for slider manipulation."
        ),
        "difficulty": "medium",
        "category": "ui_control",
    },
    {
        "id": "address_bar_navigate",
        "topic": "Navigating to a URL in a browser",
        "description": (
            "Please demonstrate navigating to a website in Microsoft Edge. "
            "Show me how you click the address bar (or use Ctrl+L), type a URL, "
            "and press Enter. I want to learn the precise click location and flow."
        ),
        "difficulty": "easy",
        "category": "browser",
    },
    {
        "id": "search_and_click",
        "topic": "Searching and clicking a result",
        "description": (
            "Please demonstrate searching for something (in a browser, file explorer, "
            "or any app with a search box). Type a query, wait for results, "
            "and click the correct result. I want to learn the timing and targeting."
        ),
        "difficulty": "easy",
        "category": "navigation",
    },
    {
        "id": "compose_email",
        "topic": "Composing and sending an email in Outlook",
        "description": (
            "Please demonstrate composing a new email in Outlook. "
            "Click New Mail, fill in To/Subject/Body fields, and send. "
            "I want to learn field navigation and the send flow."
        ),
        "difficulty": "medium",
        "category": "office",
    },
    {
        "id": "send_teams_message",
        "topic": "Sending a message in Teams",
        "description": (
            "Please demonstrate sending a chat message in Microsoft Teams. "
            "Open Teams, find a chat or person, click the message box, type, and send. "
            "I want to learn the UI flow for Teams messaging."
        ),
        "difficulty": "medium",
        "category": "office",
    },
    {
        "id": "context_menu",
        "topic": "Using right-click context menus",
        "description": (
            "Please demonstrate using a right-click context menu. "
            "Right-click on a file/element, then select an option from the menu. "
            "I want to learn the timing and precision needed."
        ),
        "difficulty": "easy",
        "category": "ui_control",
    },
    {
        "id": "window_management",
        "topic": "Arranging windows (snap, resize, minimize)",
        "description": (
            "Please demonstrate window management: snap a window to half screen, "
            "resize it by dragging edges, minimize and restore. "
            "I want to learn the drag targets and snap zones."
        ),
        "difficulty": "medium",
        "category": "system",
    },
    {
        "id": "file_drag_drop",
        "topic": "Dragging and dropping files",
        "description": (
            "Please demonstrate dragging a file from one location to another. "
            "Open File Explorer, drag a file between folders or to the desktop. "
            "I want to learn drag precision and drop targeting."
        ),
        "difficulty": "hard",
        "category": "system",
    },
    {
        "id": "scroll_and_find",
        "topic": "Scrolling to find an item",
        "description": (
            "Please demonstrate scrolling through a long list or page to find a "
            "specific item, then clicking on it. I want to learn scroll speed "
            "and recognition patterns."
        ),
        "difficulty": "easy",
        "category": "navigation",
    },
    {
        "id": "multi_step_form",
        "topic": "Filling out a multi-step form",
        "description": (
            "Please demonstrate filling in a form with multiple fields — "
            "text boxes, dropdowns, checkboxes. Tab between fields and submit. "
            "I want to learn the tab flow and field targeting."
        ),
        "difficulty": "medium",
        "category": "ui_control",
    },
    {
        "id": "create_folder",
        "topic": "Creating a new folder in File Explorer",
        "description": (
            "Please demonstrate creating a new folder in File Explorer. "
            "Open File Explorer, navigate to the Downloads folder, "
            "right-click in an empty area and select New > Folder (or use Ctrl+Shift+N), "
            "type the folder name 'TestFromAgenticOS', press Enter to confirm, "
            "then close File Explorer with Alt+F4. "
            "I want to learn the right-click context menu flow, "
            "folder naming, and the keyboard shortcuts for folder creation."
        ),
        "difficulty": "easy",
        "category": "system",
    },
    # ── v2 teaching topics ──
    {
        "id": "edge_tab_management",
        "topic": "Managing browser tabs in Edge",
        "description": (
            "Please demonstrate tab management in Edge: Ctrl+T for new tab, "
            "Ctrl+W to close, Ctrl+Tab to cycle, Ctrl+1-9 to jump to tab. "
            "Show opening 3 tabs, switching between them, and closing one."
        ),
        "difficulty": "medium",
        "category": "browser",
    },
    {
        "id": "teams_meeting_schedule",
        "topic": "Scheduling a meeting in Teams",
        "description": (
            "Please demonstrate scheduling a Teams meeting: open Calendar, "
            "click 'New meeting', fill in title and time, add attendees, "
            "then save. I want to learn the Teams calendar workflow."
        ),
        "difficulty": "medium",
        "category": "communication",
    },
    {
        "id": "outlook_email_compose",
        "topic": "Composing and organizing email in Outlook",
        "description": (
            "Please demonstrate composing a new email in Outlook: Ctrl+N, "
            "fill in To/Subject/Body, then creating a folder by right-clicking "
            "Inbox. Show search with Ctrl+E and flagging an email."
        ),
        "difficulty": "medium",
        "category": "communication",
    },
    {
        "id": "settings_navigation",
        "topic": "Navigating Windows Settings categories",
        "description": (
            "Please demonstrate navigating Windows Settings efficiently: "
            "open Settings with Win+I, navigate to Display, WiFi, Updates, "
            "Accounts. Show how to use the search box and breadcrumb navigation."
        ),
        "difficulty": "easy",
        "category": "system",
    },
    {
        "id": "file_operations",
        "topic": "File operations: rename, copy, search in Explorer",
        "description": (
            "Please demonstrate file operations in Explorer: select a file, "
            "F2 to rename, Ctrl+C/Ctrl+V to copy, Ctrl+E to search, "
            "and changing the View to Details. Show column sorting too."
        ),
        "difficulty": "easy",
        "category": "system",
    },
    {
        "id": "office_basics",
        "topic": "Basic Office app operations",
        "description": (
            "Please demonstrate basic Office operations: create a blank doc in Word, "
            "create a blank workbook in Excel with SUM formula, "
            "create a blank presentation in PowerPoint with title text."
        ),
        "difficulty": "medium",
        "category": "office",
    },
]


class HumanTeacher:
    """Manages human teaching sessions for the agent.

    Workflow:
    1. Agent identifies a weakness → calls request_teaching()
    2. Human is prompted with a specific task to demonstrate
    3. Agent records the demonstration via start/stop_recording()
    4. Agent extracts patterns from the recording → learn_from_demo()
    5. Patterns are stored and generalized for future use
    """

    def __init__(self, persist_dir: Optional[str] = None) -> None:
        """Initialize the teaching system.

        Args:
            persist_dir: Directory for saving recordings and patterns.
        """
        self._persist_dir = Path(persist_dir) if persist_dir else Path("recordings/teaching")
        self._persist_dir.mkdir(parents=True, exist_ok=True)

        self._recordings: list[DemoRecording] = []
        self._patterns: dict[str, LearnedPattern] = {}  # topic_id -> pattern
        self._pending_topics: list[dict] = []  # Topics queued for teaching
        self._is_recording: bool = False
        self._current_recording: Optional[DemoRecording] = None
        self._record_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # Load persisted patterns
        self._load_patterns()

    def get_suggested_topics(self, max_topics: int = 3) -> list[dict]:
        """Get topics the agent wants the human to demonstrate.

        Prioritizes topics that haven't been learned yet or have low success.

        Returns:
            List of topic dicts with id, topic, description.
        """
        unlearned = []
        low_success = []

        for t in TEACHING_TOPICS:
            tid = t["id"]
            pattern = self._patterns.get(tid)
            if not pattern:
                unlearned.append(t)
            elif pattern.success_rate < 0.5:
                low_success.append(t)

        # Prioritize: unlearned first, then low-success
        suggestions = unlearned[:max_topics]
        remaining = max_topics - len(suggestions)
        if remaining > 0:
            suggestions.extend(low_success[:remaining])

        return suggestions

    def request_teaching(self, topic_id: str) -> Optional[dict]:
        """Request a specific teaching topic.

        Returns the topic description for displaying to the user,
        or None if the topic is unknown.
        """
        for t in TEACHING_TOPICS:
            if t["id"] == topic_id:
                self._pending_topics.append(t)
                return t
        return None

    def start_recording(self, topic: str, description: str = "") -> None:
        """Start recording a human demonstration.

        Captures mouse movements, clicks, and key presses with timestamps.

        Args:
            topic: What is being demonstrated.
            description: Detailed description of the task.
        """
        if self._is_recording:
            self.stop_recording()

        self._current_recording = DemoRecording(
            topic=topic,
            description=description,
            start_time=time.time(),
        )
        self._is_recording = True
        self._stop_event.clear()

        # Start background capture thread
        self._record_thread = threading.Thread(
            target=self._capture_loop, daemon=True
        )
        self._record_thread.start()

    def stop_recording(self) -> Optional[DemoRecording]:
        """Stop recording and return the captured demonstration."""
        if not self._is_recording:
            return None

        self._stop_event.set()
        self._is_recording = False

        if self._record_thread:
            self._record_thread.join(timeout=3.0)

        recording = self._current_recording
        if recording:
            recording.end_time = time.time()
            recording.success = True
            recording.context_key = self._make_context_key(recording.topic)
            self._recordings.append(recording)
            self._save_recording(recording)

        self._current_recording = None
        return recording

    def learn_from_demo(self, recording: DemoRecording) -> LearnedPattern:
        """Extract generalizable patterns from a demonstration.

        Converts raw mouse/key events into abstract action sequences
        that can be replayed in similar contexts.

        Args:
            recording: The completed demonstration recording.

        Returns:
            Extracted pattern with generalized action sequence.
        """
        # Group raw actions into semantic steps
        steps = self._segment_actions(recording.actions)

        # Abstract coordinates to relative positions
        abstract_sequence = []
        for step in steps:
            abstract_action = self._abstract_action(step)
            if abstract_action:
                abstract_sequence.append(abstract_action)

        pattern = LearnedPattern(
            topic=recording.topic,
            trigger_context=recording.context_key,
            action_sequence=abstract_sequence,
            source_demos=1,
            success_rate=1.0 if recording.success else 0.0,
            created_at=time.time(),
        )

        # Merge with existing pattern if available
        existing = self._patterns.get(recording.topic)
        if existing:
            pattern = self._merge_patterns(existing, pattern)

        self._patterns[recording.topic] = pattern
        recording.generalized = True
        self._save_patterns()

        return pattern

    def lookup_pattern(self, topic_hint: str) -> Optional[LearnedPattern]:
        """Look up a learned pattern by topic or similar context.

        Args:
            topic_hint: Keyword or description to match against.

        Returns:
            Best matching pattern, or None.
        """
        hint_lower = topic_hint.lower()

        # Exact match
        if hint_lower in self._patterns:
            p = self._patterns[hint_lower]
            p.use_count += 1
            return p

        # Fuzzy match by keywords in topic
        best_match = None
        best_score = 0
        for topic, pattern in self._patterns.items():
            score = sum(1 for word in hint_lower.split() if word in topic.lower())
            if score > best_score:
                best_score = score
                best_match = pattern

        if best_match and best_score >= 2:
            best_match.use_count += 1
            return best_match

        return None

    def get_stats(self) -> dict:
        """Get teaching system statistics."""
        return {
            "recordings": len(self._recordings),
            "patterns_learned": len(self._patterns),
            "pending_topics": len(self._pending_topics),
            "total_pattern_uses": sum(p.use_count for p in self._patterns.values()),
            "topics_available": len(TEACHING_TOPICS),
            "topics_unlearned": sum(
                1 for t in TEACHING_TOPICS if t["id"] not in self._patterns
            ),
        }

    # ── Private methods ──

    def _capture_loop(self) -> None:
        """Background thread: capture mouse/key events."""
        try:
            import pyautogui
            last_pos = pyautogui.position()
            sample_interval = 0.1  # 10 Hz sampling

            while not self._stop_event.is_set():
                try:
                    pos = pyautogui.position()
                    # Only record if mouse moved significantly
                    dx = abs(pos[0] - last_pos[0])
                    dy = abs(pos[1] - last_pos[1])

                    if dx > 5 or dy > 5:
                        action = DemoAction(
                            timestamp=time.time(),
                            action_type="mouse_move",
                            params={"x": pos[0], "y": pos[1]},
                        )
                        if self._current_recording:
                            self._current_recording.actions.append(action)
                        last_pos = pos

                    self._stop_event.wait(sample_interval)
                except Exception:
                    break
        except ImportError:
            pass  # pyautogui not available

    def _segment_actions(self, actions: list[DemoAction]) -> list[list[DemoAction]]:
        """Segment raw actions into logical steps.

        Groups consecutive mouse_moves into trajectories,
        identifies click targets, and segments key sequences.
        """
        if not actions:
            return []

        segments: list[list[DemoAction]] = []
        current_segment: list[DemoAction] = []

        for action in actions:
            if action.action_type in ("click", "double_click", "right_click", "key_press"):
                # Clicks/keys end a movement segment and start a new one
                if current_segment:
                    segments.append(current_segment)
                segments.append([action])
                current_segment = []
            else:
                current_segment.append(action)

        if current_segment:
            segments.append(current_segment)

        return segments

    def _abstract_action(self, segment: list[DemoAction]) -> Optional[dict]:
        """Convert a segment of raw actions to an abstract action.

        Abstracts specific coordinates into:
        - Element-relative positions ("click on element X")
        - Screen-relative ratios (x=0.75 of screen width)
        - Trajectory patterns (move right-then-down)
        """
        if not segment:
            return None

        if len(segment) == 1:
            action = segment[0]
            if action.action_type in ("click", "double_click", "right_click"):
                return {
                    "type": action.action_type,
                    "target_element": action.element_at_cursor,
                    "absolute_pos": action.params,
                    "relative_pos": self._to_relative(action.params),
                    "window_title": action.window_title,
                }
            elif action.action_type == "key_press":
                return {
                    "type": "key_press",
                    "key": action.params.get("key", ""),
                }
            return None

        # Movement trajectory — summarize as a drag direction
        if all(a.action_type == "mouse_move" for a in segment):
            start = segment[0].params
            end = segment[-1].params
            dx = end.get("x", 0) - start.get("x", 0)
            dy = end.get("y", 0) - start.get("y", 0)
            return {
                "type": "trajectory",
                "start": self._to_relative(start),
                "end": self._to_relative(end),
                "direction": self._classify_direction(dx, dy),
                "distance": (dx * dx + dy * dy) ** 0.5,
                "duration": segment[-1].timestamp - segment[0].timestamp,
            }

        return None

    def _to_relative(self, params: dict) -> dict:
        """Convert absolute coordinates to relative screen position."""
        try:
            import pyautogui
            sw, sh = pyautogui.size()
            return {
                "rx": round(params.get("x", 0) / sw, 4),
                "ry": round(params.get("y", 0) / sh, 4),
            }
        except Exception:
            return params

    def _classify_direction(self, dx: int, dy: int) -> str:
        """Classify a movement vector into a human-readable direction."""
        if abs(dx) < 10 and abs(dy) < 10:
            return "stationary"
        angle = __import__("math").atan2(dy, dx)
        deg = __import__("math").degrees(angle)
        if -22.5 <= deg < 22.5:
            return "right"
        elif 22.5 <= deg < 67.5:
            return "down-right"
        elif 67.5 <= deg < 112.5:
            return "down"
        elif 112.5 <= deg < 157.5:
            return "down-left"
        elif deg >= 157.5 or deg < -157.5:
            return "left"
        elif -157.5 <= deg < -112.5:
            return "up-left"
        elif -112.5 <= deg < -67.5:
            return "up"
        else:
            return "up-right"

    def _merge_patterns(
        self, existing: LearnedPattern, new: LearnedPattern
    ) -> LearnedPattern:
        """Merge a new pattern with an existing one.

        Keeps the most successful sequence and updates statistics.
        """
        total_demos = existing.source_demos + new.source_demos
        weighted_success = (
            existing.success_rate * existing.source_demos
            + new.success_rate * new.source_demos
        ) / total_demos

        # Keep the newer sequence if it was successful
        sequence = new.action_sequence if new.success_rate > 0.5 else existing.action_sequence

        return LearnedPattern(
            topic=existing.topic,
            trigger_context=existing.trigger_context,
            action_sequence=sequence,
            source_demos=total_demos,
            success_rate=weighted_success,
            use_count=existing.use_count,
            created_at=existing.created_at,
        )

    def _make_context_key(self, topic: str) -> str:
        return hashlib.sha256(topic.lower().encode()).hexdigest()[:12]

    def _save_recording(self, recording: DemoRecording) -> None:
        """Save a recording to disk."""
        path = self._persist_dir / f"recording_{int(recording.start_time)}.json"
        data = {
            "topic": recording.topic,
            "description": recording.description,
            "actions": [
                {
                    "timestamp": a.timestamp,
                    "action_type": a.action_type,
                    "params": a.params,
                    "window_title": a.window_title,
                    "element_at_cursor": a.element_at_cursor,
                }
                for a in recording.actions
            ],
            "start_time": recording.start_time,
            "end_time": recording.end_time,
            "success": recording.success,
            "context_key": recording.context_key,
        }
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _save_patterns(self) -> None:
        """Persist learned patterns to disk."""
        path = self._persist_dir / "learned_patterns.json"
        data = {}
        for topic, pattern in self._patterns.items():
            data[topic] = {
                "topic": pattern.topic,
                "trigger_context": pattern.trigger_context,
                "action_sequence": pattern.action_sequence,
                "source_demos": pattern.source_demos,
                "success_rate": pattern.success_rate,
                "use_count": pattern.use_count,
                "created_at": pattern.created_at,
            }
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _load_patterns(self) -> None:
        """Load persisted patterns from disk."""
        path = self._persist_dir / "learned_patterns.json"
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            for topic, p_data in data.items():
                self._patterns[topic] = LearnedPattern(
                    topic=p_data["topic"],
                    trigger_context=p_data.get("trigger_context", ""),
                    action_sequence=p_data.get("action_sequence", []),
                    source_demos=p_data.get("source_demos", 0),
                    success_rate=p_data.get("success_rate", 0.0),
                    use_count=p_data.get("use_count", 0),
                    created_at=p_data.get("created_at", 0.0),
                )
        except Exception:
            pass  # Start fresh
