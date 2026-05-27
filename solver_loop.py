"""Autonomous question-solving loop over a user-selected screen region."""

from __future__ import annotations

import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from PIL import Image

import automator
import config
import graph_detector
import graph_solver
import math_solver
import memory
import question_monitor
import region_selector
import vision_reader

LogFn = Callable[[str], None]


@dataclass
class LoopStats:
    """Counters for session summary on stop."""

    solved: int = 0
    correct: int = 0
    skipped: int = 0
    rejected: int = 0
    errors: int = 0
    solve_times_ms: list[float] = field(default_factory=list)


def run_solver_loop(
    region: dict[str, int],
    memory_store: memory.MemoryStore,
    session_id: str,
    *,
    stop_event: threading.Event,
    log: LogFn | None = None,
) -> LoopStats:
    """
    Continuously capture, solve, enter answers, and advance until stop_event.

    Args:
        region: Locked screen region from region_selector.
        memory_store: Active SQLite memory store.
        session_id: Current session UUID.
        stop_event: Set to stop the loop (Q key or Ctrl+C handler).
        log: Optional log function (defaults to print).

    Returns:
        LoopStats summary for terminal output.
    """
    out = log or _default_log
    stats = LoopStats()
    question_monitor.reset_monitor()
    max_retries = int(config.get_config().get("max_retries_per_question", 3))

    while not stop_event.is_set():
        try:
            _run_one_iteration(
                region,
                memory_store,
                session_id,
                stats,
                stop_event,
                out,
                max_retries,
            )
        except _UserQuitLoop:
            break
        except KeyboardInterrupt:
            break
        except Exception as exc:  # noqa: BLE001
            stats.errors += 1
            out(f"\n❌ Loop error: {exc}")
            out("   Continuing in 2s — press Q to stop.")
            if stop_event.wait(2.0):
                break

    return stats


def print_session_summary(stats: LoopStats, log: LogFn | None = None) -> None:
    """
    Print totals and average solve time after the loop stops.

    Args:
        stats: Accumulated loop counters.
        log: Optional log function.
    """
    out = log or _default_log
    avg = (
        sum(stats.solve_times_ms) / len(stats.solve_times_ms)
        if stats.solve_times_ms
        else 0.0
    )
    out("\n━━━━━━━━━━ Session summary ━━━━━━━━━━")
    out(f"  Questions solved: {stats.solved}")
    out(f"  Accepted (tick):  {stats.correct}")
    out(f"  Rejected (wrong): {stats.rejected}")
    out(f"  Skipped:          {stats.skipped}")
    out(f"  Errors:           {stats.errors}")
    out(f"  Avg solve time:   {avg:.0f} ms")
    out("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")


def _run_one_iteration(
    region: dict[str, int],
    memory_store: memory.MemoryStore,
    session_id: str,
    stats: LoopStats,
    stop_event: threading.Event,
    out: LogFn,
    max_retries: int,
) -> None:
    """Single loop iteration: capture through advance."""
    if stop_event.is_set():
        return

    question_monitor.wait_for_page_ready(region)
    filepath, b64 = region_selector.capture_region(region)
    rel_path = f"screenshots/{Path(filepath).name}"
    frame = Image.open(filepath).convert("RGB")

    graph_hint = graph_detector.quick_check_for_graph(frame)
    question_json = _read_vision_with_retries(b64, max_retries, out, rel_path)
    if question_json is None:
        stats.skipped += 1
        return

    use_graph = graph_detector.should_use_graph_model(frame, question_json)
    if use_graph:
        out("📊 Graph detected — switching to graph model")

    phash = memory_store.compute_phash(frame)
    result: math_solver.SolveResult | None = None
    from_cache = False

    cached = memory_store.get_cached_answer(phash)
    if cached and cached.get("verified"):
        out("📋 Using remembered answer")
        result = memory.recall_to_solve_result(
            {
                "answer_value": cached["answer_value"],
                "answer_working": cached.get("answer_working", ""),
                "verification_working": cached.get("verification_working", ""),
                "confidence": cached.get("confidence", 1.0),
                "recheck_passed": True,
                "original_answer": None,
                "answer_unit": cached.get("answer_unit"),
            }
        )
        from_cache = True
    elif use_graph:
        result = graph_solver.solve_graph_with_recheck(b64)
    else:
        t0 = time.monotonic()
        result = math_solver.solve_with_recheck(
            question_json,
            force_recheck=True,
            interactive_gate=False,
        )
        stats.solve_times_ms.append((time.monotonic() - t0) * 1000)

    if result is None:
        return

    if not from_cache and result.confidence < config.CONFIDENCE_THRESHOLD:
        result = _prompt_low_confidence(result, out)
        if not result.ready_for_submit:
            stats.skipped += 1
            out("⏭️  Skipped — not submitting.")
            question_monitor.update_last_seen(frame)
            return

    _print_result_block(rel_path, question_json, result, from_cache, out)
    stats.solved += 1

    if not result.answer.strip():
        stats.skipped += 1
        question_monitor.update_last_seen(frame)
        return

    if not from_cache:
        try:
            qtype = "graph" if use_graph else "standard"
            memory_store.store_question_answer(
                session_id,
                frame,
                question_json,
                result,
                Path(filepath),
                question_type=qtype,
            )
        except Exception as exc:  # noqa: BLE001
            out(f"⚠️  Could not store answer: {exc}")

    if config.DRY_RUN:
        out("[DRY RUN] Skipping UI automation.")
        question_monitor.update_last_seen(frame)
        return

    if not automator.check_accessibility():
        stats.skipped += 1
        return

    automator.click_answer_button(region, dry_run=False)
    question_monitor.wait_for_page_ready(region)

    ui_type = automator.detect_ui_type(region)
    if ui_type == "unknown":
        ui_type = question_json.get("answer_type", "number")
        if ui_type in ("expression", "text"):
            ui_type = "text_input"
        elif ui_type == "multiple_choice":
            ui_type = "multiple_choice"
        else:
            ui_type = "number_pad"

    if not automator.enter_answer(result.answer, ui_type, region):
        out("❌ Answer entry failed.")
        stats.errors += 1
        return

    question_monitor.wait_for_page_ready(region)
    # 200ms grace before tick check — allows submission UI to update
    threading.Event().wait(0.2)

    feedback = automator.check_answer_feedback(region)
    if feedback == "correct":
        out("✅ Answer accepted")
        stats.correct += 1
        automator.advance_to_next_question(region)
    elif feedback == "wrong":
        out("❌ Answer rejected — logging and skipping")
        stats.rejected += 1
        memory_store.store_rejected_answer(
            session_id,
            frame,
            question_json,
            result,
            Path(filepath),
        )
        automator.advance_to_next_question(region)
    else:
        out("⚠️ Could not confirm result — advancing anyway")
        automator.advance_to_next_question(region)

    if not question_monitor.wait_for_question_change(region, timeout_seconds=30):
        out("⚠️ Timed out waiting for next question — retrying capture.")
    question_monitor.update_last_seen(region_selector.region_to_image(region))


def _read_vision_with_retries(
    b64: str,
    max_retries: int,
    out: LogFn,
    rel_path: str,
) -> dict[str, Any] | None:
    """
    Call vision_reader with retries and optional user prompt.

    Returns:
        Parsed question JSON or None to skip.
    """
    for attempt in range(max_retries):
        out(f"👁️  Reading question (attempt {attempt + 1}/{max_retries})…")
        question = vision_reader.read_question(b64)
        if not question.get("error"):
            return question
        out(f"❌ Vision error: {question.get('raw_response', '')[:200]}")
        if attempt < max_retries - 1:
            threading.Event().wait(2.0)
    return _prompt_vision_failure(rel_path, b64, out)


def _prompt_vision_failure(rel_path: str, b64: str, out: LogFn) -> dict[str, Any] | None:
    """Let user retry, skip, or quit after vision failures."""
    out(f"\nVision failed for {rel_path}")
    choice = input("[R]etry / [S]kip / [Q]uit? ").strip().lower()
    if choice == "q":
        raise _UserQuitLoop()
    if choice == "r":
        return _read_vision_with_retries(
            b64,
            int(config.get_config().get("max_retries_per_question", 3)),
            out,
            rel_path,
        )
    return None


def _prompt_low_confidence(
    result: math_solver.SolveResult,
    out: LogFn,
) -> math_solver.SolveResult:
    """
    Pause loop for user decision when confidence is below threshold.

    Args:
        result: Solve result after both passes.
        out: Log function.

    Returns:
        Updated SolveResult (may be edited).
    """
    out("\n── Low confidence — review before submitting ──")
    out(f"Pass 1 working:\n     {result.working}")
    if result.verification_working:
        out(f"Pass 2 verification:\n     {result.verification_working}")
    out(f"Answer: {result.answer}  (confidence {result.confidence:.2f})")
    choice = input("[S]ubmit best guess / [E]dit answer / [K]ip this question? ").strip().lower()
    if choice == "s":
        result.ready_for_submit = True
    elif choice == "e":
        edited = input("Enter corrected answer: ").strip()
        if edited:
            result.answer = edited
            result.ready_for_submit = True
    else:
        result.ready_for_submit = False
    return result


def _print_result_block(
    rel_path: str,
    question: dict[str, Any],
    result: math_solver.SolveResult,
    from_cache: bool,
    out: LogFn,
) -> None:
    """Print formatted solve block to terminal."""
    out("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    if from_cache:
        out("🔁 Recalled from memory")
    out(f"📸 Screenshot: {rel_path}")
    out(f"📖 {question.get('question_text', '(unknown)')[:200]}")
    out(f"📤 Answer: {result.answer}")
    if result.working:
        out(f"✏️  Working: {result.working[:300]}")
    ready = "✅ Ready" if result.ready_for_submit else "⏸️  Not ready"
    out(ready)
    out("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")


def _default_log(message: str) -> None:
    """Print with flush."""
    print(message, flush=True)


class _UserQuitLoop(Exception):
    """Raised when user chooses Quit from an interactive prompt."""
