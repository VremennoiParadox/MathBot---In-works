#!/usr/bin/env python3
"""Guide the user through capturing UI templates from their tutoring site."""

from __future__ import annotations

import sys
from pathlib import Path

import config
import region_selector

TEMPLATES = [
    (
        "answer_button.png",
        "Click and drag around the site's Answer button (just below your question region).",
    ),
    (
        "correct_tick.png",
        "Capture the green tick / success indicator shown after a correct answer.",
    ),
    (
        "wrong_highlight.png",
        "Capture the red error / wrong-answer highlight (optional but helpful).",
    ),
    (
        "next_button.png",
        "Capture the Next / Continue button that appears after answering.",
    ),
    (
        "submit_button.png",
        "Capture the Submit / Confirm button on the number pad (if separate).",
    ),
    (
        "text_field.png",
        "Capture the text input box (skip if you only use number pads).",
    ),
]


def main() -> int:
    """
    Walk through template capture into Application Support templates/.

    Returns:
        Exit code 0 on success.
    """
    print("=== MathBot template capture ===\n")
    config.load_config()
    config.TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

    print(
        "You will select a small rectangle for each UI element.\n"
        f"Files are saved to:\n  {config.TEMPLATES_DIR}\n"
    )
    input("Press Enter when your tutoring site is open on screen…")

    for filename, hint in TEMPLATES:
        print(f"\n--- {filename} ---")
        print(hint)
        skip = input("Press Enter to capture, or type 's' to skip: ").strip().lower()
        if skip == "s":
            continue
        region = region_selector.select_region()
        img = region_selector.region_to_image(region)
        dest = config.TEMPLATES_DIR / filename
        img.save(dest, format="PNG")
        print(f"✅ Saved {dest}")

    print("\nDone. Re-run MathBot: python main.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
