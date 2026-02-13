"""GIF recording of agent sessions for demos and debugging.

Records screen activity during agent task execution and produces
optimized GIF files suitable for GitHub issue embedding (<10MB).
"""

from __future__ import annotations

import io
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import imageio
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from agenticos.observation.screenshot import ScreenCapture


@dataclass
class RecordingFrame:
    """A single frame in a recording.

    Attributes:
        image: RGB numpy array (H, W, 3).
        timestamp: Unix timestamp.
        annotation: Optional text annotation to overlay.
    """
    image: np.ndarray
    timestamp: float
    annotation: Optional[str] = None


class GifRecorder:
    """Records screen activity as optimized GIF files.

    Captures frames at a configurable FPS, with optional text annotations
    and bounding box overlays. Produces GIFs suitable for GitHub embedding.

    Example:
        >>> recorder = GifRecorder(fps=5, max_duration=30)
        >>> recorder.start()
        >>> # ... agent performs actions ...
        >>> recorder.add_annotation("Clicking File menu")
        >>> # ... more actions ...
        >>> recorder.stop()
        >>> recorder.save("demo.gif")
    """

    def __init__(
        self,
        fps: int = 5,
        max_duration: int = 60,
        scale: float = 0.5,
        monitor: int = 1,
        max_width: int = 720,
    ) -> None:
        """Initialize the GIF recorder.

        Args:
            fps: Frames per second to capture.
            max_duration: Maximum recording duration in seconds.
            scale: Scale factor for captured frames.
            monitor: Monitor index to capture.
            max_width: Maximum width for output GIF (for size optimization).
        """
        self.fps = fps
        self.max_duration = max_duration
        self.scale = scale
        self.monitor = monitor
        self.max_width = max_width

        self._frames: list[RecordingFrame] = []
        self._recording = False
        self._thread: Optional[threading.Thread] = None
        self._capture = ScreenCapture(monitor=monitor, scale=scale)
        self._current_annotation: Optional[str] = None
        self._lock = threading.Lock()

    def start(self) -> None:
        """Start recording in a background thread."""
        if self._recording:
            return

        self._frames = []
        self._recording = True
        self._thread = threading.Thread(target=self._record_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop recording."""
        self._recording = False
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None

    def add_annotation(self, text: str) -> None:
        """Set annotation text to overlay on subsequent frames.

        Args:
            text: Annotation text (e.g., "Clicking Save button").
        """
        with self._lock:
            self._current_annotation = text

    def clear_annotation(self) -> None:
        """Remove current annotation."""
        with self._lock:
            self._current_annotation = None

    def add_bounding_box(
        self,
        frame_idx: int,
        bbox: tuple[int, int, int, int],
        label: str = "",
        color: str = "red",
    ) -> None:
        """Draw a bounding box on a specific frame.

        Args:
            frame_idx: Index of the frame to annotate.
            bbox: (left, top, right, bottom) in pixels.
            label: Optional label text above the box.
            color: Box color name.
        """
        if 0 <= frame_idx < len(self._frames):
            frame = self._frames[frame_idx]
            img = Image.fromarray(frame.image)
            draw = ImageDraw.Draw(img)
            draw.rectangle(bbox, outline=color, width=3)
            if label:
                draw.text((bbox[0], bbox[1] - 15), label, fill=color)
            frame.image = np.array(img)

    @property
    def frame_count(self) -> int:
        """Number of frames captured so far."""
        return len(self._frames)

    @property
    def is_recording(self) -> bool:
        """Whether recording is active."""
        return self._recording

    def _record_loop(self) -> None:
        """Background recording loop."""
        interval = 1.0 / self.fps
        start_time = time.time()

        while self._recording:
            elapsed = time.time() - start_time
            if elapsed >= self.max_duration:
                self._recording = False
                break

            try:
                screenshot = self._capture.grab()
                frame_array = screenshot.to_numpy()

                # Apply annotation if set
                with self._lock:
                    annotation = self._current_annotation

                if annotation:
                    frame_array = self._overlay_text(frame_array, annotation)

                self._frames.append(
                    RecordingFrame(
                        image=frame_array,
                        timestamp=time.time(),
                        annotation=annotation,
                    )
                )
            except Exception:
                pass  # Skip failed frames silently

            # Sleep until next frame
            next_frame_time = start_time + (len(self._frames)) * interval
            sleep_time = next_frame_time - time.time()
            if sleep_time > 0:
                time.sleep(sleep_time)

    def _overlay_text(self, frame: np.ndarray, text: str) -> np.ndarray:
        """Overlay annotation text on a frame.

        Args:
            frame: RGB numpy array.
            text: Text to overlay.

        Returns:
            Frame with text overlay.
        """
        img = Image.fromarray(frame)
        draw = ImageDraw.Draw(img)

        # Draw semi-transparent background bar
        bar_height = 30
        bar = Image.new("RGBA", (img.width, bar_height), (0, 0, 0, 180))
        img.paste(
            Image.alpha_composite(
                Image.new("RGBA", bar.size, (0, 0, 0, 0)), bar
            ).convert("RGB"),
            (0, img.height - bar_height),
        )

        # Draw text
        try:
            font = ImageFont.truetype("arial.ttf", 16)
        except (OSError, IOError):
            font = ImageFont.load_default()

        draw.text(
            (10, img.height - bar_height + 5),
            text,
            fill="white",
            font=font,
        )

        return np.array(img)

    def save(self, path: str, optimize: bool = True) -> str:
        """Save recorded frames as a GIF file.

        Args:
            path: Output file path.
            optimize: Whether to optimize GIF size.

        Returns:
            The path to the saved GIF file.
        """
        if not self._frames:
            raise ValueError("No frames recorded")

        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Resize frames for optimal GIF size
        processed_frames = []
        for frame in self._frames:
            img = Image.fromarray(frame.image)

            # Downscale to max_width
            if img.width > self.max_width:
                ratio = self.max_width / img.width
                new_size = (self.max_width, int(img.height * ratio))
                img = img.resize(new_size, Image.LANCZOS)

            processed_frames.append(np.array(img))

        # Write GIF using imageio
        imageio.mimsave(
            str(output_path),
            processed_frames,
            fps=self.fps,
            loop=0,
        )

        return str(output_path)

    def save_to_bytes(self) -> bytes:
        """Save recorded frames as GIF bytes (for embedding).

        Returns:
            GIF file bytes.
        """
        if not self._frames:
            raise ValueError("No frames recorded")

        processed_frames = []
        for frame in self._frames:
            img = Image.fromarray(frame.image)
            if img.width > self.max_width:
                ratio = self.max_width / img.width
                new_size = (self.max_width, int(img.height * ratio))
                img = img.resize(new_size, Image.LANCZOS)
            processed_frames.append(np.array(img))

        buffer = io.BytesIO()
        imageio.mimsave(buffer, processed_frames, format="GIF", fps=self.fps, loop=0)
        return buffer.getvalue()

    def __enter__(self) -> "GifRecorder":
        self.start()
        return self

    def __exit__(self, *args: object) -> None:
        self.stop()

    def __del__(self) -> None:
        self.stop()
        self._capture.close()
