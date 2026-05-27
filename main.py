"""MathBot entry point: region selection and autonomous solver loop."""

from __future__ import annotations

import sys
import threading

import requests
from pynput import keyboard

import automator
import capture
import config
import memory
import model_manager
import region_selector
import solver_loop

_stop_event = threading.Event()
_memory: memory.MemoryStore | None = None
_session_id: str = ""
_solve_times_ms: list[float] = []


def main() -> None:
    """Load config, select region, and run the autonomous solver loop."""
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

    region = region_selector.select_region()
    config.load_config()

    _log("🚀 Solver running — press Ctrl+C or Q to stop")

    listener = _start_stop_listener()
    try:
        stats = solver_loop.run_solver_loop(
            region,
            _memory,
            _session_id,
            stop_event=_stop_event,
            log=_log,
        )
        _solve_times_ms.extend(stats.solve_times_ms)
        solver_loop.print_session_summary(stats, log=_log)
    except KeyboardInterrupt:
        _log("\nInterrupted.")
    finally:
        listener.stop()
        _shutdown_memory()


def _start_stop_listener() -> keyboard.Listener:
    """Listen for Q to stop the solver loop."""

    def on_press(key: keyboard.Key | keyboard.KeyCode | None) -> None:
        try:
            if hasattr(key, "char") and key.char and key.char.lower() == "q":
                _log("\nStop requested (Q)…")
                _stop_event.set()
        except AttributeError:
            pass

    listener = keyboard.Listener(on_press=on_press)
    listener.start()
    return listener


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
        _log("⚠️  Accessibility not granted — automation clicks will fail.")

    missing = automator.list_missing_templates(
        ["answer_button.png", "correct_tick.png", "next_button.png"]
    )
    if missing:
        _log(f"⚠️  Missing UI templates: {', '.join(missing)}")
        _log(f"   Run: python capture_templates.py")
        _log(f"   Or add PNGs to: {config.TEMPLATES_DIR}")


def _print_startup_banner() -> None:
    """Print model summary."""
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
        f"[{cfg['graph_model']} → graph]"
    )
    _log(f"{think_note} | confidence gate: {cfg.get('confidence_threshold', 0.75)}")
    _log(f"Dry run: {dry} (set dry_run in config.json to toggle)")
    _log(f"Session: {_session_id[:8]}…\n")


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


def run_self_test() -> int:
    """
    Bundled smoke test: Ollama, imports, optional fixture vision.

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

    try:
        import graph_detector
        import question_monitor
        import region_selector

        _log("✓ Autonomous loop modules import OK")
    except ImportError as exc:
        _log(f"✗ Import failed: {exc}")
        return 1

    fixture = config.BUNDLE_DIR / "tests" / "fixtures" / "sample_question.png"
    if fixture.exists():
        import base64

        import vision_reader

        data = base64.b64encode(fixture.read_bytes()).decode("utf-8")
        from PIL import Image

        img = Image.open(fixture)
        graph = graph_detector.quick_check_for_graph(img)
        _log(f"✓ quick_check_for_graph (text fixture): {graph}")
        vision = vision_reader.read_question(data)
        if vision.get("error"):
            _log(f"✗ Vision fixture failed: {vision.get('raw_response', '')[:200]}")
            return 1
        _log(f"✓ Vision OK: {vision.get('question_text', '')[:80]}…")
    else:
        _log("○ No sample_question.png fixture — skipped vision test")

    _log("=== Self-test passed ===")
    return 0


def run_loop_once() -> None:
    """Run a single loop iteration (dry-run friendly) for testing."""
    global _memory, _session_id
    config.load_config()
    if not _check_ollama():
        sys.exit(1)
    region = region_selector.load_saved_region() or region_selector.select_region()
    _memory = memory.MemoryStore()
    _session_id = _memory.start_session()
    stats = solver_loop.LoopStats()
    try:
        solver_loop._run_one_iteration(
            region,
            _memory,
            _session_id,
            stats,
            threading.Event(),
            _log,
            int(config.get_config().get("max_retries_per_question", 3)),
        )
    finally:
        _shutdown_memory()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--self-test":
        config.load_config()
        sys.exit(run_self_test())
    if len(sys.argv) > 1 and sys.argv[1] == "--loop-once":
        config.load_config()
        if not config.CONFIG_PATH.exists():
            model_manager.run_setup_wizard()
            config.load_config()
        run_loop_once()
    else:
        main()
