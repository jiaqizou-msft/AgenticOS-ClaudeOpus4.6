"""Unit tests for observation modules."""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PIL import Image

from agenticos.observation.screenshot import ScreenCapture, Screenshot


class TestScreenshot:
    """Tests for the Screenshot data class."""

    def setup_method(self):
        """Create a test screenshot."""
        self.image = Image.new("RGB", (1920, 1080), color=(100, 150, 200))
        self.screenshot = Screenshot(
            image=self.image,
            width=1920,
            height=1080,
            timestamp=1000.0,
            monitor_index=1,
            capture_time_ms=5.0,
        )

    def test_to_numpy(self):
        """Test numpy conversion."""
        arr = self.screenshot.to_numpy()
        assert isinstance(arr, np.ndarray)
        assert arr.shape == (1080, 1920, 3)
        assert arr.dtype == np.uint8

    def test_to_numpy_cached(self):
        """Test that numpy result is cached."""
        arr1 = self.screenshot.to_numpy()
        arr2 = self.screenshot.to_numpy()
        assert arr1 is arr2

    def test_to_base64(self):
        """Test base64 encoding."""
        b64 = self.screenshot.to_base64()
        assert isinstance(b64, str)
        assert len(b64) > 0

    def test_to_base64_downscale(self):
        """Test that large images are downscaled."""
        b64_small = self.screenshot.to_base64(max_dimension=100)
        b64_large = self.screenshot.to_base64(max_dimension=5000)
        # Smaller max_dimension should produce smaller base64
        assert len(b64_small) < len(b64_large)

    def test_to_bytes(self):
        """Test bytes encoding."""
        data = self.screenshot.to_bytes()
        assert isinstance(data, bytes)
        assert len(data) > 0

    def test_save(self, tmp_path):
        """Test saving to file."""
        path = str(tmp_path / "test.png")
        self.screenshot.save(path)
        # Verify file exists and is a valid image
        loaded = Image.open(path)
        assert loaded.size == (1920, 1080)


class TestScreenCapture:
    """Tests for the ScreenCapture class."""

    def test_init(self):
        """Test initialization."""
        capture = ScreenCapture(monitor=1, scale=0.5)
        assert capture.monitor == 1
        assert capture.scale == 0.5

    @patch("agenticos.observation.screenshot.mss.mss")
    def test_grab(self, mock_mss_class):
        """Test screenshot capture."""
        # Mock mss
        mock_sct = MagicMock()
        mock_mss_class.return_value = mock_sct

        # Create fake monitor info
        mock_sct.monitors = [
            {"left": 0, "top": 0, "width": 3840, "height": 2160},  # All
            {"left": 0, "top": 0, "width": 1920, "height": 1080},  # Primary
        ]

        # Create fake grab result
        fake_data = bytes([100, 150, 200, 255] * (1920 * 1080))  # BGRA
        mock_grab = MagicMock()
        mock_grab.size = (1920, 1080)
        mock_grab.bgra = fake_data
        mock_sct.grab.return_value = mock_grab

        capture = ScreenCapture(monitor=1)
        screenshot = capture.grab()

        assert isinstance(screenshot, Screenshot)
        assert screenshot.width == 1920
        assert screenshot.height == 1080
        assert screenshot.capture_time_ms > 0

    def test_context_manager(self):
        """Test context manager protocol."""
        capture = ScreenCapture()
        with capture as c:
            assert c is capture

    def test_get_screen_size(self):
        """Test getting screen size (requires display)."""
        try:
            capture = ScreenCapture()
            w, h = capture.get_screen_size()
            assert w > 0
            assert h > 0
        except Exception:
            pytest.skip("No display available")
