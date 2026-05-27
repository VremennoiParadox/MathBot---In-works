"""Screenshot capture — delegates region capture to region_selector."""

from __future__ import annotations

from PIL import Image

import config
import region_selector


def crop_question_region(full: Image.Image) -> Image.Image:
    """
    Return the image used for phash identity (full frame or upper crop).

    Args:
        full: Captured region or screen image.

    Returns:
        Image for perceptual hashing.
    """
    region = config.SELECTED_REGION
    if region:
        return full
    width, height = full.size
    ratio = 0.6
    if config.QUESTION_REGION and isinstance(
        config.QUESTION_REGION.get("height_ratio"), (int, float)
    ):
        ratio = float(config.QUESTION_REGION["height_ratio"])
    crop_h = max(1, int(height * ratio))
    return full.crop((0, 0, width, crop_h))


def capture_screen() -> tuple[str, str]:
    """
    Capture the configured region, or full screen if no region is set.

    Returns:
        Tuple of (absolute filepath, base64-encoded PNG string).

    Raises:
        RuntimeError: If capture fails.
    """
    region = config.SELECTED_REGION or region_selector.load_saved_region()
    if region:
        return region_selector.capture_region(region)
    return _capture_full_screen_legacy()


def capture_region(region: dict[str, int]) -> tuple[str, str]:
    """
    Capture only the given screen region.

    Args:
        region: Dict with x, y, width, height.

    Returns:
        Tuple of (filepath, base64 PNG).
    """
    return region_selector.capture_region(region)


def _capture_full_screen_legacy() -> tuple[str, str]:
    """
    Legacy full-primary-monitor capture when no region is configured.

    Returns:
        Tuple of (filepath, base64 PNG).
    """
    import base64
    import io
    from datetime import datetime

    import mss

    config.SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = config.SCREENSHOTS_DIR / f"{timestamp}.png"

    with mss.mss() as sct:
        monitor = sct.monitors[1]
        shot = sct.grab(monitor)
        image = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")

    image.save(filepath, format="PNG")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return str(filepath), b64
