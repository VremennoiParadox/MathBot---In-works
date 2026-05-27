"""Unit tests for math_solver validation and error paths."""

from __future__ import annotations

import math_solver


def test_validate_angle_in_range() -> None:
    """Valid angle passes without warnings (returns True)."""
    assert math_solver.validate_answer("90", "number", None) is True


def test_validate_angle_out_of_range_prints(capsys) -> None:
    """Angle > 360 triggers a warning."""
    math_solver.validate_answer("400°", "number", None)
    captured = capsys.readouterr()
    assert "360" in captured.out


def test_error_result_not_ready() -> None:
    """Failed solves are not marked ready for submit."""
    result = math_solver._error_result("failed")
    assert not result.ready_for_submit
    assert result.answer == ""
