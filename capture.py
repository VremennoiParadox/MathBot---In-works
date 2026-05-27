"""Screenshot capture for the primary display."""

from __future__ import annotations

import base64
import io
from datetime import datetime
from pathlib import Path

import mss
from PIL import Image

import config


def crop_question_region(full: Image.Image) -> Image.Image:
    """
    Crop the upper portion of the screen as the question area (phash identity).

    Args:
        full: Full-screen PIL image.

    Returns:
        Cropped question-region image.
    """
    width, height = full.size
    ratio = 0.6
    if config.QUESTION_REGION and isinstance(config.QUESTION_REGION.get("height_ratio"), (int, float)):
        ratio = float(config.QUESTION_REGION["height_ratio"])
    crop_h = max(1, int(height * ratio))
    return full.crop((0, 0, width, crop_h))


def capture_screen() -> tuple[str, str]:
    """
    Capture the full primary display and save a timestamped PNG.

    Returns:
        Tuple of (absolute filepath, base64-encoded PNG string).

    Raises:
        RuntimeError: If capture or save fails after retry.
    """
    config.SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}.png"
    filepath = config.SCREENSHOTS_DIR / filename

    image = _capture_primary_display()
    _save_image(image, filepath)
    b64 = _image_to_base64(image)
    return str(filepath), b64


def _capture_primary_display() -> Image.Image:
    """
    Grab the primary monitor using mss.

    Returns:
        PIL Image of the screenshot.

    Raises:
        RuntimeError: On repeated capture failure.
    """
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            with mss.mss() as sct:
                monitor = sct.monitors[1]
                shot = sct.grab(monitor)
                return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
        except Exception as exc:  # noqa: BLE001 — surface friendly message
            last_error = exc
            print(f"Screenshot capture failed (attempt {attempt + 1}): {exc}")
    raise RuntimeError(f"Could not capture screen: {last_error}")


def _save_image(image: Image.Image, filepath: Path) -> None:
    """
    Write PIL image to disk as PNG.

    Args:
        image: Screenshot image.
        filepath: Destination path.
    """
    try:
        image.save(filepath, format="PNG")
    except OSError as exc:
        raise RuntimeError(f"Could not save screenshot to {filepath}: {exc}") from exc


def _image_to_base64(image: Image.Image) -> str:
    """
    Encode image as base64 PNG for Ollama vision API.

    Args:
        image: Screenshot image.

    Returns:
        UTF-8 base64 string without data-URI prefix.
    """
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("utf-8")
