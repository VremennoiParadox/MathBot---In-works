"""Unit tests for Pass 2 merge logic and think_mode behaviour."""

from __future__ import annotations

from unittest.mock import patch

import math_solver


def test_merge_verified_uses_pass1_answer() -> None:
    """When verified=true, final answer stays Pass 1 answer."""
    vision = {"question_text": "2x=10", "answer_type": "number"}
    pass1 = {"answer": "5", "working": "x=5", "confidence": 0.9}
    pass2 = {
        "verified": True,
        "corrected_answer": "6",
        "verification_working": "substituted x=5",
        "confidence": 0.95,
    }
    with patch.object(math_solver.config, "CONFIDENCE_THRESHOLD", 0.75):
        result = math_solver._merge_passes(vision, pass1, pass2, recheck_skipped=False)
    assert result.answer == "5"
    assert result.recheck_passed
    assert result.verification_working == "substituted x=5"


def test_merge_not_verified_uses_corrected() -> None:
    """When verified=false, use corrected_answer."""
    vision = {"question_text": "2x=10", "answer_type": "number"}
    pass1 = {"answer": "6", "working": "wrong", "confidence": 0.9}
    pass2 = {
        "verified": False,
        "corrected_answer": "5",
        "verification_working": "fixed",
        "confidence": 0.9,
    }
    with patch.object(math_solver.config, "CONFIDENCE_THRESHOLD", 0.75):
        result = math_solver._merge_passes(vision, pass1, pass2, recheck_skipped=False)
    assert result.answer == "5"
    assert result.was_corrected
    assert result.original_answer == "6"


def test_think_mode_false_skips_pass2(monkeypatch) -> None:
    """think_mode false should not call Pass 2."""
    vision = {"question_text": "1+1", "answer_type": "number"}
    monkeypatch.setattr(math_solver.config, "THINK_MODE", False)
    monkeypatch.setattr(math_solver, "_run_pass1", lambda _: {"answer": "2", "working": "1+1", "confidence": 0.99})
    monkeypatch.setattr(
        math_solver,
        "_run_pass2_recheck",
        lambda *_: (_ for _ in ()).throw(AssertionError("Pass 2 should be skipped")),
    )
    result = math_solver.solve_with_recheck(vision)
    assert result.answer == "2"
    assert result.verification_working == ""
