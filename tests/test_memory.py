"""Unit tests for MemoryStore (temporary database)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

import math_solver
import memory


def _blank_image() -> Image.Image:
    """Create a small solid image for phash tests."""
    return Image.new("RGB", (120, 80), color=(200, 100, 50))


def test_phash_and_hamming(tmp_path: Path) -> None:
    """Same image yields distance 0; different images differ."""
    store = memory.MemoryStore(tmp_path / "test.sqlite")
    img = _blank_image()
    h1 = store.compute_phash(img)
    h2 = store.compute_phash(img.copy())
    assert store.hamming_distance(h1, h2) == 0
    other = Image.new("RGB", (200, 150), color=(10, 200, 30))
    for x in range(0, 200, 10):
        for y in range(0, 150, 10):
            other.putpixel((x, y), (x % 255, y % 255, (x + y) % 255))
    h3 = store.compute_phash(other)
    assert store.hamming_distance(h1, h3) > 0
    store.close()


def test_store_and_exact_cache(tmp_path: Path) -> None:
    """Stored answer is returned by exact phash cache lookup."""
    db = tmp_path / "mem.sqlite"
    store = memory.MemoryStore(db)
    session = store.start_session()
    img = _blank_image()
    phash = store.compute_phash(img)
    result = math_solver.SolveResult(
        answer="42",
        working="steps",
        verification_working="check",
        confidence=0.9,
        recheck_passed=True,
        original_answer=None,
        was_corrected=False,
        answer_unit=None,
        ready_for_submit=True,
    )
    vision = {"question_text": "Q", "answer_type": "number"}
    store.store_question_answer(session, img, vision, result, tmp_path / "s.png")
    cached = store.get_cached_answer(phash)
    assert cached is not None
    assert cached["answer_value"] == "42"
    store.close()


def test_similar_recall(tmp_path: Path) -> None:
    """Near-identical image triggers recall_for_verification."""
    store = memory.MemoryStore(tmp_path / "sim.sqlite")
    session = store.start_session()
    img = _blank_image()
    result = math_solver.SolveResult(
        answer="7",
        working="w",
        verification_working="v",
        confidence=0.95,
        recheck_passed=True,
        original_answer=None,
        was_corrected=False,
        answer_unit=None,
        ready_for_submit=True,
    )
    store.store_question_answer(
        session,
        img,
        {"question_text": "T", "answer_type": "number"},
        result,
        tmp_path / "a.png",
    )
    hit = store.recall_for_verification(img.copy())
    assert hit is not None
    assert hit["answer_value"] == "7"
    store.close()
