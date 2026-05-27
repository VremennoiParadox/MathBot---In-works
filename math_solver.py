"""Two-pass think-and-recheck math solver with confidence gate."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

import requests

import config
import model_manager
import recheck_prompt

_JSON_BLOCK_RE = re.compile(r"\{[\s\S]*\}")


@dataclass
class SolveResult:
    """Verified solve package returned to the orchestrator."""

    answer: str
    working: str
    verification_working: str
    confidence: float
    recheck_passed: bool
    original_answer: str | None
    was_corrected: bool
    answer_unit: str | None
    ready_for_submit: bool


def solve_question(
    vision: dict[str, Any],
    question_hash: str | None = None,
    memory_store: object | None = None,
) -> SolveResult:
    """
    Solve with optional memory cache (Phase 4); always returns verified package.

    Args:
        vision: Vision extraction JSON.
        question_hash: Optional perceptual hash for cache lookup.
        memory_store: Optional MemoryStore (ignored until Phase 4).

    Returns:
        Verified SolveResult from solve_with_recheck or cache.
    """
    if memory_store is not None and question_hash:
        cached = memory_store.get_cached_answer(question_hash)
        if cached and cached.get("verified"):
            print(
                f"Memory cache hit (exact phash) — skipping Ollama solver. "
                f"Answer: {cached['answer_value']!r}",
                flush=True,
            )
            return SolveResult(
                answer=str(cached["answer_value"]),
                working=str(cached.get("answer_working", "")),
                verification_working=str(cached.get("verification_working", "")),
                confidence=float(cached.get("confidence", 1.0)),
                recheck_passed=True,
                original_answer=None,
                was_corrected=False,
                answer_unit=cached.get("answer_unit"),
                ready_for_submit=True,
            )

    return solve_with_recheck(vision)


def solve_with_recheck(
    question_json: dict[str, Any],
    *,
    force_recheck: bool = False,
    interactive_gate: bool = True,
) -> SolveResult:
    """
    Run Pass 1 → Pass 2 (if think_mode or force_recheck) → confidence gate.

    Args:
        question_json: Vision extraction dict.
        force_recheck: Always run Pass 2 even when think_mode is false.
        interactive_gate: Prompt user on low confidence when True.

    Returns:
        SolveResult with final verified answer only.
    """
    if question_json.get("error"):
        return _error_result("Vision failed to read the question.")

    pass1 = _run_pass1(question_json)
    if pass1.get("error"):
        return _error_result(str(pass1.get("raw_response", "Pass 1 failed.")))

    do_recheck = config.THINK_MODE or force_recheck
    if do_recheck:
        print("🔍 Pass 2 — rechecking answer…", flush=True)
        pass2 = _run_pass2_recheck(question_json, pass1)
    else:
        print("think_mode is false — skipping Pass 2 recheck (less accurate).", flush=True)
        pass2 = {}

    return _merge_passes(
        question_json,
        pass1,
        pass2,
        recheck_skipped=not do_recheck,
        interactive_gate=interactive_gate,
    )


def _run_pass1(question_json: dict[str, Any]) -> dict[str, Any]:
    """
    Pass 1: chain-of-thought solve via math_prompt.txt.

    Args:
        question_json: Full question context from vision.

    Returns:
        Parsed pass-1 dict or error dict.
    """
    prompt_text = _load_math_prompt()
    context = _build_math_context(question_json)
    full_prompt = f"{prompt_text}\n\nQUESTION CONTEXT (JSON):\n{context}"
    return _call_and_parse(full_prompt, pass_label="Pass 1", required_key="answer")


def _run_pass2_recheck(
    question_json: dict[str, Any],
    pass1: dict[str, Any],
) -> dict[str, Any]:
    """
    Pass 2: independent verification via math_recheck_prompt.txt + type rules.

    Args:
        question_json: Vision context.
        pass1: Pass 1 result.

    Returns:
        Parsed recheck dict.
    """
    recheck_body = recheck_prompt.build_recheck_prompt(question_json, pass1)
    context = _build_math_context(question_json)
    working = str(pass1.get("working", ""))
    full_prompt = (
        f"{recheck_body}\n\n"
        f"PASS 1 WORKING (for reference only — do not copy blindly):\n{working}\n\n"
        f"QUESTION CONTEXT (JSON):\n{context}"
    )

    for attempt in range(2):
        raw = _call_ollama_text(full_prompt)
        if raw is None:
            print("Recheck request failed.")
            return {}
        parsed = _parse_json_response(raw)
        if parsed and "verified" in parsed:
            return parsed
        if attempt == 0:
            print("Recheck JSON parse failed; retrying once...")

    print("Recheck could not be parsed; using Pass 1 answer only.")
    return {
        "verified": True,
        "corrected_answer": pass1.get("answer", ""),
        "verification_working": "",
    }


def _merge_passes(
    question_json: dict[str, Any],
    pass1: dict[str, Any],
    pass2: dict[str, Any],
    *,
    recheck_skipped: bool,
    interactive_gate: bool = True,
) -> SolveResult:
    """
    Merge Pass 1 and Pass 2, validate, and run the confidence gate.

    Args:
        question_json: Vision extraction dict.
        pass1: Initial solve output.
        pass2: Recheck output (empty if skipped).
        recheck_skipped: True when think_mode disabled Pass 2.

    Returns:
        Final SolveResult after gate.
    """
    original = str(pass1.get("answer", ""))
    working = str(pass1.get("working", ""))
    verification = str(pass2.get("verification_working", ""))
    conf1 = float(pass1.get("confidence", 0.5))
    unit = pass1.get("answer_unit")

    verified = bool(pass2.get("verified", True)) if pass2 else True
    corrected = str(pass2.get("corrected_answer", original))

    was_corrected = False
    final_answer = original

    if pass2 and not verified:
        was_corrected = True
        final_answer = corrected
        _log_correction(original, corrected)
    elif pass2 and not recheck_skipped:
        final_answer = original

    if recheck_skipped:
        confidence = conf1
    else:
        conf2 = float(pass2.get("confidence", conf1)) if pass2 else conf1
        confidence = min(conf1, conf2)

    validate_answer(
        final_answer,
        str(question_json.get("answer_type", "number")),
        unit,
    )

    result = SolveResult(
        answer=final_answer,
        working=working,
        verification_working=verification,
        confidence=confidence,
        recheck_passed=verified and not was_corrected,
        original_answer=original if was_corrected else None,
        was_corrected=was_corrected,
        answer_unit=str(unit) if unit else None,
        ready_for_submit=confidence >= config.CONFIDENCE_THRESHOLD,
    )
    return apply_confidence_gate(
        result,
        recheck_skipped,
        interactive=interactive_gate,
    )


def _log_correction(original: str, corrected: str) -> None:
    """Print recheck correction notice to the terminal."""
    print(
        f"\n⚠️  Answer corrected by recheck\n"
        f"   Original: {original}\n"
        f"   Corrected: {corrected}\n"
    )


def apply_confidence_gate(
    result: SolveResult,
    recheck_skipped: bool,
    *,
    interactive: bool = True,
) -> SolveResult:
    """
    Prompt user when confidence is below threshold.

    Args:
        result: Candidate solve result.
        recheck_skipped: Whether Pass 2 was skipped.
        interactive: When False, leave ready_for_submit False for caller prompt.

    Returns:
        Result with ready_for_submit updated from user choice.
    """
    if result.confidence >= config.CONFIDENCE_THRESHOLD:
        result.ready_for_submit = True
        return result

    if not interactive:
        result.ready_for_submit = False
        return result

    print("\n── Low confidence — review before submitting ──")
    print("Pass 1 working:")
    print(result.working)
    if result.verification_working:
        print("Pass 2 verification working:")
        print(result.verification_working)
    else:
        print("Pass 2 verification working: (skipped)" if recheck_skipped else "Pass 2: (none)")
    print(f"Final answer: {result.answer}")
    print(f"Confidence: {result.confidence:.2f}")

    choice = input("[S]ubmit best guess / [E]dit answer / [K]ip this question? ").strip().lower()
    if choice == "s":
        result.ready_for_submit = True
    elif choice == "e":
        edited = input("Enter corrected answer: ").strip()
        if edited:
            result.answer = edited
            result.ready_for_submit = True
    else:
        print("Skipped — answer not marked ready for submit.")
        result.ready_for_submit = False
    return result


def validate_answer(
    answer: str,
    answer_type: str,
    answer_unit: str | None,
) -> bool:
    """
    Run sanity checks on the final answer (warnings only).

    Args:
        answer: Submission string.
        answer_type: Vision answer_type enum value.
        answer_unit: Optional unit from Pass 1.

    Returns:
        True if no warnings were raised.
    """
    ok = True
    if answer_type in ("number", "expression") and _looks_like_angle(answer):
        try:
            value = float(re.search(r"-?\d+\.?\d*", answer).group())  # type: ignore[union-attr]
            if value < 0 or value > 360:
                print(f"Warning: angle-like answer {value} outside 0°–360°.")
                ok = False
        except (ValueError, AttributeError):
            pass
    if answer_unit and answer_unit not in ("none", "") and answer_unit not in answer:
        print(f"Note: expected unit '{answer_unit}' may be missing from answer.")
    return ok


def _looks_like_angle(text: str) -> bool:
    """Return True if the answer string appears to be an angle."""
    lowered = text.lower()
    return "°" in text or "degree" in lowered or lowered.endswith("deg")


def _call_and_parse(
    full_prompt: str,
    *,
    pass_label: str,
    required_key: str,
) -> dict[str, Any]:
    """
    Call Ollama and parse JSON with one retry.

    Args:
        full_prompt: Complete prompt text.
        pass_label: Label for retry messages.
        required_key: Required JSON field.

    Returns:
        Parsed dict or error dict.
    """
    raw = ""
    for attempt in range(2):
        raw = _call_ollama_text(full_prompt) or ""
        if not raw:
            return {"error": True, "raw_response": "Ollama solver request failed."}
        parsed = _parse_json_response(raw)
        if parsed and required_key in parsed:
            return parsed
        if attempt == 0:
            print(f"{pass_label} JSON parse failed; retrying once...")
    return {"error": True, "raw_response": raw}


def _build_math_context(question_json: dict[str, Any]) -> str:
    """Serialize vision JSON for the solver prompt."""
    return json.dumps(question_json, indent=2)


def _load_math_prompt() -> str:
    """Load prompts/math_prompt.txt."""
    path = config.PROMPTS_DIR / "math_prompt.txt"
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"Could not read math prompt at {path}: {exc}")
        return ""


def _call_ollama_text(prompt: str) -> str | None:
    """Text-only Ollama generate using the configured solver model."""
    model = model_manager.get_solver_model()
    payload = {"model": model, "prompt": prompt, "stream": False}
    try:
        response = requests.post(
            config.OLLAMA_GENERATE_URL,
            json=payload,
            timeout=120,
        )
        response.raise_for_status()
        return str(response.json().get("response", ""))
    except (requests.RequestException, json.JSONDecodeError, KeyError) as exc:
        print(f"Ollama solver error: {exc}")
        return None


def _parse_json_response(raw: str) -> dict[str, Any] | None:
    """Parse JSON from model text with brace-block fallback."""
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = _JSON_BLOCK_RE.search(raw)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                return None
    return None


def error_result(message: str) -> SolveResult:
    """Build a failed SolveResult for terminal display."""
    return _error_result(message)


def _error_result(message: str) -> SolveResult:
    """Internal failed SolveResult builder."""
    return SolveResult(
        answer="",
        working=message,
        verification_working="",
        confidence=0.0,
        recheck_passed=False,
        original_answer=None,
        was_corrected=False,
        answer_unit=None,
        ready_for_submit=False,
    )
