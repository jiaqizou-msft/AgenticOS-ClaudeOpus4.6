"""Vision-based grounding using VLM (Vision Language Model).

Sends screenshots to a VLM (Claude, GPT-4o) to identify UI elements
when the UIA accessibility tree is sparse or unavailable. This serves
as the fallback in the hybrid grounding pipeline.
"""

from __future__ import annotations

import json
from typing import Optional

from agenticos.grounding.accessibility import UIElement
from agenticos.observation.screenshot import Screenshot
from agenticos.utils.exceptions import GroundingError

# System prompt for UI element detection
GROUNDING_SYSTEM_PROMPT = """You are a UI element detector. Given a screenshot of a desktop application,
identify all interactive UI elements (buttons, text fields, menus, links, checkboxes, etc.).

For each element, provide:
- name: The visible text or label
- control_type: Button, Edit, MenuItem, CheckBox, ComboBox, Link, Tab, etc.
- bbox: [left, top, right, bottom] pixel coordinates of the bounding box
- description: Brief description of what the element does

Return a JSON array of elements. Example:
[
  {"name": "File", "control_type": "MenuItem", "bbox": [5, 0, 40, 25], "description": "Opens file menu"},
  {"name": "Save", "control_type": "Button", "bbox": [100, 50, 160, 80], "description": "Saves current document"}
]

Be precise with bounding box coordinates. Only include visible, interactive elements.
Return ONLY the JSON array, no other text."""


class VisionGrounder:
    """Vision-based UI element detection using VLM.

    Sends screenshots to a vision-capable LLM to identify interactive
    elements. Used as fallback when UIA grounding returns too few elements.

    Example:
        >>> grounder = VisionGrounder(model="claude-sonnet-4-20250514")
        >>> elements = await grounder.detect(screenshot)
    """

    def __init__(
        self,
        model: str = "claude-sonnet-4-20250514",
        api_key: Optional[str] = None,
        max_tokens: int = 4096,
    ) -> None:
        """Initialize vision grounder.

        Args:
            model: VLM model identifier (litellm format).
            api_key: API key (uses env var if not provided).
            max_tokens: Maximum response tokens.
        """
        self.model = model
        self.api_key = api_key
        self.max_tokens = max_tokens

    async def detect(self, screenshot: Screenshot) -> list[UIElement]:
        """Detect UI elements in a screenshot using VLM.

        Args:
            screenshot: Screenshot to analyze.

        Returns:
            List of detected UIElement objects.

        Raises:
            GroundingError: If VLM call fails or returns invalid data.
        """
        try:
            import litellm

            base64_img = screenshot.to_base64(format="PNG", max_dimension=1568)

            response = await litellm.acompletion(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": GROUNDING_SYSTEM_PROMPT},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{base64_img}"
                                },
                            },
                        ],
                    }
                ],
                max_tokens=self.max_tokens,
                temperature=0.0,
                api_key=self.api_key,
            )

            # Parse response
            content = response.choices[0].message.content
            return self._parse_response(content, screenshot)

        except ImportError:
            raise GroundingError(
                "litellm is required for vision grounding. "
                "Install with: pip install litellm"
            )
        except json.JSONDecodeError as e:
            raise GroundingError(f"VLM returned invalid JSON: {e}")
        except Exception as e:
            raise GroundingError(f"Vision grounding failed: {e}") from e

    def detect_sync(self, screenshot: Screenshot) -> list[UIElement]:
        """Synchronous version of detect.

        Args:
            screenshot: Screenshot to analyze.

        Returns:
            List of detected UIElement objects.
        """
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(asyncio.run, self.detect(screenshot))
                    return future.result()
            else:
                return loop.run_until_complete(self.detect(screenshot))
        except RuntimeError:
            return asyncio.run(self.detect(screenshot))

    def _parse_response(
        self, content: str, screenshot: Screenshot
    ) -> list[UIElement]:
        """Parse VLM response into UIElement objects.

        Args:
            content: Raw VLM response text.
            screenshot: Original screenshot for coordinate validation.

        Returns:
            List of parsed UIElement objects.
        """
        # Try to extract JSON from response
        content = content.strip()
        if content.startswith("```"):
            # Strip markdown code block
            lines = content.split("\n")
            content = "\n".join(lines[1:-1])

        elements_data = json.loads(content)
        if not isinstance(elements_data, list):
            raise GroundingError("VLM response is not a JSON array")

        elements: list[UIElement] = []
        for i, elem_data in enumerate(elements_data):
            try:
                bbox_raw = elem_data.get("bbox", [0, 0, 0, 0])
                bbox = (
                    int(bbox_raw[0]),
                    int(bbox_raw[1]),
                    int(bbox_raw[2]),
                    int(bbox_raw[3]),
                )

                # Validate coordinates are within screen bounds
                bbox = (
                    max(0, min(bbox[0], screenshot.width)),
                    max(0, min(bbox[1], screenshot.height)),
                    max(0, min(bbox[2], screenshot.width)),
                    max(0, min(bbox[3], screenshot.height)),
                )

                w = bbox[2] - bbox[0]
                h = bbox[3] - bbox[1]
                center = (bbox[0] + w // 2, bbox[1] + h // 2)

                elements.append(
                    UIElement(
                        name=str(elem_data.get("name", "")),
                        control_type=str(elem_data.get("control_type", "Unknown")),
                        bbox=bbox,
                        center=center,
                        idx=i,
                        depth=0,
                    )
                )
            except (KeyError, IndexError, ValueError):
                continue  # Skip malformed elements

        return elements
