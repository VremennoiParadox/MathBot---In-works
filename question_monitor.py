"""Detect question changes and page stability in the selected region."""

from __future__ import annotations

import threading
from typing import Any

import imagehash
from PIL import Image

import config
import region_selector


_last_hash: imagehash.ImageHash | None = None
_last_frame: Image.Image | None = None


def has_question_changed(current_frame: Image.Image) -> bool:
    """
    Return True if phash distance from the last stored frame exceeds threshold.

    Args:
        current_frame: Latest region screenshot.

    Returns:
        True when the question area looks different enough to be a new question.
    """
    global _last_hash
    current_hash = imagehash.phash(current_frame)
    if _last_hash is None:
        return True
    threshold = int(config.get_config().get("change_threshold", 10))
    return (current_hash - _last_hash) > threshold


def update_last_seen(frame: Image.Image) -> None:
    """
    Store the current frame as the new baseline for change detection.

    Args:
        frame: Region PIL image after a question transition.
    """
    global _last_hash, _last_frame
    _last_frame = frame.copy()
    _last_hash = imagehash.phash(_last_frame)


def reset_monitor() -> None:
    """Clear stored baseline (e.g. at session start)."""
    global _last_hash, _last_frame
    _last_hash = None
    _last_frame = None


def wait_for_question_change(
    region: dict[str, int],
    timeout_seconds: int = 30,
) -> bool:
    """
    Poll the region every 300ms until the question image changes.

    Args:
        region: Selected screen region.
        timeout_seconds: Max wait time.

    Returns:
        True if change detected, False on timeout.
    """
    poll_s = 0.3
    deadline = _monotonic_deadline(timeout_seconds)
    baseline = _last_hash

    while _monotonic_now() < deadline:
        frame = region_selector.region_to_image(region)
        current = imagehash.phash(frame)
        if baseline is not None and (current - baseline) > _change_threshold():
            update_last_seen(frame)
            return True
        if baseline is None and _last_hash is not None:
            if has_question_changed(frame):
                update_last_seen(frame)
                return True
        threading.Event().wait(poll_s)
    return False


def wait_for_page_ready(
    region: dict[str, int],
    stable_duration_seconds: float | None = None,
) -> None:
    """
    Wait until the region has been visually stable for stable_duration_seconds.

    Args:
        region: Selected screen region.
        stable_duration_seconds: Override config page_ready_stable_duration.
    """
    cfg = config.get_config()
    stable = stable_duration_seconds
    if stable is None:
        stable = float(cfg.get("page_ready_stable_duration", 1.5))
    poll_s = 0.3
    required_stable = stable

    prev_hash: imagehash.ImageHash | None = None
    stable_since: float | None = None
    deadline = _monotonic_deadline(max(required_stable * 4, 8.0))

    while _monotonic_now() < deadline:
        frame = region_selector.region_to_image(region)
        current = imagehash.phash(frame)
        now = _monotonic_now()
        if prev_hash is not None and (current - prev_hash) <= _change_threshold():
            if stable_since is None:
                stable_since = now
            elif now - stable_since >= required_stable:
                return
        else:
            stable_since = None
        prev_hash = current
        threading.Event().wait(poll_s)


def _change_threshold() -> int:
    """Read change_threshold from config."""
    return int(config.get_config().get("change_threshold", 10))


def _monotonic_now() -> float:
    """Monotonic clock seconds."""
    import time

    return time.monotonic()


def _monotonic_deadline(seconds: float) -> float:
    """Deadline from now in monotonic seconds."""
    return _monotonic_now() + seconds
