"""OCR-based grounding for text element detection.

Uses OCR to find text elements on screen with their bounding boxes.
Serves as a lightweight middle layer between UIA and full VLM grounding.
"""

from __future__ import annotations

import time
from typing import Optional

import numpy as np

from agenticos.grounding.accessibility import UIElement
from agenticos.observation.screenshot import Screenshot
from agenticos.utils.exceptions import GroundingError


class OCRGrounder:
    """OCR-based text element detection.

    Uses RapidOCR (ONNX-based, no GPU required) or falls back to
    Windows.Media.OCR for text detection with bounding boxes.

    Example:
        >>> grounder = OCRGrounder()
        >>> elements = grounder.detect(screenshot)
        >>> for elem in elements:
        ...     print(f"Text: {elem.name} at {elem.center}")
    """

    def __init__(self, confidence_threshold: float = 0.5) -> None:
        """Initialize OCR grounder.

        Args:
            confidence_threshold: Minimum confidence for detected text (0-1).
        """
        self.confidence_threshold = confidence_threshold
        self._ocr_engine: object = None

    def _get_engine(self) -> object:
        """Lazy-initialize OCR engine."""
        if self._ocr_engine is None:
            try:
                from rapidocr_onnxruntime import RapidOCR
                self._ocr_engine = RapidOCR()
            except ImportError:
                raise GroundingError(
                    "rapidocr-onnxruntime is required for OCR grounding. "
                    "Install with: pip install rapidocr-onnxruntime"
                )
        return self._ocr_engine

    def detect(self, screenshot: Screenshot) -> list[UIElement]:
        """Detect text elements in a screenshot using OCR.

        Args:
            screenshot: Screenshot to analyze.

        Returns:
            List of UIElement objects for detected text regions.

        Raises:
            GroundingError: If OCR fails.
        """
        try:
            engine = self._get_engine()
            img_array = screenshot.to_numpy()

            start = time.perf_counter()
            result, elapse = engine(img_array)  # type: ignore
            elapsed_ms = (time.perf_counter() - start) * 1000

            if result is None:
                return []

            elements: list[UIElement] = []
            for i, (bbox_points, text, confidence) in enumerate(result):
                if confidence < self.confidence_threshold:
                    continue

                # bbox_points is [[x1,y1],[x2,y2],[x3,y3],[x4,y4]] (polygon)
                xs = [p[0] for p in bbox_points]
                ys = [p[1] for p in bbox_points]
                left = int(min(xs))
                top = int(min(ys))
                right = int(max(xs))
                bottom = int(max(ys))

                w = right - left
                h = bottom - top
                center = (left + w // 2, top + h // 2)

                elements.append(
                    UIElement(
                        name=text,
                        control_type="Text",
                        bbox=(left, top, right, bottom),
                        center=center,
                        idx=i,
                        value=text,
                        depth=0,
                    )
                )

            return elements

        except GroundingError:
            raise
        except Exception as e:
            raise GroundingError(f"OCR grounding failed: {e}") from e

    def detect_text_at(
        self, screenshot: Screenshot, x: int, y: int, radius: int = 50
    ) -> Optional[str]:
        """Detect text near a specific screen coordinate.

        Args:
            screenshot: Screenshot to analyze.
            x: X coordinate to search near.
            y: Y coordinate to search near.
            radius: Search radius in pixels.

        Returns:
            Detected text near the coordinate, or None.
        """
        elements = self.detect(screenshot)
        best_match: Optional[UIElement] = None
        best_distance = float("inf")

        for elem in elements:
            dx = elem.center[0] - x
            dy = elem.center[1] - y
            distance = (dx * dx + dy * dy) ** 0.5

            if distance < radius and distance < best_distance:
                best_distance = distance
                best_match = elem

        return best_match.name if best_match else None

    def get_all_text(self, screenshot: Screenshot) -> str:
        """Extract all visible text from the screenshot.

        Args:
            screenshot: Screenshot to analyze.

        Returns:
            All detected text concatenated with newlines.
        """
        elements = self.detect(screenshot)
        # Sort by vertical position then horizontal
        elements.sort(key=lambda e: (e.center[1] // 20, e.center[0]))
        return "\n".join(e.name for e in elements if e.name)
