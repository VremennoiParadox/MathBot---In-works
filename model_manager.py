"""Ollama model discovery, setup wizard, RAM checks, and model accessors."""

from __future__ import annotations

import subprocess
import sys
from typing import Literal

import psutil
import requests

import config

VISION_TAGS: tuple[str, ...] = ("vl", "vision", "llava", "moondream", "gemma", "minicpm")

# Heuristic RAM estimates (GB) for wizard warnings
_RAM_ESTIMATES_GB: dict[str, float] = {
    "moondream": 2.0,
    "minicpm": 4.0,
    "gemma": 5.0,
    "llava": 6.0,
    "vl": 8.0,
    "vision": 8.0,
    "math": 6.0,
    "deepseek-r1:14b": 14.0,
    "deepseek-r1:7b": 7.0,
    "qwen2.5-math": 6.0,
    "qwen2.5vl": 8.0,
}


def list_installed_models() -> list[str]:
    """
    Parse `ollama list` output and return installed model names.

    Returns:
        List of model name strings as reported by Ollama.
    """
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"Failed to run 'ollama list': {exc}")
        return []

    if result.returncode != 0:
        print(result.stderr.strip() or "ollama list failed.")
        return []

    models: list[str] = []
    for line in result.stdout.strip().splitlines()[1:]:
        parts = line.split()
        if parts:
            models.append(parts[0])
    return models


def is_vision_capable(model_name: str) -> bool:
    """
    Return True if the model name matches vision capability keywords.

    Args:
        model_name: Ollama model name.

    Returns:
        True when any VISION_TAGS substring appears (case-insensitive).
    """
    lowered = model_name.lower()
    return any(tag in lowered for tag in VISION_TAGS)


def group_models(models: list[str]) -> tuple[list[str], list[str]]:
    """
    Split models into vision-capable and text-only lists.

    Args:
        models: All installed model names.

    Returns:
        Tuple of (vision_capable, text_only).
    """
    vision = [m for m in models if is_vision_capable(m)]
    text_only = [m for m in models if not is_vision_capable(m)]
    return vision, text_only


def estimate_model_ram_gb(model_name: str) -> float:
    """
    Estimate RAM usage in GB using name heuristics.

    Args:
        model_name: Ollama model name.

    Returns:
        Estimated gigabytes for worst-case load.
    """
    lowered = model_name.lower()
    for key, gb in sorted(_RAM_ESTIMATES_GB.items(), key=lambda x: -len(x[0])):
        if key in lowered:
            return gb
    if "14b" in lowered or ":14b" in lowered:
        return 14.0
    if "7b" in lowered or ":7b" in lowered:
        return 7.0
    if "3b" in lowered:
        return 3.0
    return 6.0


def check_ram_for_combo(vision: str, solver: str, graph: str) -> tuple[bool, str]:
    """
    Warn if vision+solver peak exceeds 80% of available RAM.

    Args:
        vision: Vision model name.
        solver: Solver model name.
        graph: Graph model name.

    Returns:
        (ok, message) — ok is False when over threshold.
    """
    peak = estimate_model_ram_gb(vision) + estimate_model_ram_gb(solver)
    peak = max(peak, estimate_model_ram_gb(graph))
    available_gb = psutil.virtual_memory().available / (1024**3)
    limit = available_gb * 0.8
    if peak > limit:
        return (
            False,
            f"Estimated peak RAM ~{peak:.1f} GB exceeds 80% of available "
            f"({limit:.1f} GB of {available_gb:.1f} GB free).",
        )
    return True, f"Estimated peak RAM ~{peak:.1f} GB within safe range."


def check_ollama_running() -> bool:
    """
    Return True if Ollama HTTP API responds.

    Returns:
        True when GET to OLLAMA_HOST succeeds.
    """
    try:
        response = requests.get(config.OLLAMA_HOST, timeout=3)
        return response.status_code < 500
    except requests.RequestException:
        return False


def _print_ollama_start_help() -> None:
    """Print instructions when Ollama is not reachable."""
    print("\nOllama is not running.")
    print("Start it with:  ollama serve")
    print("Then run MathBot again.\n")


def _prompt_number(prompt: str, choices: list[str]) -> str:
    """
    Show numbered list and return selected model name.

    Args:
        prompt: User-facing prompt line.
        choices: Model names to pick from.

    Returns:
        Selected model name.
    """
    if not choices:
        print("No models available for this category.")
        return ""

    print(f"\n{prompt}")
    for idx, name in enumerate(choices, start=1):
        tag = "vision" if is_vision_capable(name) else "text"
        print(f"  {idx}. {name}  [{tag}]")

    while True:
        raw = input("Enter number: ").strip()
        try:
            num = int(raw)
            if 1 <= num <= len(choices):
                return choices[num - 1]
        except ValueError:
            pass
        print(f"Please enter a number between 1 and {len(choices)}.")


def _read_wizard_options() -> tuple[bool, float, bool]:
    """
    Read optional wizard fields for think_mode, threshold, and dry_run.

    Returns:
        Tuple of (think_mode, confidence_threshold, dry_run).
    """
    think_raw = input("think_mode [true] (forced recheck): ").strip().lower()
    think_mode = think_raw not in ("false", "f", "0", "no")

    thresh_raw = input("confidence_threshold [0.75]: ").strip()
    try:
        confidence_threshold = float(thresh_raw) if thresh_raw else 0.75
    except ValueError:
        confidence_threshold = 0.75

    dry_raw = input("dry_run [false]: ").strip().lower()
    dry_run = dry_raw in ("true", "t", "1", "yes", "y")
    return think_mode, confidence_threshold, dry_run


def get_vision_model() -> str:
    """
    Return the configured vision model name.

    Returns:
        vision_model from config.
    """
    return config.get_config()["vision_model"]


def get_solver_model() -> str:
    """
    Return the configured solver model name.

    Returns:
        solver_model from config.
    """
    return config.get_config()["solver_model"]


def run_setup_wizard() -> dict:
    """
    Interactive first-run wizard; write config.json to Application Support.

    Returns:
        Config dict written to disk.
    """
    if not check_ollama_running():
        _print_ollama_start_help()
        sys.exit(1)

    models = list_installed_models()
    if not models:
        print("No Ollama models installed. Run:  ollama pull <model>")
        sys.exit(1)

    vision_list, text_list = group_models(models)
    if not vision_list:
        print("\nNo vision-capable models found in Ollama.")
        print("Installed models:")
        for name in models:
            print(f"  - {name}")
        print(
            "\nMathBot needs a model that can read screenshots. Pull one, then run main.py again:\n"
            "  ollama pull moondream:v2        # small (~1.7 GB), good for 8–12 GB Macs\n"
            "  ollama pull qwen2.5vl:7b        # better vision (~6 GB)\n"
        )
        sys.exit(1)
    if not text_list:
        print("\nNo text-only solver models found.")
        print("Installed models:")
        for name in models:
            tag = "vision" if is_vision_capable(name) else "text"
            print(f"  - {name}  [{tag}]")
        print(
            "\nPull a math/text solver, then run main.py again:\n"
            "  ollama pull qwen2.5:7b\n"
            "  ollama pull mightykatun/qwen2.5-math:7b\n"
        )
        sys.exit(1)

    print("\n=== MathBot Model Selection Wizard ===\n")
    vision = _prompt_number("Select your VISION model (reads the screenshot):", vision_list)
    solver = _prompt_number("Select your MATH SOLVER model (solves the problem):", text_list)
    graph = _prompt_number(
        "Select your GRAPH model (same as vision or different):",
        vision_list,
    )

    think_mode, confidence_threshold, dry_run = _read_wizard_options()

    ok, msg = check_ram_for_combo(vision, solver, graph)
    print(msg)
    if not ok:
        cont = input("Continue anyway? [y/N]: ").strip().lower()
        if cont not in ("y", "yes"):
            return run_setup_wizard()

    cfg = config.get_config()
    cfg["vision_model"] = vision
    cfg["solver_model"] = solver
    cfg["graph_model"] = graph
    cfg["think_mode"] = think_mode
    cfg["confidence_threshold"] = confidence_threshold
    cfg["dry_run"] = dry_run

    config.save_config(cfg)
    config.first_run = False
    print(f"\nConfiguration saved to {config.CONFIG_PATH}\n")
    return cfg


def pull_model(model_name: str) -> bool:
    """
    Pull an Ollama model; stream progress to the terminal.

    Args:
        model_name: Model tag to pull.

    Returns:
        True if pull succeeded.
    """
    print(f"\nPulling {model_name}…")
    try:
        proc = subprocess.run(
            ["ollama", "pull", model_name],
            timeout=3600,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"Pull failed: {exc}")
        return False
    if proc.returncode != 0:
        print(f"ollama pull {model_name} failed.")
        return False
    print(f"Successfully pulled {model_name}.")
    return True


def _ensure_model_available(model_name: str) -> bool:
    """
    Ensure model is installed; offer pull if missing.

    Args:
        model_name: Ollama model name.

    Returns:
        True if model is available locally.
    """
    if model_name in list_installed_models():
        return True
    print(f"Model '{model_name}' is not installed.")
    choice = input(f"Pull now with 'ollama pull {model_name}'? [y/N]: ").strip().lower()
    if choice in ("y", "yes"):
        return pull_model(model_name)
    return False


def _unload_model(model_name: str) -> None:
    """
    Best-effort unload of a running Ollama model.

    Args:
        model_name: Model to stop.
    """
    if not model_name:
        return
    try:
        subprocess.run(
            ["ollama", "stop", model_name],
            capture_output=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"Note: could not unload {model_name}: {exc}")


def switch_model(role: Literal["vision", "solver", "graph"], new_name: str) -> None:
    """
    Switch vision, solver, or graph model; persist to config.json.

    Args:
        role: Which config field to update.
        new_name: New Ollama model name.
    """
    if not _ensure_model_available(new_name):
        print("Keeping previous model.")
        return

    cfg = config.get_config()
    key = f"{role}_model"
    old_name = cfg.get(key, "")

    if role == "vision" and not is_vision_capable(new_name):
        print("Warning: selected model may not support vision.")
    if role == "solver" and is_vision_capable(new_name):
        print("Warning: solver is usually a text-only math model.")

    _unload_model(old_name)
    config.save_config({key: new_name})
    print(f"Switched {role} model: {old_name} → {new_name}")


def run_model_switcher(current_config: dict | None = None) -> dict:
    """
    Mid-session model picker (M key); updates config without restart.

    Args:
        current_config: Optional existing config (reloads if None).

    Returns:
        Updated config dict.
    """
    if not check_ollama_running():
        _print_ollama_start_help()
        return config.get_config()

    cfg = current_config or config.get_config()
    models = list_installed_models()
    if not models:
        print("No models installed.")
        return cfg

    vision_list, text_list = group_models(models)
    print("\n=== Change models (Enter to keep current) ===\n")

    if vision_list:
        print("Vision models:")
        for i, name in enumerate(vision_list, 1):
            print(f"  {i}. {name}")
    current_v = cfg["vision_model"]
    raw_v = input(f"Vision [{current_v}] — number or Enter to keep: ").strip()
    if raw_v.isdigit() and vision_list:
        idx = int(raw_v) - 1
        if 0 <= idx < len(vision_list):
            switch_model("vision", vision_list[idx])

    current_s = cfg["solver_model"]
    if text_list:
        print("\nSolver models:")
        for i, name in enumerate(text_list, 1):
            print(f"  {i}. {name}")
    raw_s = input(f"Solver [{current_s}] — number or Enter to keep: ").strip()
    if raw_s.isdigit() and text_list:
        idx = int(raw_s) - 1
        if 0 <= idx < len(text_list):
            switch_model("solver", text_list[idx])

    if vision_list:
        print("\nGraph models (vision-capable):")
        for i, name in enumerate(vision_list, 1):
            print(f"  {i}. {name}")
    current_g = cfg["graph_model"]
    raw_g = input(f"Graph [{current_g}] — number or Enter to keep: ").strip()
    if raw_g.isdigit() and vision_list:
        idx = int(raw_g) - 1
        if 0 <= idx < len(vision_list):
            switch_model("graph", vision_list[idx])

    updated = config.get_config()
    print(
        f"\nNow using: [{updated['vision_model']} → vision] "
        f"[{updated['solver_model']} → solver] "
        f"[{updated['graph_model']} → graph]\n"
    )
    return updated
