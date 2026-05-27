"""Build Pass 2 recheck prompts from math_recheck_prompt.txt and question type."""

from __future__ import annotations

from typing import Any, Literal

import config

RecheckCategory = Literal[
    "geometry",
    "proportion",
    "algebra",
    "multiple_choice",
    "general",
]

RECHECK_PHRASE = (
    "do not simply confirm the previous answer — use a different method to verify"
)

_TYPE_RULES: dict[RecheckCategory, str] = {
    "geometry": (
        "GEOMETRY: Verify angle sums for the stated shape. "
        "The final angle must be between 0° and 360°."
    ),
    "proportion": (
        "PROPORTIONALITY: Substitute your answer back into the original proportion "
        "or variation relation; both sides must match exactly."
    ),
    "algebra": (
        "ALGEBRA: Substitute your answer into the original equation; "
        "left-hand and right-hand sides must be equal."
    ),
    "multiple_choice": (
        "MULTIPLE CHOICE: Confirm the selected option follows from independent "
        "working — do not restate the first answer without justification."
    ),
    "general": (
        "Use an independent method (work backwards, substitute, or alternate approach)."
    ),
}


def detect_recheck_category(question_json: dict[str, Any]) -> RecheckCategory:
    """
    Infer recheck rule set from vision JSON text and answer_type.

    Args:
        question_json: Vision extraction dict.

    Returns:
        Category key for type-specific recheck instructions.
    """
    if question_json.get("answer_type") == "multiple_choice":
        return "multiple_choice"

    blob = " ".join(
        [
            str(question_json.get("question_text", "")),
            str(question_json.get("visual_elements", "")),
            str(question_json.get("question_asked", "")),
            " ".join(str(c) for c in question_json.get("constraints", [])),
        ]
    ).lower()

    geometry_words = ("angle", "triangle", "degree", "°", "polygon", "isosceles", "geometry")
    proportion_words = ("proportion", "proportional", "ratio", "variation", "directly", "inversely")
    algebra_words = ("equation", "solve for", "algebra", "expression", "factorise", "factorize")

    if any(word in blob for word in geometry_words):
        return "geometry"
    if any(word in blob for word in proportion_words):
        return "proportion"
    if any(word in blob for word in algebra_words) or "=" in blob:
        return "algebra"
    return "general"


def load_recheck_prompt_template() -> str:
    """
    Load prompts/math_recheck_prompt.txt from bundled resources.

    Returns:
        Template text with [answer] placeholder.
    """
    path = config.PROMPTS_DIR / "math_recheck_prompt.txt"
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"Could not read recheck prompt at {path}: {exc}")
        return ""


def build_recheck_prompt(question_json: dict[str, Any], pass1: dict[str, Any]) -> str:
    """
    Build Pass 2 prompt from template, Pass 1 answer, and type-specific rules.

    Args:
        question_json: Vision extraction dict.
        pass1: Pass 1 solver JSON (answer, working, confidence).

    Returns:
        Full recheck prompt string for the solver model.
    """
    answer = str(pass1.get("answer", ""))
    category = detect_recheck_category(question_json)
    rules = _TYPE_RULES[category]

    template = load_recheck_prompt_template()
    if not template:
        template = (
            "You previously solved this problem and got [answer].\n"
            "Independently verify using a different method.\n"
        )

    prompt = template.replace("[answer]", answer)
    prompt += (
        f"\n\nADDITIONAL RULES FOR THIS QUESTION:\n{rules}\n\n"
        f"CRITICAL: {RECHECK_PHRASE}.\n"
    )
    return prompt
