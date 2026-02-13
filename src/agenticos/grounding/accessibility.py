"""Windows UI Automation (UIA) based grounding.

Extracts a structured accessibility tree of all interactive UI elements
using pywinauto's UIA backend. This is the primary grounding method —
fast, precise, and requires no GPU.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from agenticos.utils.exceptions import GroundingError


@dataclass
class UIElement:
    """A detected UI element from the accessibility tree.

    Attributes:
        name: Display name of the element.
        control_type: Type of control (Button, Edit, MenuItem, etc.).
        automation_id: Unique automation identifier.
        class_name: Win32 class name.
        bbox: Bounding box as (left, top, right, bottom).
        center: Center point as (x, y).
        is_enabled: Whether the element is enabled.
        is_visible: Whether the element is visible on screen.
        value: Current value (for text fields, etc.).
        children_count: Number of child elements.
        depth: Depth in the UI tree.
        handle: Window handle (HWND).
        idx: Index assigned during enumeration.
    """

    name: str
    control_type: str
    automation_id: str = ""
    class_name: str = ""
    bbox: tuple[int, int, int, int] = (0, 0, 0, 0)
    center: tuple[int, int] = (0, 0)
    is_enabled: bool = True
    is_visible: bool = True
    value: Optional[str] = None
    children_count: int = 0
    depth: int = 0
    handle: int = 0
    idx: int = 0

    def to_dict(self) -> dict:
        """Convert to dictionary for LLM consumption.

        Returns:
            Dict with all element properties.
        """
        return {
            "idx": self.idx,
            "name": self.name,
            "control_type": self.control_type,
            "automation_id": self.automation_id,
            "bbox": list(self.bbox),
            "center": list(self.center),
            "is_enabled": self.is_enabled,
            "value": self.value,
        }

    def description(self) -> str:
        """Human-readable description of this element.

        Returns:
            String like '[3] Button "Save" at (500, 300)'.
        """
        name_str = f' "{self.name}"' if self.name else ""
        return f"[{self.idx}] {self.control_type}{name_str} at {self.center}"


class UIAGrounder:
    """Grounding via Windows UI Automation accessibility tree.

    Uses pywinauto's UIA backend to enumerate all interactive elements
    on the current screen or within a specific window.

    Example:
        >>> grounder = UIAGrounder()
        >>> elements = grounder.detect()
        >>> for elem in elements:
        ...     print(elem.description())
        [0] Button "File" at (50, 25)
        [1] Button "Edit" at (100, 25)
        [2] Edit "" at (400, 300)
    """

    # Control types we consider "interactive"
    INTERACTIVE_TYPES = {
        "Button",
        "Edit",
        "ComboBox",
        "CheckBox",
        "RadioButton",
        "MenuItem",
        "TabItem",
        "ListItem",
        "TreeItem",
        "Hyperlink",
        "Slider",
        "Spinner",
        "MenuBar",
        "Menu",
        "ToolBar",
        "DataGrid",
        "DataItem",
        "ScrollBar",
    }

    def __init__(
        self,
        max_depth: int = 8,
        interactive_only: bool = True,
        min_size: int = 5,
    ) -> None:
        """Initialize UIA grounder.

        Args:
            max_depth: Maximum depth to traverse in the UI tree.
            interactive_only: Only return interactive elements.
            min_size: Minimum element width/height in pixels.
        """
        self.max_depth = max_depth
        self.interactive_only = interactive_only
        self.min_size = min_size

    def detect(
        self,
        window_title: Optional[str] = None,
        process_id: Optional[int] = None,
    ) -> list[UIElement]:
        """Detect all UI elements on screen or in a specific window.

        Args:
            window_title: If specified, only detect elements in this window.
            process_id: If specified, only detect elements from this process.

        Returns:
            List of UIElement objects found.

        Raises:
            GroundingError: If UI Automation access fails.
        """
        try:
            from pywinauto import Desktop
            from pywinauto.application import Application

            start = time.perf_counter()
            elements: list[UIElement] = []

            if window_title:
                # Connect to specific window
                try:
                    app = Application(backend="uia").connect(
                        title_re=f".*{window_title}.*",
                        timeout=5,
                    )
                    window = app.top_window()
                    self._walk_tree(window.wrapper_object(), elements, depth=0)
                except Exception as e:
                    raise GroundingError(
                        f"Could not connect to window '{window_title}': {e}"
                    ) from e
            elif process_id:
                try:
                    app = Application(backend="uia").connect(process=process_id)
                    window = app.top_window()
                    self._walk_tree(window.wrapper_object(), elements, depth=0)
                except Exception as e:
                    raise GroundingError(
                        f"Could not connect to process {process_id}: {e}"
                    ) from e
            else:
                # Enumerate all top-level windows
                desktop = Desktop(backend="uia")
                for win in desktop.windows():
                    try:
                        if not win.is_visible():
                            continue
                        self._walk_tree(win, elements, depth=0)
                    except Exception:
                        continue  # Skip inaccessible windows

            # Assign indices
            for i, elem in enumerate(elements):
                elem.idx = i

            elapsed_ms = (time.perf_counter() - start) * 1000
            return elements

        except ImportError:
            raise GroundingError(
                "pywinauto is required for UIA grounding. "
                "Install with: pip install pywinauto"
            )
        except GroundingError:
            raise
        except Exception as e:
            raise GroundingError(f"UIA grounding failed: {e}") from e

    def detect_focused_window(self) -> list[UIElement]:
        """Detect elements in the currently focused/foreground window.

        Returns:
            List of UIElement objects in the active window.
        """
        try:
            import win32gui  # type: ignore[import]

            hwnd = win32gui.GetForegroundWindow()
            title = win32gui.GetWindowText(hwnd)
            if title:
                return self.detect(window_title=title)
            return []
        except ImportError:
            raise GroundingError("pywin32 is required for focused window detection")

    def get_element_tree_text(
        self,
        window_title: Optional[str] = None,
    ) -> str:
        """Get a text representation of the UI tree for LLM consumption.

        Args:
            window_title: Optional window to scope the tree to.

        Returns:
            Formatted string describing all detected elements.
        """
        elements = self.detect(window_title=window_title)
        if not elements:
            return "No interactive UI elements detected."

        lines = [f"Detected {len(elements)} interactive UI elements:"]
        for elem in elements:
            indent = "  " * min(elem.depth, 4)
            lines.append(f"{indent}{elem.description()}")

        return "\n".join(lines)

    def _walk_tree(
        self,
        element: object,
        results: list[UIElement],
        depth: int,
    ) -> None:
        """Recursively walk the UI automation tree.

        Args:
            element: pywinauto wrapper element.
            results: Accumulator list for found elements.
            depth: Current depth in the tree.
        """
        if depth > self.max_depth:
            return

        try:
            # Get element properties
            props = element.element_info  # type: ignore[attr-defined]
            control_type = props.control_type or ""
            name = props.name or ""

            # Filter to interactive types
            if self.interactive_only and control_type not in self.INTERACTIVE_TYPES:
                pass  # Still recurse into children
            else:
                # Get bounding rectangle
                try:
                    rect = element.rectangle()  # type: ignore[attr-defined]
                    bbox = (rect.left, rect.top, rect.right, rect.bottom)
                    w = rect.right - rect.left
                    h = rect.bottom - rect.top

                    # Filter out tiny/invisible elements
                    if w >= self.min_size and h >= self.min_size:
                        center = (rect.left + w // 2, rect.top + h // 2)

                        # Try to get value
                        value = None
                        try:
                            value = element.window_text()  # type: ignore[attr-defined]
                            if value == name:
                                value = None
                        except Exception:
                            pass

                        # Get child count
                        try:
                            children = element.children()  # type: ignore[attr-defined]
                            children_count = len(children)
                        except Exception:
                            children_count = 0

                        ui_elem = UIElement(
                            name=name,
                            control_type=control_type,
                            automation_id=getattr(props, "automation_id", "") or "",
                            class_name=getattr(props, "class_name", "") or "",
                            bbox=bbox,
                            center=center,
                            is_enabled=getattr(props, "enabled", True),
                            is_visible=getattr(props, "visible", True),
                            value=value,
                            children_count=children_count,
                            depth=depth,
                            handle=getattr(props, "handle", 0) or 0,
                        )
                        results.append(ui_elem)
                except Exception:
                    pass

            # Recurse into children
            try:
                for child in element.children():  # type: ignore[attr-defined]
                    self._walk_tree(child, results, depth + 1)
            except Exception:
                pass

        except Exception:
            pass  # Skip inaccessible elements
