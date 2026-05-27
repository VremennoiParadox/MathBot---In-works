"""Load config.json, resolve Application Support paths, and expose typed settings."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any, TypedDict

# Ollama endpoints (static — not user config)
OLLAMA_HOST: str = "http://localhost:11434"
OLLAMA_GENERATE_URL: str = f"{OLLAMA_HOST}/api/generate"

# Vision fallback when primary model fails (defined here only — never elsewhere)
VISION_FALLBACK_MODEL: str = "moondream:v2"

# Static thresholds and timing (not in config.json)
IMAGE_HASH_MATCH_THRESHOLD: int = 8
TEMPLATE_POLL_INTERVAL_MS: int = 100
TEMPLATE_TIMEOUT_MS: int = 5000
POST_CLICK_DELAY_MS: int = 50
AUTO_START_OLLAMA: bool = True

QUESTION_REGION: dict[str, Any] | None = None
ANSWER_REGION: dict[str, Any] | None = None


class SessionStats(TypedDict, total=False):
    """Session statistics persisted in config.json."""

    last_session_id: str | None
    avg_solve_time_ms: float | None
    model_combo: str | None


class AppConfig(TypedDict):
    """User-facing configuration loaded from config.json."""

    vision_model: str
    solver_model: str
    graph_model: str
    think_mode: bool
    confidence_threshold: float
    dry_run: bool
    default_hotkey: str
    graph_hotkey: str
    session_stats: SessionStats


def get_app_support_dir() -> Path:
    """
    Return ~/Library/Application Support/MathBot, creating it if missing.

    Returns:
        Path to the MathBot Application Support directory.
    """
    app_dir = Path.home() / "Library" / "Application Support" / "MathBot"
    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir


APP_SUPPORT_DIR: Path = get_app_support_dir()
CONFIG_PATH: Path = APP_SUPPORT_DIR / "config.json"
DB_PATH: Path = APP_SUPPORT_DIR / "db" / "mathbot.sqlite"
SCREENSHOTS_DIR: Path = APP_SUPPORT_DIR / "screenshots"
EXPORTS_DIR: Path = APP_SUPPORT_DIR / "exports"
TEMPLATES_DIR: Path = APP_SUPPORT_DIR / "templates"

_config: AppConfig | None = None
first_run: bool = False

# Typed constants (populated by load_config)
VISION_MODEL: str = ""
SOLVER_MODEL: str = ""
GRAPH_MODEL: str = ""
THINK_MODE: bool = True
CONFIDENCE_THRESHOLD: float = 0.75
DRY_RUN: bool = False
DEFAULT_HOTKEY: str = "cmd+shift+s"
GRAPH_HOTKEY: str = "cmd+shift+g"
SESSION_STATS: SessionStats = {}


def is_frozen() -> bool:
    """
    Check whether the app runs inside a PyInstaller bundle.

    Returns:
        True if sys._MEIPASS is present.
    """
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def resource_path(relative: str) -> Path:
    """
    Resolve a bundled read-only asset path (prompts, defaults).

    Args:
        relative: Path relative to project root or PyInstaller bundle.

    Returns:
        Absolute path to the resource.
    """
    if is_frozen():
        base = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    else:
        base = Path(__file__).resolve().parent
    return base / relative


PROMPTS_DIR: Path = resource_path("prompts")
BUNDLE_DIR: Path = resource_path(".")
DEFAULT_CONFIG_PATH: Path = resource_path("config.json.default")


def _ensure_writable_dirs() -> None:
    """Create db, screenshots, templates, and exports under Application Support."""
    for folder in (DB_PATH.parent, SCREENSHOTS_DIR, TEMPLATES_DIR, EXPORTS_DIR):
        folder.mkdir(parents=True, exist_ok=True)


def seed_templates_from_bundle() -> None:
    """Copy bundled templates/*.png into Application Support if missing."""
    bundle_templates = resource_path("templates")
    if not bundle_templates.is_dir():
        return
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    for src in bundle_templates.glob("*.png"):
        dest = TEMPLATES_DIR / src.name
        if not dest.exists():
            try:
                shutil.copy2(src, dest)
            except OSError as exc:
                print(f"Could not copy template {src.name}: {exc}")


def _default_config() -> AppConfig:
    """Load defaults from config.json.default shipped with the repo."""
    try:
        with DEFAULT_CONFIG_PATH.open(encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return AppConfig(
            vision_model="",
            solver_model="",
            graph_model="",
            think_mode=True,
            confidence_threshold=0.75,
            dry_run=False,
            default_hotkey="cmd+shift+s",
            graph_hotkey="cmd+shift+g",
            session_stats=SessionStats(),
        )


def _apply_constants(cfg: AppConfig) -> None:
    """Copy AppConfig fields into module-level typed constants."""
    global VISION_MODEL, SOLVER_MODEL, GRAPH_MODEL, THINK_MODE
    global CONFIDENCE_THRESHOLD, DRY_RUN, DEFAULT_HOTKEY, GRAPH_HOTKEY, SESSION_STATS

    VISION_MODEL = cfg["vision_model"]
    SOLVER_MODEL = cfg["solver_model"]
    GRAPH_MODEL = cfg["graph_model"]
    THINK_MODE = cfg["think_mode"]
    CONFIDENCE_THRESHOLD = cfg["confidence_threshold"]
    DRY_RUN = cfg["dry_run"]
    DEFAULT_HOTKEY = cfg["default_hotkey"]
    GRAPH_HOTKEY = cfg["graph_hotkey"]
    SESSION_STATS = cfg.get("session_stats", SessionStats())


def load_config() -> AppConfig:
    """
    Load config.json from Application Support; set first_run if missing.

    Returns:
        Loaded AppConfig dictionary.
    """
    global _config, first_run

    _ensure_writable_dirs()
    seed_templates_from_bundle()

    if not CONFIG_PATH.exists():
        first_run = True
        defaults = _default_config()
        _config = defaults
        _apply_constants(defaults)
        return defaults

    first_run = False
    try:
        with CONFIG_PATH.open(encoding="utf-8") as handle:
            data: dict[str, Any] = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        backup = CONFIG_PATH.with_suffix(".json.bak")
        try:
            shutil.copy2(CONFIG_PATH, backup)
            print(f"Invalid config.json backed up to {backup}: {exc}")
        except OSError:
            print(f"Invalid config.json and backup failed: {exc}")
        first_run = True
        data = dict(_default_config())

    merged = _default_config()
    merged.update({k: v for k, v in data.items() if k in merged or k == "session_stats"})
    if "session_stats" not in merged:
        merged["session_stats"] = SessionStats()

    _config = merged  # type: ignore[assignment]
    _apply_constants(merged)
    return merged


def get_config() -> AppConfig:
    """
    Return cached configuration, loading first if needed.

    Returns:
        Current AppConfig.

    Raises:
        RuntimeError: If configuration was never loaded.
    """
    if _config is None:
        return load_config()
    return _config


def save_config(updates: dict[str, Any]) -> None:
    """
    Merge updates into config.json and refresh module constants.

    Args:
        updates: Partial config fields to write.
    """
    global _config

    cfg = dict(get_config())
    cfg.update(updates)
    if "session_stats" in updates:
        stats = dict(cfg.get("session_stats", {}))
        stats.update(updates["session_stats"])
        cfg["session_stats"] = stats

    with CONFIG_PATH.open("w", encoding="utf-8") as handle:
        json.dump(cfg, handle, indent=2)

    _config = cfg  # type: ignore[assignment]
    _apply_constants(cfg)  # type: ignore[arg-type]
