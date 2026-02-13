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
            bbox=(100, 200, 180, 230),
            center=(140, 215),
        )
        assert elem.name == "OK"
        assert elem.control_type == "Button"
        assert elem.bbox == (100, 200, 180, 230)

    def test_to_dict(self):
        elem = UIElement(
            name="Save",
            control_type="Button",
            automation_id="btn_save",
            class_name="Button",
            is_enabled=True,
            is_visible=True,
            bbox=(50, 50, 150, 90),
            center=(100, 70),
            idx=3,
        )
        d = elem.to_dict()
        assert d["name"] == "Save"
        assert d["control_type"] == "Button"
        assert "bbox" in d
        assert d["idx"] == 3

    def test_description(self):
        elem = UIElement(
            name="File",
            control_type="MenuItem",
            automation_id="menu_file",
            class_name="MenuItem",
            is_enabled=True,
            is_visible=True,
            bbox=(10, 10, 70, 35),
            center=(40, 22),
            idx=1,
        )
        desc = elem.description()
        assert "File" in desc
        assert "MenuItem" in desc

    def test_center_coords(self):
        elem = UIElement(
            name="Test",
            control_type="Button",
            automation_id="test",
            class_name="Button",
            is_enabled=True,
            is_visible=True,
            bbox=(100, 200, 180, 240),
            center=(140, 220),
        )
        assert elem.center == (140, 220)


class TestUIAGrounder:
    """Tests for the UIAGrounder."""

    def test_init(self):
        grounder = UIAGrounder()
        assert grounder is not None

    def test_init_custom_params(self):
        grounder = UIAGrounder(max_depth=5, interactive_only=False, min_size=10)
        assert grounder.max_depth == 5
