#!/usr/bin/env python3
"""Create placeholder PNG templates in assets/templates/."""

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "templates"

PLACEHOLDERS = [
    ("answer_button.png", (120, 40), "#4a90d9"),
    ("correct_tick.png", (48, 48), "#2ecc71"),
    ("wrong_highlight.png", (80, 40), "#e74c3c"),
    ("next_button.png", (100, 36), "#9b59b6"),
    ("submit_button.png", (90, 36), "#34495e"),
    ("text_field.png", (200, 32), "#ecf0f1"),
]


def main() -> None:
    """Write coloured placeholder rectangles for each template slot."""
    OUT.mkdir(parents=True, exist_ok=True)
    for name, size, colour in PLACEHOLDERS:
        img = Image.new("RGB", size, colour)
        draw = ImageDraw.Draw(img)
        draw.rectangle((0, 0, size[0] - 1, size[1] - 1), outline="#000000", width=2)
        path = OUT / name
        img.save(path)
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
