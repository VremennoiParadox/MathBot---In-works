"""Local and vision-based graph detection for routing to graph solver."""

from __future__ import annotations

from typing import Any

import cv2
import numpy as np
from PIL import Image


def quick_check_for_graph(image: Image.Image) -> bool:
    """
    Fast OpenCV heuristic for graph-like visuals (no AI call).

    Args:
        image: Question region screenshot.

    Returns:
        True when axis/grid/bar-chart patterns are likely present.
    """
    bgr = cv2.cvtColor(np.array(image.convert("RGB")), cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape[:2]
    if h < 40 or w < 40:
        return False

    score = 0
    if _has_axis_lines(gray):
        score += 2
    if _has_grid_pattern(gray):
        score += 2
    if _has_bar_chart_regions(bgr):
        score += 2
    if _has_tick_marks(gray):
        score += 1
    return score >= 3


def should_use_graph_model(image: Image.Image, vision_response: dict[str, Any]) -> bool:
    """
    Combine local heuristic and vision model response for graph routing.

    Args:
        image: Region screenshot.
        vision_response: Parsed vision JSON.

    Returns:
        True to route through graph_solver pipeline.
    """
    if vision_response.get("contains_graph") is True:
        return True
    if vision_response.get("answer_type") == "graph":
        return True
    return quick_check_for_graph(image)


def _has_axis_lines(gray: np.ndarray) -> bool:
    """Detect long horizontal/vertical lines near image edges."""
    edges = cv2.Canny(gray, 50, 150)
    lines = cv2.HoughLinesP(
        edges,
        1,
        np.pi / 180,
        threshold=80,
        minLineLength=int(min(gray.shape) * 0.35),
        maxLineGap=12,
    )
    if lines is None:
        return False
    h, w = gray.shape
    horiz = 0
    vert = 0
    for line in lines[:40]:
        x1, y1, x2, y2 = line[0]
        if abs(y2 - y1) < 8 and abs(x2 - x1) > w * 0.25:
            horiz += 1
        if abs(x2 - x1) < 8 and abs(y2 - y1) > h * 0.25:
            vert += 1
    return horiz >= 1 and vert >= 1


def _has_grid_pattern(gray: np.ndarray) -> bool:
    """Detect intersecting light grid lines in the interior."""
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    edges = cv2.Canny(blur, 30, 100)
    lines = cv2.HoughLinesP(
        edges,
        1,
        np.pi / 180,
        threshold=60,
        minLineLength=int(min(gray.shape) * 0.15),
        maxLineGap=8,
    )
    if lines is None or len(lines) < 6:
        return False
    return len(lines) >= 8


def _has_tick_marks(gray: np.ndarray) -> bool:
    """Detect short perpendicular marks along edges (axis ticks)."""
    edges = cv2.Canny(gray, 40, 120)
    lines = cv2.HoughLinesP(
        edges,
        1,
        np.pi / 180,
        threshold=40,
        minLineLength=6,
        maxLineGap=4,
    )
    if lines is None:
        return False
    short_lines = 0
    for line in lines:
        x1, y1, x2, y2 = line[0]
        length = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
        if 6 <= length <= 25:
            short_lines += 1
    return short_lines >= 6


def _has_bar_chart_regions(bgr: np.ndarray) -> bool:
    """Detect large solid-colour rectangles typical of bar charts."""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    h, w = bgr.shape[:2]
    min_area = (h * w) * 0.02
    for channel in (hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]):
        _, mask = cv2.threshold(channel, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < min_area:
                continue
            x, y, bw, bh = cv2.boundingRect(cnt)
            aspect = bw / max(bh, 1)
            if 0.2 < aspect < 5.0 and bh > h * 0.08:
                return True
    return False
