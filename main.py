"""MathBot entry point: hotkeys, orchestration, and terminal output."""

from __future__ import annotations

import sys
import threading
from pathlib import Path

import requests
from pynput import keyboard

import capture
import config
import graph_solver
import math_solver
import model_manager
import vision_reader

_quit_event = threading.Event()
_solve_lock = threading.Lock()


def main() -> None:
    """Load config, run wizard if needed, register hotkeys, and block until quit."""
    config.load_config()

    if config.first_run or not config.CONFIG_PATH.exists():
        model_manager.run_setup_wizard()
        config.load_config()

    if not _check_ollama():
        sys.exit(1)

    _print_startup_banner()

    hotkey = _parse_hotkey(config.DEFAULT_HOTKEY)
    holder: dict[str, keyboard.GlobalHotKeys] = {}
    listener = keyboard.GlobalHotKeys(
        {
            hotkey: _on_solve_hotkey,
            "<cmd>+m": _on_model_switch_key,
            "m": _on_model_switch_key,
            "<cmd>+q": lambda: _request_quit(holder["listener"]),
            "q": lambda: _request_quit(holder["listener"]),
        }
    )
    holder["listener"] = listener
    listener.start()
    try:
        while not _quit_event.is_set():
            _quit_event.wait(timeout=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        listener.stop()
        print("\nMathBot stopped.")


def _print_startup_banner() -> None:
    """Print model summary, think_mode status, and hotkey help."""
    cfg = config.get_config()
    think_note = (
        "Recheck ON (think_mode: true)"
        if cfg.get("think_mode", True)
        else "Recheck OFF (think_mode: false — faster, less accurate)"
    )
    print(
        f"Using: [{cfg['vision_model']} → vision] "
        f"[{cfg['solver_model']} → solver] "
        f"[{cfg['graph_model']} → graph] — press M to change"
    )
    print(f"{think_note} | confidence gate: {cfg.get('confidence_threshold', 0.75)}")
    print("Press solve hotkey to capture and solve. Press Q to quit.\n")


def _request_quit(listener: keyboard.GlobalHotKeys) -> None:
    """Stop the hotkey listener and signal the main loop to exit."""
    print("\nQuitting…")
    _quit_event.set()
    listener.stop()


def _check_ollama() -> bool:
    """Verify Ollama HTTP API is reachable."""
    try:
        response = requests.get(config.OLLAMA_HOST, timeout=3)
        if response.status_code < 500:
            return True
    except requests.RequestException:
        pass
    print("\nOllama is not reachable at http://localhost:11434")
    print("Start it with:  ollama serve\n")
    return False


def _on_solve_hotkey() -> None:
    """Hotkey callback: capture → vision → solve → print formatted result."""
    if not _solve_lock.acquire(blocking=False):
        print("\nSolve already in progress…")
        return
    try:
        _solve_current_question()
    finally:
        _solve_lock.release()


def _on_model_switch_key() -> None:
    """M key: mid-session model switcher."""
    try:
        model_manager.run_model_switcher()
        _print_startup_banner()
    except EOFError:
        print("Model switch cancelled.")


def _solve_current_question() -> None:
    """Run capture → vision → solve (or graph two-pass) → terminal output."""
    if not _check_ollama():
        return

    filepath, b64 = capture.capture_screen()
    rel_path = _relative_screenshot_path(filepath)

    question = vision_reader.read_question(b64)
    if question.get("error"):
        _print_vision_error(rel_path, question)
        return

    if question.get("answer_type") == "graph":
        result = graph_solver.solve_graph_with_recheck(b64)
    else:
        result = math_solver.solve_question(question)

    _print_solve_result(rel_path, question, result)


def _print_vision_error(rel_path: str, question: dict) -> None:
    """Print formatted vision failure output."""
    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"📸 Screenshot saved: {rel_path}")
    print("❌ Vision failed to read the question.")
    print(f"   Raw: {question.get('raw_response', '')[:500]}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")


def _print_solve_result(
    rel_path: str,
    question: dict,
    result: math_solver.SolveResult,
) -> None:
    """Print Pass 1 + Pass 2 working and submission readiness."""
    q_text = question.get("question_text", "(unknown)")
    a_type = question.get("answer_type", "number")
    working_lines = result.working.replace("\n", "\n     ")
    verify_lines = result.verification_working.replace("\n", "\n     ")

    if result.recheck_passed and not result.was_corrected:
        recheck_line = "✅ Recheck passed"
    elif result.was_corrected:
        recheck_line = "⚠️  Recheck corrected answer"
    else:
        recheck_line = "⚠️  Recheck flagged issue"

    ready = "✅ Ready for submit" if result.ready_for_submit else "⏸️  Not ready (review or skip)"

    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"📸 Screenshot saved: {rel_path}")
    print(f"📖 Question: {q_text}")
    print(f"🔢 Answer type: {a_type}")
    print("✏️  Pass 1 working:")
    print(f"     {working_lines}")
    if result.verification_working:
        print("🔍 Pass 2 verification:")
        print(f"     {verify_lines}")
    print(recheck_line)
    print(f"📤 Answer: {result.answer}")
    print(ready)
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")


def _relative_screenshot_path(filepath: str) -> str:
    """Return screenshots/NAME for display."""
    return f"screenshots/{Path(filepath).name}"


def _parse_hotkey(hotkey: str) -> str:
    """Convert config hotkey string to pynput GlobalHotKeys format."""
    parts = [p.strip().lower() for p in hotkey.split("+")]
    mapped: list[str] = []
    for part in parts:
        if part in ("cmd", "command", "meta"):
            mapped.append("<cmd>")
        elif part in ("ctrl", "control"):
            mapped.append("<ctrl>")
        elif part in ("alt", "option"):
            mapped.append("<alt>")
        elif part == "shift":
            mapped.append("<shift>")
        else:
            mapped.append(part)
    return "+".join(mapped)


if __name__ == "__main__":
    main()
