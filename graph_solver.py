"""Graph questions: vision two-pass recheck (Phase 2 terminal path)."""

from __future__ import annotations

from typing import Any

import config
import math_solver
import model_manager
import vision_reader

_RECHECK_PHRASE = "do not simply confirm the previous answer"


def load_graph_prompt() -> str:
    """
    Load prompts/graph_prompt.txt.

    Returns:
        Graph Pass 1 prompt text.
    """
    path = config.PROMPTS_DIR / "graph_prompt.txt"
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"Could not read graph prompt at {path}: {exc}")
        return ""


def load_graph_recheck_prompt() -> str:
    """
    Load prompts/graph_recheck_prompt.txt.

    Returns:
        Graph Pass 2 prompt template with [answer] placeholder.
    """
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
        Verified SolveResult (shared confidence gate with math_solver).
    """
    model = config.get_config()["graph_model"]
    pass1 = _run_graph_pass(base64_image, load_graph_prompt(), model, "Pass 1")
    if pass1.get("error"):
        return math_solver._error_result(str(pass1.get("raw_response", "Graph Pass 1 failed.")))

    if not config.THINK_MODE:
        print("think_mode is false — skipping graph Pass 2 recheck.")
        return _graph_result_from_pass1(pass1, recheck_skipped=True)

    answer = str(pass1.get("answer", ""))
    template = load_graph_recheck_prompt()
    recheck_prompt = template.replace("[answer]", answer)
    recheck_prompt += (
        f"\n\nCRITICAL: {_RECHECK_PHRASE} — use a different method to verify.\n"
    )

    pass2 = _run_graph_pass(base64_image, recheck_prompt, model, "Pass 2")
    if pass2.get("error"):
        print("Graph Pass 2 failed; using Pass 1 answer.")
        return _graph_result_from_pass1(pass1, recheck_skipped=False)
    return _merge_graph_passes(pass1, pass2)


def _run_graph_pass(
    base64_image: str,
    prompt: str,
    model: str,
    label: str,
) -> dict[str, Any]:
    """
    Single vision pass for graph solving.

    Args:
        base64_image: Base64 PNG.
        prompt: Prompt text.
        model: Ollama vision model name.
        label: Pass label for logging.

    Returns:
        Parsed JSON dict or error dict.
    """
    for attempt in range(2):
        raw = vision_reader.call_ollama_vision(base64_image, prompt, model)
        if raw is None:
            return {"error": True, "raw_response": f"{label} vision request failed."}
        parsed = vision_reader.parse_json_response(raw)
        if parsed and ("answer" in parsed or "verified" in parsed):
            return parsed
        if attempt == 0:
            print(f"Graph {label} JSON parse failed; retrying once...")
    return {"error": True, "raw_response": raw or ""}


def _merge_graph_passes(pass1: dict[str, Any], pass2: dict[str, Any]) -> math_solver.SolveResult:
    """
    Merge graph Pass 1 and Pass 2 into SolveResult.

    Args:
        pass1: Initial graph read.
        pass2: Recheck vision read.

    Returns:
        SolveResult after confidence gate.
    """
    original = str(pass1.get("answer", ""))
    working = str(pass1.get("working", ""))
    conf1 = float(pass1.get("confidence", 0.5))

    verified = bool(pass2.get("verified", True)) if pass2 else True
    corrected = str(pass2.get("corrected_answer", original))
    verification = str(pass2.get("verification_working", ""))
    conf2 = float(pass2.get("confidence", conf1)) if pass2 else conf1

    was_corrected = False
    final_answer = original
    if pass2 and not verified:
        was_corrected = True
        final_answer = corrected
        print(f"\n⚠️  Graph answer corrected by recheck: {original} → {corrected}\n")

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


def run_graph_hotkey(_session_id: str, dry_run: bool | None = None) -> None:
    """Graph hotkey handler — full wiring in Phase 5."""
    raise NotImplementedError("run_graph_hotkey is completed in Phase 5")


def main() -> None:
    """Standalone graph hotkey entry — Phase 5."""
    raise NotImplementedError("graph_solver.main is completed in Phase 5")
