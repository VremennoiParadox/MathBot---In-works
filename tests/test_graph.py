"""Tests for graph_solver prompt loading and pass merge logic."""

from __future__ import annotations

import graph_solver
import math_solver


def test_load_graph_prompts_non_empty() -> None:
    """Graph prompt files load with expected keywords."""
    p1 = graph_solver.load_graph_prompt()
    p2 = graph_solver.load_graph_recheck_prompt()
    assert "graph" in p1.lower()
    assert "[answer]" in p2


def test_merge_graph_passes_verified() -> None:
    """Verified Pass 2 keeps Pass 1 answer."""
    pass1 = {
        "answer": "12",
        "working": "read bar height",
        "confidence": 0.9,
    }
    pass2 = {
        "verified": True,
        "corrected_answer": "99",
        "verification_working": "recounted bars",
        "confidence": 0.95,
    }
    result = graph_solver._merge_graph_passes(pass1, pass2)
    assert result.answer == "12"
    assert result.recheck_passed


def test_merge_graph_passes_corrected() -> None:
    """Failed verification uses corrected_answer."""
    pass1 = {"answer": "99", "working": "w", "confidence": 0.9}
    pass2 = {
        "verified": False,
        "corrected_answer": "12",
        "verification_working": "fix",
        "confidence": 0.9,
    }
    result = graph_solver._merge_graph_passes(pass1, pass2)
    assert result.answer == "12"
    assert result.was_corrected


def test_graph_result_from_pass1_shape() -> None:
    """Pass-1-only graph result is a valid SolveResult."""
    pass1 = {"answer": "5", "working": "steps", "confidence": 0.8}
    result = graph_solver._graph_result_from_pass1(pass1, recheck_skipped=True)
    assert isinstance(result, math_solver.SolveResult)
    assert result.answer == "5"
