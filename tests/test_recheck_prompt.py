"""Unit tests for recheck category detection and prompt building."""

from __future__ import annotations

import recheck_prompt


def test_detect_geometry_triangle() -> None:
    """Angle/triangle questions use geometry recheck rules."""
    q = {
        "question_text": "Find angle y in an isosceles triangle",
        "answer_type": "expression",
        "constraints": ["angles sum to 180°"],
    }
    assert recheck_prompt.detect_recheck_category(q) == "geometry"


def test_detect_proportion() -> None:
    """Proportion questions use proportion recheck rules."""
    q = {
        "question_text": "y is directly proportional to the square root of x",
        "answer_type": "expression",
    }
    assert recheck_prompt.detect_recheck_category(q) == "proportion"


def test_detect_algebra() -> None:
    """Equation questions use algebra recheck rules."""
    q = {
        "question_text": "Solve the equation 2x + 5 = 17",
        "answer_type": "number",
    }
    assert recheck_prompt.detect_recheck_category(q) == "algebra"


def test_detect_multiple_choice() -> None:
    """MCQ answer_type selects multiple_choice rules."""
    q = {"question_text": "Which option is correct?", "answer_type": "multiple_choice"}
    assert recheck_prompt.detect_recheck_category(q) == "multiple_choice"


def test_build_recheck_prompt_contains_phrase_and_rules() -> None:
    """Recheck prompt includes required phrase and geometry rules."""
    q = {
        "question_text": "Angle x in a triangle",
        "answer_type": "number",
        "visual_elements": "triangle diagram",
    }
    pass1 = {"answer": "60", "working": "sum = 180"}
    prompt = recheck_prompt.build_recheck_prompt(q, pass1)
    assert "60" in prompt
    assert recheck_prompt.RECHECK_PHRASE in prompt
    assert "GEOMETRY" in prompt
    assert "do not simply confirm" in prompt.lower()
