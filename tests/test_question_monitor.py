"""Tests for question_monitor phash change detection."""

from __future__ import annotations

import pytest
from PIL import Image, ImageDraw

pytest.importorskip("mss")
import config  # noqa: E402
import question_monitor  # noqa: E402


def test_has_question_changed_after_update() -> None:
    """Different frames should register as changed."""
    question_monitor.reset_monitor()
    a = Image.new("RGB", (200, 100), (255, 255, 255))
    question_monitor.update_last_seen(a)
    b = Image.new("RGB", (200, 100), (255, 255, 255))
    draw = ImageDraw.Draw(b)
    draw.text((10, 10), "New question 99", fill=(0, 0, 0))
    assert question_monitor.has_question_changed(b) is True


def test_has_question_changed_same_frame() -> None:
    """Identical frame should not register as changed."""
    question_monitor.reset_monitor()
    frame = Image.new("RGB", (100, 80), (240, 240, 240))
    question_monitor.update_last_seen(frame)
    assert question_monitor.has_question_changed(frame.copy()) is False


def test_change_threshold_from_config() -> None:
    """change_threshold is read from config."""
    config.load_config()
    assert config.get_config().get("change_threshold", 10) >= 1
