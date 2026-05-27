"""Unit tests for model_manager vision detection."""

from __future__ import annotations

import model_manager


def test_is_vision_capable_moondream() -> None:
    """Moondream tag is vision-capable."""
    assert model_manager.is_vision_capable("moondream:v2")


def test_is_vision_capable_math_not_vision() -> None:
    """Math-only models are not vision-capable."""
    assert not model_manager.is_vision_capable("qwen2.5-math:7b")


def test_group_models_splits_lists() -> None:
    """group_models returns disjoint vision and text lists."""
    models = ["moondream:v2", "qwen2.5:7b", "qwen2.5vl:7b"]
    vision, text = model_manager.group_models(models)
    assert "moondream:v2" in vision
    assert "qwen2.5vl:7b" in vision
    assert "qwen2.5:7b" in text
    assert "qwen2.5:7b" not in vision
