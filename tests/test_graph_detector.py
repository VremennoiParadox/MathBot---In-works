"""Tests for graph_detector heuristics."""

from __future__ import annotations

import pytest
from PIL import Image, ImageDraw

pytest.importorskip("cv2")
import graph_detector  # noqa: E402


def _make_text_question() -> Image.Image:
    """Plain text question without axes."""
    img = Image.new("RGB", (400, 200), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((20, 20), "Solve: 2x + 5 = 17", fill=(0, 0, 0))
    return img


def _make_fake_graph() -> Image.Image:
    """Synthetic axes + bars."""
    img = Image.new("RGB", (400, 300), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.line((40, 260, 380, 260), fill=(0, 0, 0), width=2)
    draw.line((40, 40, 40, 260), fill=(0, 0, 0), width=2)
    for x in range(80, 360, 40):
        draw.line((x, 255, x, 265), fill=(0, 0, 0), width=1)
    for y in range(60, 260, 40):
        draw.line((35, y, 45, y), fill=(0, 0, 0), width=1)
    draw.rectangle((100, 120, 140, 260), fill=(50, 120, 200))
    draw.rectangle((200, 80, 240, 260), fill=(200, 80, 50))
    return img


def test_quick_check_plain_text_false() -> None:
    """Text-only image should not trigger graph heuristic."""
    assert graph_detector.quick_check_for_graph(_make_text_question()) is False


def test_quick_check_graph_true() -> None:
    """Synthetic chart should trigger graph heuristic."""
    assert graph_detector.quick_check_for_graph(_make_fake_graph()) is True


def test_should_use_graph_model_vision_override() -> None:
    """Vision contains_graph=true overrides local false."""
    img = _make_text_question()
    assert graph_detector.should_use_graph_model(
        img,
        {"contains_graph": True, "answer_type": "number"},
    )


def test_should_use_graph_model_heuristic() -> None:
    """Local heuristic can enable graph without vision flag."""
    img = _make_fake_graph()
    assert graph_detector.should_use_graph_model(
        img,
        {"contains_graph": False, "answer_type": "number"},
    )
