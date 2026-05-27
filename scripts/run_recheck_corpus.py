#!/usr/bin/env python3
"""Run solve_with_recheck on all fixture questions (manual Phase 2 validation)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
import math_solver  # noqa: E402
import model_manager  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "questions"


def main() -> int:
    """
    Solve each fixture JSON and print a one-line summary.

    Returns:
        Exit code 0 on success, 1 if Ollama unavailable.
    """
    config.load_config()
    if not config.CONFIG_PATH.exists():
        print("Run main.py once to create config.json via the wizard.")
        return 1
    if not model_manager.check_ollama_running():
        print("Start Ollama: ollama serve")
        return 1

    files = sorted(FIXTURES.glob("*.json"))
    if len(files) < 20:
        print(f"Expected 20+ fixture files, found {len(files)}")
        return 1

    print(f"Running recheck corpus ({len(files)} questions)…\n")
    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        name = path.stem
        notes = data.pop("_notes", "")
        result = math_solver.solve_with_recheck(data)
        status = "OK" if result.recheck_passed else "CORRECTED"
        ready = "ready" if result.ready_for_submit else "hold"
        print(f"{name}: {status} | {ready} | answer={result.answer!r}")
        if notes:
            print(f"  notes: {notes}")
    print("\nDone. Review Pass 1 / Pass 2 output above before starting Phase 3.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
