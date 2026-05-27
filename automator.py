"""UI automation: template matching, answer entry, success detection."""

from __future__ import annotations

import re
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

UIType = Literal["number_pad", "multiple_choice", "text_field", "expression"]

_TEMPLATE_CONFIDENCE = 0.85
_SUCCESS_PHASH_DELTA = 12

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
        print(f"Accessibility check failed: {exc}")
        print(
            "Enable: System Settings → Privacy & Security → Accessibility → Terminal"
        )
        return False


def template_path(name: str) -> Path:
    """
    Resolve a template PNG under Application Support templates/.

    Args:
        name: Filename such as 'answer_button.png'.

    Returns:
        Absolute path to the template file.
    """
    return config.TEMPLATES_DIR / name


def list_missing_templates(required: list[str]) -> list[str]:
    """
    Return required template filenames that are not on disk.

    Args:
        required: Template basenames to check.

    Returns:
        List of missing filenames.
    """
    return [name for name in required if not template_path(name).exists()]


def _grab_screen_bgr() -> np.ndarray:
    """
    Capture the primary display as an OpenCV BGR image.

    Returns:
        BGR numpy array of the full screen.
    """
    with mss.mss() as sct:
        monitor = sct.monitors[1]
        shot = sct.grab(monitor)
        bgra = np.array(shot)
        return cv2.cvtColor(bgra, cv2.COLOR_BGRA2BGR)


def _match_template(
    screen_bgr: np.ndarray,
    template_path: Path,
    confidence: float,
) -> tuple[int, int, float] | None:
    """
    Find template on screen; return center x, y and score.

    Args:
        screen_bgr: Full screen BGR image.
        template_path: Path to template PNG.
        confidence: Minimum match score 0–1.

    Returns:
        (center_x, center_y, score) or None.
    """
    if not template_path.exists():
        return None
    try:
        template = cv2.imread(str(template_path), cv2.IMREAD_COLOR)
        if template is None:
            return None
        result = cv2.matchTemplate(screen_bgr, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        if max_val < confidence:
            return None
        h, w = template.shape[:2]
        cx = max_loc[0] + w // 2
        cy = max_loc[1] + h // 2
        return cx, cy, float(max_val)
    except cv2.error as exc:
        print(f"Template match error ({template_path.name}): {exc}")
        return None


def wait_for_template(
    template_file: str,
    timeout_ms: int | None = None,
    poll_ms: int | None = None,
    confidence: float = _TEMPLATE_CONFIDENCE,
) -> tuple[int, int] | None:
    """
    Poll the screen until a template appears or timeout.

    Args:
        template_file: PNG filename in templates/.
        timeout_ms: Max wait (defaults to config.TEMPLATE_TIMEOUT_MS).
        poll_ms: Poll interval (defaults to config.TEMPLATE_POLL_INTERVAL_MS).
        confidence: matchTemplate threshold.

    Returns:
        Center (x, y) in screen coordinates, or None.
    """
    path = template_path(template_file)
    timeout = timeout_ms if timeout_ms is not None else config.TEMPLATE_TIMEOUT_MS
    poll = poll_ms if poll_ms is not None else config.TEMPLATE_POLL_INTERVAL_MS
    deadline = time.monotonic() + timeout / 1000.0

    while time.monotonic() < deadline:
        screen = _grab_screen_bgr()
        hit = _match_template(screen, path, confidence)
        if hit:
            return hit[0], hit[1]
        time.sleep(poll / 1000.0)  # poll interval — not a blind fixed delay
    return None


def _dry(msg: str, dry_run: bool) -> bool:
    """Print dry-run line when enabled; return True if dry."""
    if dry_run:
        print(f"[DRY RUN] {msg}", flush=True)
        return True
    return False


def _click_at(x: int, y: int, dry_run: bool, label: str) -> bool:
    """
    Click screen coordinates or log dry-run intent.

    Returns:
        True if click attempted or dry-run logged.
    """
    if _dry(f"Would click {label} at ({x}, {y})", dry_run):
        return True
    try:
        _init_pyautogui()
        pyautogui.click(x, y)
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"Click failed at ({x}, {y}): {exc}")
        return False


def click_answer_button(dry_run: bool = False) -> bool:
    """
    Find and click the Answer button template.

    Args:
        dry_run: Log only, no mouse movement.

    Returns:
        True if button found (and clicked unless dry_run).
    """
    pos = wait_for_template("answer_button.png")
    if not pos:
        print("Answer button template not found. Add templates/answer_button.png")
        return False
    return _click_at(pos[0], pos[1], dry_run, "Answer")


def detect_ui_type(answer_type: str) -> UIType:
    """
    Infer UI entry mode from vision answer_type and template presence.

    Args:
        answer_type: Vision classification string.

    Returns:
        UIType for entry strategy.
    """
    if answer_type == "multiple_choice":
        return "multiple_choice"
    if answer_type in ("expression", "text"):
        return "expression"
    if template_path("digit_0.png").exists():
        return "number_pad"
    if template_path("text_field.png").exists():
        return "text_field"
    if answer_type == "number":
        return "number_pad"
    return "text_field"


def enter_number_pad(answer: str, dry_run: bool = False) -> bool:
    """
    Enter a numeric answer via digit templates (0–9, decimal).

    Args:
        answer: Numeric string to enter.
        dry_run: Log only.

    Returns:
        True if all characters were entered or dry-run logged.
    """
    cleaned = re.sub(r"[^\d.\-]", "", answer)
    if not cleaned:
        print("Number pad: empty answer after cleaning.")
        return False

    for char in cleaned:
        if char == ".":
            file = "decimal_point.png"
        elif char == "-":
            file = "minus.png"
        else:
            file = f"digit_{char}.png"
        pos = wait_for_template(file, timeout_ms=3000)
        if not pos:
            print(f"Digit template missing or not visible: {file}")
            return False
        if not _click_at(pos[0], pos[1], dry_run, file):
            return False
    return True


def enter_text_field(answer: str, dry_run: bool = False) -> bool:
    """
    Click text field template and type the answer.

    Args:
        answer: Text to type.
        dry_run: Log only.

    Returns:
        True on success.
    """
    pos = wait_for_template("text_field.png", timeout_ms=3000)
    if pos:
        if not _click_at(pos[0], pos[1], dry_run, "text_field"):
            return False
    elif not _dry("Would focus text field (no template — typing at cursor)", dry_run):
        pass

    if _dry(f"Would type: {answer!r}", dry_run):
        return True
    try:
        _init_pyautogui()
        pyautogui.write(answer, interval=0.03)
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"Typing failed: {exc}")
        return False


def select_multiple_choice(option: str, dry_run: bool = False) -> bool:
    """
    Select MCQ option by letter (A–D) via template or typing.

    Args:
        option: Option letter or full option text from solver.
        dry_run: Log only.

    Returns:
        True on success.
    """
    letter = option.strip().upper()[:1]
    if not letter.isalpha():
        match = re.search(r"\b([A-D])\b", option.upper())
        letter = match.group(1) if match else "A"

    mcq_file = f"mcq_{letter.lower()}.png"
    pos = wait_for_template(mcq_file, timeout_ms=2500)
    if pos:
        return _click_at(pos[0], pos[1], dry_run, f"option {letter}")

    return enter_text_field(letter, dry_run=dry_run)


def submit_answer(dry_run: bool = False) -> bool:
    """
    Click submit/confirm if a separate template exists.

    Args:
        dry_run: Log only.

    Returns:
        True if clicked, dry-run, or no submit button required.
    """
    if not template_path("submit_button.png").exists():
        return True
    pos = wait_for_template("submit_button.png", timeout_ms=3000)
    if not pos:
        return True
    return _click_at(pos[0], pos[1], dry_run, "Submit")


def _grab_screen_pil() -> Image.Image:
    """Capture primary display as a PIL RGB image."""
    with mss.mss() as sct:
        monitor = sct.monitors[1]
        shot = sct.grab(monitor)
        return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")


def detect_answer_accepted(
    before_question: Image.Image | None = None,
    timeout_ms: int | None = None,
) -> bool:
    """
    Detect success via tick template or large change in screen phash.

    Args:
        before_question: PIL image from pre-submit capture.
        timeout_ms: Max wait for success indicators.

    Returns:
        True if success detected; False if error template or timeout.
    """
    timeout = timeout_ms if timeout_ms is not None else config.TEMPLATE_TIMEOUT_MS
    poll = config.TEMPLATE_POLL_INTERVAL_MS
    deadline = time.monotonic() + timeout / 1000.0
    before_hash = imagehash.phash(before_question) if before_question else None

    while time.monotonic() < deadline:
        screen = _grab_screen_bgr()
        err_path = template_path("error_red.png")
        if err_path.exists() and _match_template(screen, err_path, 0.8):
            print("Error indicator detected on screen.")
            return False

        tick_path = template_path("tick_green.png")
        if tick_path.exists():
            hit = _match_template(screen, tick_path, 0.8)
            if hit:
                print("Success tick detected.")
                return True

        if before_hash is not None:
            try:
                after_hash = imagehash.phash(_grab_screen_pil())
                if before_hash - after_hash >= _SUCCESS_PHASH_DELTA:
                    print("Screen changed — assuming question advanced.")
                    return True
            except Exception as exc:  # noqa: BLE001
                print(f"phash compare failed: {exc}")

        time.sleep(poll / 1000.0)
    print("Timed out waiting for success confirmation.")
    return False


def run_automation(
    answer: str,
    answer_type: str,
    before_question: Image.Image | None = None,
    dry_run: bool | None = None,
) -> bool:
    """
    Full UI flow: Answer → enter by type → submit → detect accepted.

    Args:
        answer: Verified answer string to submit.
        answer_type: Vision answer_type enum value.
        before_question: Screenshot before submit for phash compare.
        dry_run: Override config.DRY_RUN when not None.

    Returns:
        True if automation completed and success was detected (or dry-run).
    """
    use_dry = config.DRY_RUN if dry_run is None else dry_run
    if not answer.strip():
        print("Automation skipped: empty answer.")
        return False

    required = ["answer_button.png"]
    missing = list_missing_templates(required)
    if missing:
        print(f"Missing required templates: {', '.join(missing)}")
        print(f"Add PNG files to: {config.TEMPLATES_DIR}")
        return False

    if not use_dry and not check_accessibility():
        return False

    print(f"\n🖱️  Automation ({'dry run' if use_dry else 'live'})…", flush=True)

    if not click_answer_button(dry_run=use_dry):
        return False

    ui = detect_ui_type(answer_type)
    entered = False
    if ui == "number_pad":
        entered = enter_number_pad(answer, dry_run=use_dry)
    elif ui == "multiple_choice":
        entered = select_multiple_choice(answer, dry_run=use_dry)
    else:
        entered = enter_text_field(answer, dry_run=use_dry)

    if not entered:
        print("Answer entry failed.")
        return False

    if not submit_answer(dry_run=use_dry):
        return False

    if use_dry:
        _dry("Would wait for success template 'tick_green.png'", True)
        return True

    return detect_answer_accepted(before_question=before_question)
