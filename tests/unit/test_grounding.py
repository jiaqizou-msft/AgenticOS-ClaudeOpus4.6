"""Unit tests for grounding modules."""

from unittest.mock import MagicMock, patch

import pytest

from agenticos.grounding.accessibility import UIAGrounder, UIElement


class TestUIElement:
    """Tests for the UIElement data class."""

    def test_basic_creation(self):
        elem = UIElement(
            name="OK",
            control_type="Button",
            automation_id="btn_ok",
            class_name="Button",
            is_enabled=True,
            is_visible=True,
            bounding_box=(100, 200, 80, 30),
        )
        assert elem.name == "OK"
        assert elem.control_type == "Button"
        assert elem.bounding_box == (100, 200, 80, 30)

    def test_to_dict(self):
        elem = UIElement(
            name="Save",
            control_type="Button",
            automation_id="btn_save",
            class_name="Button",
            is_enabled=True,
            is_visible=True,
            bounding_box=(50, 50, 100, 40),
        )
        d = elem.to_dict()
        assert d["name"] == "Save"
        assert d["control_type"] == "Button"
        assert "bounding_box" in d

    def test_description(self):
        elem = UIElement(
            name="File",
            control_type="MenuItem",
            automation_id="menu_file",
            class_name="MenuItem",
            is_enabled=True,
            is_visible=True,
            bounding_box=(10, 10, 60, 25),
        )
        desc = elem.description
        assert "File" in desc
        assert "MenuItem" in desc

    def test_center_property(self):
        elem = UIElement(
            name="Test",
            control_type="Button",
            automation_id="test",
            class_name="Button",
            is_enabled=True,
            is_visible=True,
            bounding_box=(100, 200, 80, 40),
        )
        cx, cy = elem.center
        assert cx == 140  # 100 + 80/2
        assert cy == 220  # 200 + 40/2


class TestUIAGrounder:
    """Tests for the UIAGrounder."""

    def test_init(self):
        grounder = UIAGrounder()
        assert grounder is not None

    @patch("agenticos.grounding.accessibility.Desktop")
    def test_detect_empty(self, mock_desktop):
        mock_desktop.return_value.windows.return_value = []
        grounder = UIAGrounder()
        elements = grounder.detect()
        assert isinstance(elements, list)
