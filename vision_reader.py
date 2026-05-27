"""Vision model: screenshot base64 → structured question JSON."""

from __future__ import annotations

import json
import re
from typing import Any

import requests

import config
import model_manager

_JSON_BLOCK_RE = re.compile(r"\{[\s\S]*\}")


def read_question(base64_image: str) -> dict[str, Any]:
    """
    Run vision model on a base64 PNG and return parsed question JSON.

    Args:
        base64_image: PNG image encoded as base64 (no data-URI prefix).

    Returns:
        Parsed question dict, or {"error": true, "raw_response": "..."} on failure.
    """
    prompt = _load_vision_prompt()
    model = model_manager.get_vision_model()

    result = _read_with_model(base64_image, prompt, model)
    if not result.get("error"):
        return result

    fallback = config.VISION_FALLBACK_MODEL
    if model.lower().startswith(fallback.split(":")[0].lower()):
        return result

    print(f"Vision model '{model}' failed; retrying with fallback '{fallback}'.")
    return _read_with_model(base64_image, prompt, fallback)


def _read_with_model(base64_image: str, prompt: str, model: str) -> dict[str, Any]:
    """
    Call vision API up to two parse attempts for one model.

    Args:
        base64_image: Base64 PNG string.
        prompt: Vision system prompt text.
        model: Ollama model name.

    Returns:
        Parsed JSON dict or error dict.
    """
    for attempt in range(2):
        raw = call_ollama_vision(base64_image, prompt, model)
        if raw is None:
            return {"error": True, "raw_response": "Ollama vision request failed."}
        parsed = _parse_json_response(raw)
        if parsed is not None:
            if "answer_type" not in parsed:
                parsed["answer_type"] = "number"
            return parsed
        if attempt == 0:
            print("Vision JSON parse failed; retrying once...")
    return {"error": True, "raw_response": raw or ""}


def _load_vision_prompt() -> str:
    """
    Load prompts/vision_prompt.txt from bundled resources.

    Returns:
        Prompt file contents.
    """
    path = config.PROMPTS_DIR / "vision_prompt.txt"
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"Could not read vision prompt at {path}: {exc}")
        return ""


def call_ollama_vision(base64_image: str, prompt: str, model: str) -> str | None:
    """
    POST to Ollama /api/generate with an image attachment.

    Args:
        base64_image: Base64-encoded PNG.
        prompt: Full prompt text.
        model: Ollama model name.

    Returns:
        Raw response text, or None on failure.
    """
    payload = {
        "model": model,
        "prompt": prompt,
        "images": [base64_image],
        "stream": False,
    }
    try:
        response = requests.post(
            config.OLLAMA_GENERATE_URL,
            json=payload,
            timeout=120,
        )
        response.raise_for_status()
        data = response.json()
        return str(data.get("response", ""))
    except (requests.RequestException, json.JSONDecodeError, KeyError) as exc:
        print(f"Ollama vision error ({model}): {exc}")
        return None


def parse_json_response(raw: str) -> dict[str, Any] | None:
    """
    Parse JSON from model output with markdown-fence fallback.

    Args:
        raw: Model text output.

    Returns:
        Parsed dict or None if parsing fails.
    """
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
