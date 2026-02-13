"""Fast screenshot capture using mss.

This module provides high-performance screen capture for the AgenticOS
observation pipeline. It uses the mss library for zero-dependency,
cross-platform screenshot capture with minimal latency.
"""

from __future__ import annotations

import base64
import io
import time
from dataclasses import dataclass, field
from typing import Optional

import mss
import numpy as np
from PIL import Image

from agenticos.utils.exceptions import ScreenCaptureError


@dataclass
class Screenshot:
    """A captured screenshot with metadata.

    Attributes:
        image: PIL Image of the screenshot.
        width: Width in pixels.
        height: Height in pixels.
        timestamp: Unix timestamp of capture.
        monitor_index: Which monitor was captured.
        capture_time_ms: Time taken to capture in milliseconds.
    """

    image: Image.Image
    width: int
    height: int
    timestamp: float
    monitor_index: int
    capture_time_ms: float
    _numpy_cache: Optional[np.ndarray] = field(default=None, repr=False)

    def to_numpy(self) -> np.ndarray:
        """Convert to numpy array (RGB, HWC format).

        Returns:
            numpy array of shape (H, W, 3) in RGB format.
        """
        if self._numpy_cache is None:
            self._numpy_cache = np.array(self.image)
        return self._numpy_cache

    def to_base64(self, format: str = "PNG", max_dimension: int = 1568) -> str:
        """Encode screenshot as base64 string for LLM consumption.

        Optionally downscales to fit within max_dimension (Claude's recommended
        max is 1568px on longest edge for optimal token usage).

        Args:
            format: Image format (PNG or JPEG).
            max_dimension: Maximum pixel dimension on longest edge.

        Returns:
            Base64-encoded image string.
        """
        img = self.image
        # Downscale if needed (Claude Computer Use recommends ≤1568px longest edge)
        if max(img.width, img.height) > max_dimension:
            ratio = max_dimension / max(img.width, img.height)
            new_size = (int(img.width * ratio), int(img.height * ratio))
            img = img.resize(new_size, Image.LANCZOS)

        buffer = io.BytesIO()
        img.save(buffer, format=format)
        return base64.b64encode(buffer.getvalue()).decode("utf-8")

    def to_bytes(self, format: str = "PNG") -> bytes:
        """Encode screenshot as bytes.

        Args:
            format: Image format (PNG or JPEG).

        Returns:
            Image bytes.
        """
        buffer = io.BytesIO()
        self.image.save(buffer, format=format)
        return buffer.getvalue()

    def save(self, path: str, format: str = "PNG") -> None:
        """Save screenshot to file.

        Args:
            path: File path to save to.
            format: Image format.
        """
        self.image.save(path, format=format)


class ScreenCapture:
    """High-performance screen capture using mss.

    Provides fast, low-latency screenshot capture with optional scaling
    and format conversion for LLM consumption.

    Example:
        >>> capture = ScreenCapture()
        >>> screenshot = capture.grab()
        >>> base64_img = screenshot.to_base64()
        >>> print(f"Captured {screenshot.width}x{screenshot.height} in {screenshot.capture_time_ms:.1f}ms")
    """

    def __init__(self, monitor: int = 1, scale: float = 1.0) -> None:
        """Initialize screen capture.

        Args:
            monitor: Monitor index (1 = primary, 0 = all monitors combined).
            scale: Scale factor for output (0.5 = half resolution).
        """
        self.monitor = monitor
        self.scale = scale
        self._sct: Optional[mss.mss] = None

    def _get_sct(self) -> mss.mss:
        """Get or create mss instance (lazy init)."""
        if self._sct is None:
            self._sct = mss.mss()
        return self._sct

    def grab(self, region: Optional[dict] = None) -> Screenshot:
        """Capture a screenshot.

        Args:
            region: Optional dict with keys 'left', 'top', 'width', 'height'
                    to capture a specific region. If None, captures full monitor.

        Returns:
            Screenshot object with image and metadata.

        Raises:
            ScreenCaptureError: If capture fails.
        """
        try:
            sct = self._get_sct()
            start = time.perf_counter()

            if region:
                monitor = region
            else:
                monitor = sct.monitors[self.monitor]

            raw = sct.grab(monitor)

            # Convert BGRA → RGB PIL Image
            img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")

            # Apply scaling if needed
            if self.scale != 1.0:
                new_size = (int(img.width * self.scale), int(img.height * self.scale))
                img = img.resize(new_size, Image.LANCZOS)

            elapsed_ms = (time.perf_counter() - start) * 1000

            return Screenshot(
                image=img,
                width=img.width,
                height=img.height,
                timestamp=time.time(),
                monitor_index=self.monitor,
                capture_time_ms=elapsed_ms,
            )

        except Exception as e:
            raise ScreenCaptureError(f"Failed to capture screen: {e}") from e

    def get_screen_size(self) -> tuple[int, int]:
        """Get the size of the configured monitor.

        Returns:
            Tuple of (width, height) in pixels.
        """
        sct = self._get_sct()
        mon = sct.monitors[self.monitor]
        return mon["width"], mon["height"]

    def close(self) -> None:
        """Release mss resources."""
        if self._sct is not None:
            self._sct.close()
            self._sct = None

    def __enter__(self) -> "ScreenCapture":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def __del__(self) -> None:
        self.close()
