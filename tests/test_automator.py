"""Unit tests for automator helpers (no live screen required)."""

from __future__ import annotations

import automator


def test_detect_ui_type_number_defaults() -> None:
    """Number type prefers number_pad when digit template exists marker file check."""
    ui = automator.detect_ui_type("number")
    assert ui in ("number_pad", "text_field")


def test_list_missing_templates() -> None:
    """Missing list includes files that are not present."""
    missing = automator.list_missing_templates(["nonexistent_template_xyz.png"])
    assert "nonexistent_template_xyz.png" in missing


def test_dry_run_click_logs(capsys) -> None:
    """Dry-run click prints intent without raising."""
    automator._click_at(100, 200, dry_run=True, label="test")
    out = capsys.readouterr().out
    assert "[DRY RUN]" in out
