"""Region-aware UI automation via OpenCV template matching."""

from __future__ import annotations

import re
import threading
import time
from pathlib import Path
from typing import Literal

import cv2
import imagehash
import mss
import numpy as np
import pyautogui
from PIL import Image

import config
import region_selector

UIType = Literal[
    "number_pad",
    "text_input",
    "multiple_choice",
    "dropdown",
    "unknown",
]
LegacyUIType = Literal["number_pad", "multiple_choice", "text_field", "expression"]

_TEMPLATE_CONFIDENCE = 0.85
_SUCCESS_PHASH_DELTA = 12
_ANSWER_EXTEND_BELOW_PX = 120

_pyautogui_ready = False


def _init_pyautogui() -> None:
    """Configure pyautogui safety settings once."""
    global _pyautogui_ready
    if _pyautogui_ready:
        return
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = max(0.05, config.POST_CLICK_DELAY_MS / 1000.0)
    _pyautogui_ready = True


def check_accessibility() -> bool:
    """
    Verify pyautogui can read the cursor (Accessibility permission).

    Returns:
        True when mouse position is readable.
    """
    try:
        _init_pyautogui()
        pyautogui.position()
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"Accessibility check failed: {exc}", flush=True)
        print(
            "Enable: System Settings → Privacy & Security → Accessibility → Terminal",
            flush=True,
        )
        return False


def template_path(name: str) -> Path:
    """
    Resolve a template PNG (user templates dir, then bundled assets).

    Args:
        name: Filename such as 'answer_button.png'.

    Returns:
        First existing path, or user dir path for missing-file checks.
    """
    user = config.TEMPLATES_DIR / name
    if user.exists():
        return user
    bundled = config.ASSETS_TEMPLATES_DIR / name
    if bundled.exists():
        return bundled
    return user


def list_missing_templates(required: list[str]) -> list[str]:
    """
    Return required template filenames that are not on disk.

    Args:
        required: Template basenames to check.

    Returns:
        List of missing filenames.
    """
    return [name for name in required if not template_path(name).exists()]


def _bounds_from_region(
    region: dict[str, int],
    *,
    extend_below: int = 0,
) -> tuple[int, int, int, int]:
    """
    Convert region dict to left, top, right, bottom screen bounds.

    Args:
        region: x, y, width, height.
        extend_below: Extra pixels below region for Answer/Next buttons.

    Returns:
        (left, top, right, bottom) inclusive-exclusive for cropping.
    """
    left = int(region["x"])
    top = int(region["y"])
    right = left + int(region["width"])
    bottom = top + int(region["height"]) + extend_below
    return left, top, right, bottom


def _grab_bounds_bgr(left: int, top: int, right: int, bottom: int) -> np.ndarray:
    """
    Capture a screen rectangle as BGR numpy array.

    Args:
        left: Left edge in screen coordinates.
        top: Top edge.
        right: Right edge.
        bottom: Bottom edge.

    Returns:
        BGR image of the bounds.
    """
    width = max(1, right - left)
    height = max(1, bottom - top)
    monitor = {"left": left, "top": top, "width": width, "height": height}
    with mss.mss() as sct:
        shot = sct.grab(monitor)
        bgra = np.array(shot)
        return cv2.cvtColor(bgra, cv2.COLOR_BGRA2BGR)


def _match_in_crop(
    crop_bgr: np.ndarray,
    template_path: Path,
    confidence: float,
    offset_x: int,
    offset_y: int,
) -> tuple[int, int, float] | None:
    """
    Match template inside a crop; return screen-center coordinates.

    Args:
        crop_bgr: Cropped screen BGR image.
        template_path: Template PNG path.
        confidence: Minimum normalized score.
        offset_x: Crop origin x on screen.
        offset_y: Crop origin y on screen.

    Returns:
        (screen_x, screen_y, score) or None.
    """
    if not template_path.exists():
        return None
    try:
        template = cv2.imread(str(template_path), cv2.IMREAD_COLOR)
        if template is None:
            return None
        th, tw = template.shape[:2]
        if th > crop_bgr.shape[0] or tw > crop_bgr.shape[1]:
            return None
        result = cv2.matchTemplate(crop_bgr, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        if max_val < confidence:
            return None
        cx = offset_x + max_loc[0] + tw // 2
        cy = offset_y + max_loc[1] + th // 2
        return cx, cy, float(max_val)
    except cv2.error as exc:
        print(f"Template match error ({template_path.name}): {exc}", flush=True)
        return None


def find_and_click(
    template_name: str,
    region: dict[str, int],
    timeout: float = 5.0,
    *,
    extend_below: int = 0,
    dry_run: bool | None = None,
) -> bool:
    """
    Find a UI template within region bounds and click it.

    Args:
        template_name: PNG filename in templates/.
        region: Selected screen region.
        timeout: Max seconds to poll.
        extend_below: Allow search slightly below region (Answer/Next).
        dry_run: Override config.DRY_RUN.

    Returns:
        True if found and clicked (or dry-run logged).
    """
    use_dry = config.DRY_RUN if dry_run is None else dry_run
    path = template_path(template_name)
    left, top, right, bottom = _bounds_from_region(region, extend_below=extend_below)
    deadline = time.monotonic() + timeout
    poll_s = config.TEMPLATE_POLL_INTERVAL_MS / 1000.0

    while time.monotonic() < deadline:
        crop = _grab_bounds_bgr(left, top, right, bottom)
        hit = _match_in_crop(crop, path, _TEMPLATE_CONFIDENCE, left, top)
        if hit:
            label = template_name.replace(".png", "")
            return _click_at(hit[0], hit[1], use_dry, label)
        threading.Event().wait(poll_s)
    return False


def detect_ui_type(region: dict[str, int]) -> UIType:
    """
    Detect which answer-entry UI is visible inside the region.

    Args:
        region: Selected screen region.

    Returns:
        One of number_pad, text_input, multiple_choice, dropdown, unknown.
    """
    left, top, right, bottom = _bounds_from_region(region)
    crop = _grab_bounds_bgr(left, top, right, bottom)

    digit_hits = 0
    for d in range(10):
        path = template_path(f"digit_{d}.png")
        if path.exists() and _match_in_crop(crop, path, 0.82, left, top):
            digit_hits += 1
    if digit_hits >= 3:
        return "number_pad"

    if template_path("text_field.png").exists():
        if _match_in_crop(crop, template_path("text_field.png"), 0.8, left, top):
            return "text_input"

    for letter in "abcd":
        mcq = template_path(f"mcq_{letter}.png")
        if mcq.exists() and _match_in_crop(crop, mcq, 0.8, left, top):
            return "multiple_choice"

    if template_path("dropdown.png").exists():
        if _match_in_crop(crop, template_path("dropdown.png"), 0.8, left, top):
            return "dropdown"

    return "unknown"


def enter_answer(
    answer: str,
    ui_type: UIType | str,
    region: dict[str, int],
    *,
    dry_run: bool | None = None,
) -> bool:
    """
    Enter the answer using the strategy for the detected UI type.

    Args:
        answer: Verified answer string.
        ui_type: From detect_ui_type().
        region: Selected screen region.
        dry_run: Override config.DRY_RUN.

    Returns:
        True if entry steps completed (or dry-run).
    """
    use_dry = config.DRY_RUN if dry_run is None else dry_run
    if ui_type == "number_pad":
        return _enter_number_pad_region(answer, region, use_dry)
    if ui_type == "multiple_choice":
        return _enter_mcq_region(answer, region, use_dry)
    if ui_type == "dropdown":
        return _enter_dropdown_region(answer, region, use_dry)
    return _enter_text_region(answer, region, use_dry)


def advance_to_next_question(
    region: dict[str, int],
    *,
    dry_run: bool | None = None,
) -> bool:
    """
    Click next/continue after a confirmed correct answer.

    Args:
        region: Selected screen region.
        dry_run: Override config.DRY_RUN.

    Returns:
        True if a next button was found and clicked.
    """
    for name in ("next_button.png", "submit_button.png", "continue_button.png"):
        if template_path(name).exists():
            if find_and_click(
                name,
                region,
                timeout=4.0,
                extend_below=_ANSWER_EXTEND_BELOW_PX,
                dry_run=dry_run,
            ):
                return True
    return False


def check_answer_feedback(
    region: dict[str, int],
    timeout_seconds: float | None = None,
) -> str:
    """
    Look for correct tick or wrong highlight inside the region.

    Args:
        region: Selected screen region.
        timeout_seconds: Max wait (defaults to config).

    Returns:
        'correct', 'wrong', or 'unknown'.
    """
    timeout = timeout_seconds
    if timeout is None:
        timeout = float(config.get_config().get("answer_confirmation_timeout", 3.0))
    left, top, right, bottom = _bounds_from_region(
        region,
        extend_below=_ANSWER_EXTEND_BELOW_PX,
    )
    deadline = time.monotonic() + timeout
    poll_s = config.TEMPLATE_POLL_INTERVAL_MS / 1000.0

    tick = template_path("correct_tick.png")
    wrong = template_path("wrong_highlight.png")
    legacy_tick = template_path("tick_green.png")
    legacy_wrong = template_path("error_red.png")

    while time.monotonic() < deadline:
        crop = _grab_bounds_bgr(left, top, right, bottom)
        for path, label in (
            (tick, "correct"),
            (legacy_tick, "correct"),
            (wrong, "wrong"),
            (legacy_wrong, "wrong"),
        ):
            if path.exists() and _match_in_crop(crop, path, 0.78, left, top):
                return label
        threading.Event().wait(poll_s)
    return "unknown"


def click_answer_button(
    region: dict[str, int] | None = None,
    dry_run: bool = False,
) -> bool:
    """
    Find and click the Answer button (region-aware when region provided).

    Args:
        region: Optional selected region.
        dry_run: Log only, no mouse movement.

    Returns:
        True if button found.
    """
    if region is None:
        return _click_answer_fullscreen(dry_run)
    return find_and_click(
        "answer_button.png",
        region,
        timeout=5.0,
        extend_below=_ANSWER_EXTEND_BELOW_PX,
        dry_run=dry_run,
    )


def _click_answer_fullscreen(dry_run: bool) -> bool:
    """Legacy full-screen Answer button click."""
    pos = _wait_for_template_fullscreen("answer_button.png")
    if not pos:
        print("Answer button template not found.", flush=True)
        return False
    return _click_at(pos[0], pos[1], dry_run, "Answer")


def _enter_number_pad_region(answer: str, region: dict[str, int], dry_run: bool) -> bool:
    """Enter digits via templates within region."""
    cleaned = re.sub(r"[^\d.\-]", "", answer)
    if not cleaned:
        return False
    for char in cleaned:
        if char == ".":
            file = "decimal_point.png"
        elif char == "-":
            file = "minus.png"
        else:
            file = f"digit_{char}.png"
        if not find_and_click(file, region, timeout=3.0, dry_run=dry_run):
            return False
    return _click_submit_if_present(region, dry_run)


def _enter_text_region(answer: str, region: dict[str, int], dry_run: bool) -> bool:
    """Focus text field and type answer."""
    find_and_click("text_field.png", region, timeout=2.0, dry_run=dry_run)
    if _dry(f"Would type: {answer!r}", dry_run):
        return True
    try:
        _init_pyautogui()
        delay = config.INTER_CHARACTER_DELAY_MS / 1000.0
        pyautogui.write(answer, interval=delay)
        return _click_submit_if_present(region, dry_run)
    except Exception as exc:  # noqa: BLE001
        print(f"Typing failed: {exc}", flush=True)
        return False


def _enter_mcq_region(answer: str, region: dict[str, int], dry_run: bool) -> bool:
    """Select MCQ option by letter template."""
    letter = answer.strip().upper()[:1]
    if not letter.isalpha():
        match = re.search(r"\b([A-D])\b", answer.upper())
        letter = match.group(1) if match else "A"
    file = f"mcq_{letter.lower()}.png"
    if template_path(file).exists():
        return find_and_click(file, region, timeout=3.0, dry_run=dry_run)
    return _enter_text_region(letter, region, dry_run)


def _enter_dropdown_region(answer: str, region: dict[str, int], dry_run: bool) -> bool:
    """Open dropdown and pick matching option text."""
    if not find_and_click("dropdown.png", region, timeout=3.0, dry_run=dry_run):
        return False
    threading.Event().wait(0.2)
    return _enter_text_region(answer, region, dry_run)


def _click_submit_if_present(region: dict[str, int], dry_run: bool) -> bool:
    """Click submit/confirm when template exists."""
    if not template_path("submit_button.png").exists():
        return True
    return find_and_click(
        "submit_button.png",
        region,
        timeout=3.0,
        extend_below=_ANSWER_EXTEND_BELOW_PX,
        dry_run=dry_run,
    )


def _dry(msg: str, dry_run: bool) -> bool:
    """Print dry-run line when enabled."""
    if dry_run:
        print(f"[DRY RUN] {msg}", flush=True)
        return True
    return False


def _click_at(x: int, y: int, dry_run: bool, label: str) -> bool:
    """Click screen coordinates or log dry-run."""
    if _dry(f"Would click {label} at ({x}, {y})", dry_run):
        return True
    try:
        _init_pyautogui()
        pyautogui.click(x, y)
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"Click failed at ({x}, {y}): {exc}", flush=True)
        return False


# --- Legacy API (hotkey / graph_solver compatibility) ---


def wait_for_template(
    template_file: str,
    timeout_ms: int | None = None,
    poll_ms: int | None = None,
    confidence: float = _TEMPLATE_CONFIDENCE,
) -> tuple[int, int] | None:
    """
    Poll full screen until a template appears (legacy).

    Returns:
        Center (x, y) in screen coordinates, or None.
    """
    path = template_path(template_file)
    timeout = timeout_ms if timeout_ms is not None else config.TEMPLATE_TIMEOUT_MS
    poll = poll_ms if poll_ms is not None else config.TEMPLATE_POLL_INTERVAL_MS
    deadline = time.monotonic() + timeout / 1000.0

    while time.monotonic() < deadline:
        screen = _grab_screen_bgr_full()
        hit = _match_in_crop(screen, path, confidence, 0, 0)
        if hit:
            return hit[0], hit[1]
        threading.Event().wait(poll / 1000.0)
    return None


def _wait_for_template_fullscreen(template_file: str) -> tuple[int, int] | None:
    """Full-screen template wait helper."""
    pos = wait_for_template(template_file)
    return pos


def _grab_screen_bgr_full() -> np.ndarray:
    """Capture primary display as BGR."""
    with mss.mss() as sct:
        monitor = sct.monitors[1]
        shot = sct.grab(monitor)
        bgra = np.array(shot)
        return cv2.cvtColor(bgra, cv2.COLOR_BGRA2BGR)


def detect_ui_type_legacy(answer_type: str) -> LegacyUIType:
    """Legacy UI type from vision answer_type string."""
    if answer_type == "multiple_choice":
        return "multiple_choice"
    if answer_type in ("expression", "text"):
        return "expression"
    if template_path("digit_0.png").exists():
        return "number_pad"
    return "text_field"


def enter_number_pad(answer: str, dry_run: bool = False) -> bool:
    """Legacy full-screen number pad entry."""
    region = config.SELECTED_REGION
    if region:
        return _enter_number_pad_region(answer, region, dry_run)
    cleaned = re.sub(r"[^\d.\-]", "", answer)
    for char in cleaned:
        file = f"digit_{char}.png" if char.isdigit() else "decimal_point.png"
        pos = wait_for_template(file, timeout_ms=3000)
        if not pos:
            return False
        if not _click_at(pos[0], pos[1], dry_run, file):
            return False
    return True


def enter_text_field(answer: str, dry_run: bool = False) -> bool:
    """Legacy text field entry."""
    region = config.SELECTED_REGION
    if region:
        return _enter_text_region(answer, region, dry_run)
    pos = wait_for_template("text_field.png", timeout_ms=3000)
    if pos:
        _click_at(pos[0], pos[1], dry_run, "text_field")
    if _dry(f"Would type: {answer!r}", dry_run):
        return True
    _init_pyautogui()
    pyautogui.write(answer, interval=0.03)
    return True


def select_multiple_choice(option: str, dry_run: bool = False) -> bool:
    """Legacy MCQ selection."""
    region = config.SELECTED_REGION
    if region:
        return _enter_mcq_region(option, region, dry_run)
    letter = option.strip().upper()[:1]
    pos = wait_for_template(f"mcq_{letter.lower()}.png", timeout_ms=2500)
    if pos:
        return _click_at(pos[0], pos[1], dry_run, f"option {letter}")
    return enter_text_field(letter, dry_run=dry_run)


def submit_answer(dry_run: bool = False) -> bool:
    """Legacy submit click."""
    region = config.SELECTED_REGION
    if region:
        return _click_submit_if_present(region, dry_run)
    if not template_path("submit_button.png").exists():
        return True
    pos = wait_for_template("submit_button.png", timeout_ms=3000)
    if not pos:
        return True
    return _click_at(pos[0], pos[1], dry_run, "Submit")


def detect_answer_accepted(
    before_question: Image.Image | None = None,
    timeout_ms: int | None = None,
) -> bool:
    """Legacy success detection on full screen."""
    region = config.SELECTED_REGION
    if region:
        # 200ms grace for submission latency before checking tick
        threading.Event().wait(0.2)
        outcome = check_answer_feedback(
            region,
            timeout_seconds=(timeout_ms or 3000) / 1000.0,
        )
        return outcome == "correct"

    timeout = timeout_ms if timeout_ms is not None else config.TEMPLATE_TIMEOUT_MS
    poll = config.TEMPLATE_POLL_INTERVAL_MS
    deadline = time.monotonic() + timeout / 1000.0
    before_hash = imagehash.phash(before_question) if before_question else None

    while time.monotonic() < deadline:
        screen = _grab_screen_bgr_full()
        for name in ("tick_green.png", "correct_tick.png"):
            path = template_path(name)
            if path.exists() and _match_in_crop(screen, path, 0.8, 0, 0):
                return True
        if before_hash is not None:
            after = imagehash.phash(_grab_screen_pil_full())
            if before_hash - after >= _SUCCESS_PHASH_DELTA:
                return True
        threading.Event().wait(poll / 1000.0)
    return False


def _grab_screen_pil_full() -> Image.Image:
    """Full screen PIL capture."""
    with mss.mss() as sct:
        monitor = sct.monitors[1]
        shot = sct.grab(monitor)
        return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")


def run_automation(
    answer: str,
    answer_type: str,
    before_question: Image.Image | None = None,
    dry_run: bool | None = None,
    region: dict[str, int] | None = None,
) -> bool:
    """
    Full UI flow: Answer → enter → submit → detect accepted.

    Args:
        answer: Verified answer string.
        answer_type: Vision answer_type enum.
        before_question: Pre-submit screenshot for phash compare.
        dry_run: Override config.DRY_RUN.
        region: Optional region override.

    Returns:
        True if automation completed successfully (or dry-run).
    """
    use_dry = config.DRY_RUN if dry_run is None else dry_run
    active_region = region or config.SELECTED_REGION

    if not answer.strip():
        print("Automation skipped: empty answer.", flush=True)
        return False

    if list_missing_templates(["answer_button.png"]):
        print(f"Add answer_button.png to: {config.TEMPLATES_DIR}", flush=True)
        return False

    if not use_dry and not check_accessibility():
        return False

    print(f"\n🖱️  Automation ({'dry run' if use_dry else 'live'})…", flush=True)

    if active_region:
        if not click_answer_button(active_region, dry_run=use_dry):
            return False
        ui = detect_ui_type(active_region)
        if ui == "unknown":
            ui = detect_ui_type_legacy(answer_type)  # type: ignore[assignment]
            if ui == "text_field":
                ui = "text_input"
        if not enter_answer(answer, ui, active_region, dry_run=use_dry):
            return False
        threading.Event().wait(0.2)  # grace before tick check — submission latency
        if use_dry:
            _dry("Would check correct_tick.png", True)
            return True
        feedback = check_answer_feedback(active_region)
        if feedback == "correct":
            advance_to_next_question(active_region, dry_run=use_dry)
            return True
        return feedback != "wrong"

    if not click_answer_button(dry_run=use_dry):
        return False
    ui = detect_ui_type_legacy(answer_type)
    entered = False
    if ui == "number_pad":
        entered = enter_number_pad(answer, dry_run=use_dry)
    elif ui == "multiple_choice":
        entered = select_multiple_choice(answer, dry_run=use_dry)
    else:
        entered = enter_text_field(answer, dry_run=use_dry)
    if not entered:
        return False
    if not submit_answer(dry_run=use_dry):
        return False
    if use_dry:
        return True
    threading.Event().wait(0.2)
    return detect_answer_accepted(before_question=before_question)
