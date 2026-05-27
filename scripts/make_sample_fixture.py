#!/usr/bin/env python3
"""Create tests/fixtures/sample_question.png for --self-test."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tests" / "fixtures" / "sample_question.png"


def main() -> None:
    """Write a simple synthetic math question image."""
    img = Image.new("RGB", (640, 400), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.rectangle((20, 20, 620, 380), outline=(0, 0, 0), width=2)
    text = "Solve: 2x + 5 = 17\nFind x."
    draw.multiline_text((40, 40), text, fill=(0, 0, 0), spacing=8)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
