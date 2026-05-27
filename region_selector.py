"""Fullscreen region selection overlay and region-scoped capture."""

from __future__ import annotations

import base64
import io
import tkinter as tk
from datetime import datetime
from typing import Any

import mss
from PIL import Image

import config


def select_region() -> dict[str, int]:
    """
    Show the fullscreen overlay, block until the user draws a region.

    Returns:
        Dict with keys x, y, width, height in screen coordinates.

    Raises:
        SystemExit: When the user presses Escape.
    """
    root = tk.Tk()
    root.withdraw()
    screen_w = root.winfo_screenwidth()
    screen_h = root.winfo_screenheight()
    root.destroy()

    state: dict[str, Any] = {
        "start": None,
        "rect_id": None,
        "result": None,
        "cancelled": False,
    }

    overlay = tk.Tk()
    overlay.title("MathBot — select question region")
    overlay.geometry(f"{screen_w}x{screen_h}+0+0")
    overlay.attributes("-topmost", True)
    overlay.overrideredirect(True)
    try:
        overlay.attributes("-alpha", 0.35)
    except tk.TclError:
        pass
    overlay.configure(bg="#1a1a2e", cursor="crosshair")

    canvas = tk.Canvas(
        overlay,
        width=screen_w,
        height=screen_h,
        highlightthickness=0,
        bg="#1a1a2e",
    )
    canvas.pack(fill=tk.BOTH, expand=True)

    hint = canvas.create_text(
        screen_w // 2,
        40,
        text="Drag to select the question area · Esc to cancel",
        fill="white",
        font=("Helvetica", 16),
    )

    def _on_escape(_event: tk.Event | None = None) -> None:
        """Cancel selection and exit."""
        state["cancelled"] = True
        overlay.destroy()

    def _on_press(event: tk.Event) -> None:
        """Record drag start."""
        state["start"] = (event.x, event.y)
        if state["rect_id"] is not None:
            canvas.delete(state["rect_id"])
        state["rect_id"] = canvas.create_rectangle(
            event.x,
            event.y,
            event.x,
            event.y,
            outline="#00ff88",
            width=3,
            fill="#00ff88",
            stipple="gray50",
        )

    def _on_drag(event: tk.Event) -> None:
        """Redraw selection rectangle."""
        if state["start"] is None or state["rect_id"] is None:
            return
        x0, y0 = state["start"]
        canvas.coords(state["rect_id"], x0, y0, event.x, event.y)

    def _on_release(event: tk.Event) -> None:
        """Finalize region and close overlay."""
        if state["start"] is None:
            return
        x0, y0 = state["start"]
        x1, y1 = event.x, event.y
        left = min(x0, x1)
        top = min(y0, y1)
        width = abs(x1 - x0)
        height = abs(y1 - y0)
        if width < 20 or height < 20:
            return
        state["result"] = {
            "x": int(left),
            "y": int(top),
            "width": int(width),
            "height": int(height),
        }
        overlay.destroy()

    overlay.bind("<Escape>", _on_escape)
    canvas.bind("<ButtonPress-1>", _on_press)
    canvas.bind("<B1-Motion>", _on_drag)
    canvas.bind("<ButtonRelease-1>", _on_release)
    overlay.mainloop()

    if state["cancelled"] or state["result"] is None:
        print("Region selection cancelled.", flush=True)
        raise SystemExit(0)

    region = state["result"]
    config.save_config({"selected_region": region})
    print(
        f"✅ Region locked: {region['width']}x{region['height']} "
        f"at ({region['x']}, {region['y']}) — starting solver loop",
        flush=True,
    )
    return region


def capture_region(region: dict[str, int]) -> tuple[str, str]:
    """
    Capture only the selected region using mss.

    Args:
        region: Dict with x, y, width, height.

    Returns:
        Tuple of (absolute filepath, base64-encoded PNG string).

    Raises:
        RuntimeError: If capture or save fails.
    """
    config.SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = config.SCREENSHOTS_DIR / f"{timestamp}.png"

    image = _grab_region_image(region)
    try:
        image.save(filepath, format="PNG")
    except OSError as exc:
        raise RuntimeError(f"Could not save screenshot to {filepath}: {exc}") from exc

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return str(filepath), b64


def region_to_image(region: dict[str, int]) -> Image.Image:
    """
    Capture the region as a PIL image without saving to disk.

    Args:
        region: Screen region dict.

    Returns:
        RGB PIL image of the region.
    """
    return _grab_region_image(region)


def _grab_region_image(region: dict[str, int]) -> Image.Image:
    """
    Grab a monitor sub-rectangle via mss.

    Args:
        region: x, y, width, height in screen coordinates.

    Returns:
        RGB PIL image.

    Raises:
        RuntimeError: On capture failure.
    """
    monitor = {
        "left": int(region["x"]),
        "top": int(region["y"]),
        "width": int(region["width"]),
        "height": int(region["height"]),
    }
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            with mss.mss() as sct:
                shot = sct.grab(monitor)
                return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            print(f"Region capture failed (attempt {attempt + 1}): {exc}", flush=True)
    raise RuntimeError(f"Could not capture region: {last_error}")


def load_saved_region() -> dict[str, int] | None:
    """
    Load selected_region from config if present and valid.

    Returns:
        Region dict or None.
    """
    cfg = config.get_config()
    region = cfg.get("selected_region")
    if not isinstance(region, dict):
        return None
    keys = ("x", "y", "width", "height")
    if not all(k in region for k in keys):
        return None
    try:
        return {k: int(region[k]) for k in keys}
    except (TypeError, ValueError):
        return None
