"""MathBot entry point: hotkeys, orchestration, solve, memory, automation."""

from __future__ import annotations

import queue
import sys
import threading
from pathlib import Path
from typing import Callable

import requests
from PIL import Image
from pynput import keyboard

import automator
import capture
import config
import graph_solver
import math_solver
import memory
import model_manager
import vision_reader

_quit_event = threading.Event()
_work_queue: queue.Queue[Callable[[], None]] = queue.Queue()
_solve_lock = threading.Lock()
_memory: memory.MemoryStore | None = None
_session_id: str = ""
_solve_times_ms: list[float] = []


def main() -> None:
    """Load config, run wizard if needed, register hotkeys, and block until quit."""
    global _memory, _session_id

    config.load_config()

    if config.first_run or not config.CONFIG_PATH.exists():
        model_manager.run_setup_wizard()
        config.load_config()

    ensure_ollama_running()
    if not _check_ollama():
        sys.exit(1)

    _memory = memory.MemoryStore()
    _session_id = _memory.start_session()

    _check_permissions()
    _print_startup_banner()
    _log(f"Session: {_session_id[:8]}… | DB: {config.DB_PATH}")
    _log(f"Solve hotkey: {config.DEFAULT_HOTKEY} (registered)")
    _log(f"Graph hotkey: {config.GRAPH_HOTKEY}")
    _log("Dry-run toggle: Cmd+Shift+D")

    hotkey = _parse_hotkey(config.DEFAULT_HOTKEY)
    graph_hk = _parse_hotkey(config.GRAPH_HOTKEY)
    dry_toggle = _parse_hotkey("cmd+shift+d")
    holder: dict[str, keyboard.GlobalHotKeys] = {}
    listener = keyboard.GlobalHotKeys(
        {
            hotkey: _on_solve_hotkey,
            graph_hk: _on_graph_hotkey,
            dry_toggle: _on_dry_run_toggle,
            "<cmd>+m": _on_model_switch_key,
            "m": _on_model_switch_key,
            "<cmd>+q": lambda: _request_quit(holder),
            "q": lambda: _request_quit(holder),
        }
    )
    holder["listener"] = listener
    listener.start()
    try:
        while not _quit_event.is_set():
            _drain_work_queue()
            _quit_event.wait(timeout=0.1)
    except KeyboardInterrupt:
        pass
    finally:
        listener.stop()
        _shutdown_memory()
        _log("\nMathBot stopped.")


def _shutdown_memory() -> None:
    """End session, write session_stats, export CSV, and close DB."""
    global _memory, _session_id, _solve_times_ms
    if _memory and _session_id:
        try:
            _write_session_stats()
            _memory.end_session(_session_id)
            out = _memory.export_session_csv(_session_id)
            _log(f"Session exported: {out}")
        except Exception as exc:  # noqa: BLE001
            _log(f"Could not export session: {exc}")
        _memory.close()
        _memory = None
        _session_id = ""
    _solve_times_ms = []


def _write_session_stats() -> None:
    """Persist avg solve time and model combo to config.json."""
    if not _solve_times_ms:
        return
    avg_ms = sum(_solve_times_ms) / len(_solve_times_ms)
    cfg = config.get_config()
    stats = dict(cfg.get("session_stats") or {})
    stats["avg_solve_time_ms"] = round(avg_ms, 1)
    stats["last_session_id"] = _session_id
    stats["model_combo"] = (
        f"{cfg['vision_model']} + {cfg['solver_model']} + {cfg['graph_model']}"
    )
    config.save_config({"session_stats": stats})
    _log(f"Session avg solve time: {avg_ms:.0f} ms (saved to config.json)")


def _drain_work_queue() -> None:
    """Run queued jobs on the main thread."""
    while True:
        try:
            job = _work_queue.get_nowait()
        except queue.Empty:
            return
        try:
            job()
        except Exception as exc:  # noqa: BLE001
            _log(f"\n❌ Error: {exc}")
            _log("   If this keeps happening, run: python main.py --solve-once")


def _enqueue(job: Callable[[], None]) -> None:
    """Schedule work on the main thread."""
    _work_queue.put(job)


def _log(message: str) -> None:
    """Print to terminal and flush immediately."""
    print(message, flush=True)


def _check_permissions() -> None:
    """Warn if Screen Recording or Accessibility may block capture/automation."""
    try:
        capture.capture_screen()
    except Exception as exc:  # noqa: BLE001
        _log(f"⚠️  Screen capture check failed: {exc}")
        _log("   Enable Screen Recording for Terminal in System Settings.")

    if not automator.check_accessibility():
        _log("⚠️  Accessibility not granted — hotkeys may work but clicks will fail.")

    missing = automator.list_missing_templates(["answer_button.png"])
    if missing:
        _log(f"⚠️  Missing UI templates: {', '.join(missing)}")
        _log(f"   Add PNGs to: {config.TEMPLATES_DIR}")


def _print_startup_banner() -> None:
    """Print model summary and hotkey help."""
    cfg = config.get_config()
    think_note = (
        "Recheck ON (think_mode: true)"
        if cfg.get("think_mode", True)
        else "Recheck OFF (think_mode: false)"
    )
    dry = "ON" if cfg.get("dry_run", False) else "OFF"
    _log(
        f"Using: [{cfg['vision_model']} → vision] "
        f"[{cfg['solver_model']} → solver] "
        f"[{cfg['graph_model']} → graph] — press M to change"
    )
    _log(f"{think_note} | confidence gate: {cfg.get('confidence_threshold', 0.75)}")
    _log(f"Dry run: {dry} (Cmd+Shift+D to toggle)")
    _log("Press solve hotkey to capture, solve, and enter answer. Press Q to quit.\n")


def _request_quit(holder: dict[str, keyboard.GlobalHotKeys]) -> None:
    """Stop the hotkey listener and signal exit."""

    def _quit() -> None:
        _log("\nQuitting…")
        holder["listener"].stop()
        _quit_event.set()

    _enqueue(_quit)


def ensure_ollama_running() -> None:
    """Start Ollama in the background if the API is not reachable."""
    if _check_ollama():
        return
    _log("Attempting to start Ollama (ollama serve)…")
    try:
        import subprocess

        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for _ in range(30):
            if _check_ollama():
                _log("Ollama is now running.")
                return
            threading.Event().wait(1.0)
    except OSError as exc:
        _log(f"Could not start Ollama: {exc}")
    _log("Ollama did not start in time. Run: ollama serve")


def _check_ollama() -> bool:
    """Verify Ollama HTTP API is reachable."""
    try:
        response = requests.get(config.OLLAMA_HOST, timeout=3)
        if response.status_code < 500:
            return True
    except requests.RequestException:
        pass
    _log("\nOllama is not reachable at http://localhost:11434")
    _log("Start it with:  ollama serve\n")
    return False


def _on_solve_hotkey() -> None:
    """Hotkey callback: queue solve on main thread."""
    _enqueue(_run_solve_safe)


def _on_graph_hotkey() -> None:
    """Graph hotkey callback."""
    _enqueue(_run_graph_safe)


def _on_model_switch_key() -> None:
    """M key: queue model switcher."""
    _enqueue(_run_model_switch_safe)


def _on_dry_run_toggle() -> None:
    """Cmd+Shift+D: toggle dry_run."""
    _enqueue(_toggle_dry_run)


def _toggle_dry_run() -> None:
    """Flip dry_run in config."""
    cfg = config.get_config()
    new_val = not cfg.get("dry_run", False)
    config.save_config({"dry_run": new_val})
    _log(f"\nDry run is now {'ON' if new_val else 'OFF'}")


def _run_solve_safe() -> None:
    """Run solve with lock."""
    if not _solve_lock.acquire(blocking=False):
        _log("\nSolve already in progress…")
        return
    try:
        import time

        t0 = time.monotonic()
        _solve_current_question()
        _solve_times_ms.append((time.monotonic() - t0) * 1000)
    finally:
        _solve_lock.release()


def _run_graph_safe() -> None:
    """Run graph hotkey flow with lock."""
    if not _solve_lock.acquire(blocking=False):
        _log("\nGraph solve already in progress…")
        return
    try:
        if not _check_ollama():
            return
        import time

        t0 = time.monotonic()
        if _memory and _session_id:
            graph_solver.run_graph_hotkey(
                _session_id,
                _memory,
                log=_log,
            )
        _solve_times_ms.append((time.monotonic() - t0) * 1000)
    finally:
        _solve_lock.release()


def _run_model_switch_safe() -> None:
    """Run model switcher."""
    try:
        model_manager.run_model_switcher()
        _print_startup_banner()
    except EOFError:
        _log("Model switch cancelled.")


def _solve_current_question() -> None:
    """Capture → memory recall or vision+solve → store → automate."""
    _log("\n▶ Hotkey received — starting solve…")

    if not _check_ollama():
        return

    _log("📸 Capturing screen…")
    filepath, b64 = capture.capture_screen()
    rel_path = _relative_screenshot_path(filepath)
    _log(f"   Saved: {rel_path}")

    try:
        full_image = Image.open(filepath)
    except OSError:
        full_image = None

    question_image = capture.crop_question_region(full_image) if full_image else None
    phash = _memory.compute_phash(question_image) if _memory and question_image else None

    question: dict
    result: math_solver.SolveResult
    question_type = "standard"
    from_cache = False

    if _memory and question_image:
        recall = _memory.recall_for_verification(question_image)
        if recall:
            _log(
                f"🔁 Verification screen detected — recalling answer "
                f"{recall['answer_value']!r} (phash distance ≤ {config.IMAGE_HASH_MATCH_THRESHOLD})"
            )
            result = memory.recall_to_solve_result(recall)
            question = {
                "question_text": recall.get("question_text") or "(recalled)",
                "answer_type": recall.get("answer_type") or "number",
            }
            from_cache = True

    if not from_cache:
        cfg = config.get_config()
        _log(f"👁️  Reading question with {cfg['vision_model']} (may take 30–90s)…")
        question = vision_reader.read_question(b64)
        if question.get("error"):
            _print_vision_error(rel_path, question)
            return

        _log(f"📖 Question: {question.get('question_text', '(unknown)')[:120]}…")

        if question.get("answer_type") == "graph":
            question_type = "graph"
            _log(f"📊 Graph mode — solving with {cfg['graph_model']}…")
            result = graph_solver.solve_graph_with_recheck(b64)
        else:
            _log(f"🧮 Solving with {cfg['solver_model']} (Pass 1 + recheck)…")
            result = math_solver.solve_question(
                question,
                question_hash=phash,
                memory_store=_memory,
            )

    _print_solve_result(rel_path, question, result, from_cache=from_cache)

    question_id: int | None = None
    if (
        _memory
        and _session_id
        and question_image
        and result.ready_for_submit
        and not from_cache
    ):
        try:
            question_id = _memory.store_question_answer(
                _session_id,
                question_image,
                question,
                result,
                Path(filepath),
                question_type=question_type,
            )
            _log(f"💾 Stored in memory (question_id={question_id})")
        except Exception as exc:  # noqa: BLE001
            _log(f"⚠️  Could not store answer: {exc}")

    if not result.ready_for_submit:
        _log("⏸️  Automation skipped — not ready for submit.")
        return
    if not result.answer.strip():
        _log("⏸️  Automation skipped — empty answer.")
        return

    ok = automator.run_automation(
        result.answer,
        question.get("answer_type", "number"),
        before_question=full_image,
    )
    if question_id and _memory:
        try:
            _memory.update_answer_accepted(question_id, ok)
        except Exception as exc:  # noqa: BLE001
            _log(f"⚠️  Could not update accepted flag: {exc}")

    if ok:
        _log("✅ Automation finished successfully.")
    else:
        _log("❌ Automation did not confirm success.")


def _print_vision_error(rel_path: str, question: dict) -> None:
    """Print vision failure."""
    _log("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    _log(f"📸 Screenshot saved: {rel_path}")
    _log("❌ Vision failed to read the question.")
    _log(f"   Raw: {question.get('raw_response', '')[:500]}")
    _log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")


def _print_solve_result(
    rel_path: str,
    question: dict,
    result: math_solver.SolveResult,
    *,
    from_cache: bool = False,
) -> None:
    """Print solve output."""
    q_text = question.get("question_text", "(unknown)")
    a_type = question.get("answer_type", "number")
    source = "🔁 Recalled from memory" if from_cache else ""

    _log("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    if source:
        _log(source)
    _log(f"📸 Screenshot saved: {rel_path}")
    _log(f"📖 Question: {q_text}")
    _log(f"🔢 Answer type: {a_type}")
    _log("✏️  Pass 1 working:")
    _log(f"     {result.working.replace(chr(10), chr(10) + '     ')}")
    if result.verification_working:
        _log("🔍 Pass 2 verification:")
        _log(f"     {result.verification_working.replace(chr(10), chr(10) + '     ')}")
    _log(f"📤 Answer: {result.answer}")
    ready = "✅ Ready for submit" if result.ready_for_submit else "⏸️  Not ready"
    _log(ready)
    _log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")


def _relative_screenshot_path(filepath: str) -> str:
    """Return screenshots/NAME for display."""
    return f"screenshots/{Path(filepath).name}"


def _parse_hotkey(hotkey: str) -> str:
    """Convert config hotkey to pynput format."""
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


def _ensure_memory_for_cli() -> None:
    """Start a one-off session for CLI --solve-once modes."""
    global _memory, _session_id
    if _memory is None:
        _memory = memory.MemoryStore()
        _session_id = _memory.start_session()


def run_self_test() -> int:
    """
    Bundled smoke test: Ollama, imports, optional fixture vision (dry_run).

    Returns:
        Exit code 0 on success, 1 on failure.
    """
    _log("=== MathBot self-test ===")
    config.load_config()
    if not config.CONFIG_PATH.exists():
        _log("No config.json — run main.py once for the wizard.")
        return 1
    if not _check_ollama():
        return 1

    _log("✓ Ollama reachable")
    _log("✓ Config loaded")

    fixture = config.BUNDLE_DIR / "tests" / "fixtures" / "sample_question.png"
    if fixture.exists():
        _log(f"Running vision on fixture {fixture.name}…")
        import base64

        data = base64.b64encode(fixture.read_bytes()).decode("utf-8")
        vision = vision_reader.read_question(data)
        if vision.get("error"):
            _log(f"✗ Vision fixture failed: {vision.get('raw_response', '')[:200]}")
            return 1
        _log(f"✓ Vision OK: {vision.get('question_text', '')[:80]}…")
    else:
        _log("○ No sample_question.png fixture — skipped vision test")

    if config.DRY_RUN:
        _log("✓ dry_run enabled in config")
    _log("=== Self-test passed ===")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--self-test":
        config.load_config()
        sys.exit(run_self_test())
    if len(sys.argv) > 1 and sys.argv[1] in ("--solve-once", "--dry-run-once"):
        config.load_config()
        if not config.CONFIG_PATH.exists():
            model_manager.run_setup_wizard()
            config.load_config()
        _ensure_memory_for_cli()
        if sys.argv[1] == "--dry-run-once":
            config.save_config({"dry_run": True})
        _run_solve_safe()
        _shutdown_memory()
    else:
        main()
