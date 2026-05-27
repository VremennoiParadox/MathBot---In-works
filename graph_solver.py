"""Graph questions: vision two-pass recheck and graph hotkey flow."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

import config
import math_solver
import vision_reader

_RECHECK_PHRASE = "do not simply confirm the previous answer"
LogFn = Callable[[str], None]


def load_graph_prompt() -> str:
    """Load prompts/graph_prompt.txt."""
    path = config.PROMPTS_DIR / "graph_prompt.txt"
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"Could not read graph prompt at {path}: {exc}")
        return ""


def load_graph_recheck_prompt() -> str:
    """Load prompts/graph_recheck_prompt.txt."""
    path = config.PROMPTS_DIR / "graph_recheck_prompt.txt"
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"Could not read graph recheck prompt at {path}: {exc}")
        return ""


def solve_graph_with_recheck(base64_image: str) -> math_solver.SolveResult:
    """
    Vision two-pass graph solve: Pass 1 read, Pass 2 re-read and verify.

    Args:
        base64_image: Screenshot PNG as base64.

    Returns:
        Verified SolveResult after confidence gate.
    """
    model = config.get_config()["graph_model"]
    pass1 = _run_graph_pass(base64_image, load_graph_prompt(), model, "Pass 1")
    if pass1.get("error"):
        return math_solver.error_result(str(pass1.get("raw_response", "Graph Pass 1 failed.")))

    if not config.THINK_MODE:
        print("think_mode is false — skipping graph Pass 2 recheck.", flush=True)
        return _graph_result_from_pass1(pass1, recheck_skipped=True)

    answer = str(pass1.get("answer", ""))
    template = load_graph_recheck_prompt()
    recheck_prompt = template.replace("[answer]", answer)
    recheck_prompt += (
        f"\n\nCRITICAL: {_RECHECK_PHRASE} — use a different method to verify.\n"
    )

    pass2 = _run_graph_pass(base64_image, recheck_prompt, model, "Pass 2")
    if pass2.get("error"):
        print("Graph Pass 2 failed; using Pass 1 answer.", flush=True)
        return _graph_result_from_pass1(pass1, recheck_skipped=False)
    return _merge_graph_passes(pass1, pass2)


def run_graph_hotkey(
    session_id: str,
    memory_store: Any | None = None,
    *,
    log: LogFn | None = None,
    dry_run: bool | None = None,
) -> bool:
    """
    Graph hotkey flow: capture → two-pass graph solve → memory → automation.

    Args:
        session_id: Active session UUID.
        memory_store: Optional MemoryStore instance.
        log: Logging callable (defaults to print).
        dry_run: Override config dry_run for automation.

    Returns:
        True if flow completed successfully.
    """
    import automator
    import capture
    import memory as memory_mod

    out = log or (lambda msg: print(msg, flush=True))
    t0 = time.monotonic()

    out("\n▶ Graph hotkey — starting graph solve…")
    out("📸 Capturing screen…")
    filepath, b64 = capture.capture_screen()
    out(f"   Saved: screenshots/{Path(filepath).name}")

    try:
        from PIL import Image

        full_image = Image.open(filepath)
    except OSError:
        full_image = None

    question_image = capture.crop_question_region(full_image) if full_image else None

    if memory_store and question_image:
        recall = memory_store.recall_for_verification(question_image)
        if recall:
            out(f"🔁 Recalled graph answer {recall['answer_value']!r}")
            result = memory_mod.recall_to_solve_result(recall)
            question = _vision_from_recall(recall)
            return _finish_graph_flow(
                out,
                result,
                question,
                filepath,
                full_image,
                session_id,
                memory_store,
                question_image,
                from_cache=True,
                dry_run=dry_run,
                elapsed_ms=(time.monotonic() - t0) * 1000,
            )

    cfg = config.get_config()
    out(f"📊 Graph Pass 1+2 with {cfg['graph_model']}…")
    result = solve_graph_with_recheck(b64)
    question = _vision_from_graph_pass(result, b64)
    return _finish_graph_flow(
        out,
        result,
        question,
        filepath,
        full_image,
        session_id,
        memory_store,
        question_image,
        from_cache=False,
        dry_run=dry_run,
        elapsed_ms=(time.monotonic() - t0) * 1000,
    )


def _finish_graph_flow(
    out: LogFn,
    result: math_solver.SolveResult,
    question: dict[str, Any],
    filepath: str,
    full_image: Any,
    session_id: str,
    memory_store: Any | None,
    question_image: Any,
    *,
    from_cache: bool,
    dry_run: bool | None,
    elapsed_ms: float,
) -> bool:
    """Print, store, and automate a graph solve result."""
    import automator

    _print_graph_result(out, filepath, question, result, from_cache)

    qid = None
    if memory_store and question_image and result.ready_for_submit and not from_cache:
        try:
            qid = memory_store.store_question_answer(
                session_id,
                question_image,
                question,
                result,
                Path(filepath),
                question_type="graph",
            )
            out(f"💾 Stored (question_id={qid})")
        except Exception as exc:  # noqa: BLE001
            out(f"⚠️  Store failed: {exc}")

    if not result.ready_for_submit or not result.answer.strip():
        out("⏸️  Automation skipped.")
        return False

    ok = automator.run_automation(
        result.answer,
        question.get("answer_type", "number"),
        before_question=full_image,
        dry_run=dry_run,
    )
    if qid and memory_store:
        try:
            memory_store.update_answer_accepted(qid, ok)
        except Exception as exc:  # noqa: BLE001
            out(f"⚠️  accepted flag: {exc}")

    out(f"⏱️  Graph solve took {elapsed_ms:.0f} ms")
    out("✅ Graph flow done." if ok else "❌ Automation did not confirm success.")
    return ok


def _vision_from_graph_pass(result: math_solver.SolveResult, _b64: str) -> dict[str, Any]:
    """Build minimal vision JSON for memory storage after graph solve."""
    return {
        "question_text": result.working[:200] if result.working else "Graph question",
        "answer_type": "graph",
    }


def _vision_from_recall(recall: dict[str, Any]) -> dict[str, Any]:
    """Build vision dict from memory recall row."""
    return {
        "question_text": recall.get("question_text") or "Graph (recalled)",
        "answer_type": recall.get("answer_type") or "graph",
    }


def _print_graph_result(
    out: LogFn,
    filepath: str,
    question: dict[str, Any],
    result: math_solver.SolveResult,
    from_cache: bool,
) -> None:
    """Print graph solve summary."""
    out("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    if from_cache:
        out("🔁 Recalled from memory")
    out(f"📸 Screenshot: screenshots/{Path(filepath).name}")
    out(f"📖 {question.get('question_text', 'Graph')}")
    out(f"📤 Answer: {result.answer}")
    out("✅ Ready for submit" if result.ready_for_submit else "⏸️  Not ready")
    out("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")


def _run_graph_pass(
    base64_image: str,
    prompt: str,
    model: str,
    label: str,
) -> dict[str, Any]:
    """Single vision API pass for graph solving."""
    raw = ""
    for attempt in range(2):
        raw = vision_reader.call_ollama_vision(base64_image, prompt, model) or ""
        if not raw:
            return {"error": True, "raw_response": f"{label} vision request failed."}
        parsed = vision_reader.parse_json_response(raw)
        if parsed and ("answer" in parsed or "verified" in parsed):
            return parsed
        if attempt == 0:
            print(f"Graph {label} JSON parse failed; retrying once...", flush=True)
    return {"error": True, "raw_response": raw}


def _merge_graph_passes(pass1: dict[str, Any], pass2: dict[str, Any]) -> math_solver.SolveResult:
    """Merge graph passes into SolveResult with confidence gate."""
    original = str(pass1.get("answer", ""))
    working = str(pass1.get("working", ""))
    conf1 = float(pass1.get("confidence", 0.5))
    verified = bool(pass2.get("verified", True))
    corrected = str(pass2.get("corrected_answer", original))
    verification = str(pass2.get("verification_working", ""))
    conf2 = float(pass2.get("confidence", conf1))

    was_corrected = False
    final_answer = original
    if not verified:
        was_corrected = True
        final_answer = corrected
        print(f"\n⚠️  Graph answer corrected: {original} → {corrected}\n", flush=True)

    result = math_solver.SolveResult(
        answer=final_answer,
        working=working,
        verification_working=verification,
        confidence=min(conf1, conf2),
        recheck_passed=verified and not was_corrected,
        original_answer=original if was_corrected else None,
        was_corrected=was_corrected,
        answer_unit=None,
        ready_for_submit=min(conf1, conf2) >= config.CONFIDENCE_THRESHOLD,
    )
    return math_solver.apply_confidence_gate(result, recheck_skipped=False)


def _graph_result_from_pass1(
    pass1: dict[str, Any],
    *,
    recheck_skipped: bool,
) -> math_solver.SolveResult:
    """Build SolveResult from graph Pass 1 only."""
    conf = float(pass1.get("confidence", 0.5))
    result = math_solver.SolveResult(
        answer=str(pass1.get("answer", "")),
        working=str(pass1.get("working", "")),
        verification_working="",
        confidence=conf,
        recheck_passed=True,
        original_answer=None,
        was_corrected=False,
        answer_unit=None,
        ready_for_submit=conf >= config.CONFIDENCE_THRESHOLD,
    )
    return math_solver.apply_confidence_gate(result, recheck_skipped)


def main() -> None:
    """CLI entry: run graph hotkey once (requires config + Ollama)."""
    config.load_config()
    store = memory.MemoryStore()
    session = store.start_session()
    try:
        run_graph_hotkey(session, store)
    finally:
        store.end_session(session)
        store.export_session_csv(session)
        store.close()
