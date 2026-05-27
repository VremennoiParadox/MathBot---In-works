"""SQLite persistence, perceptual-hash recall, and session export."""

from __future__ import annotations

import csv
import json
import socket
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import imagehash
from PIL import Image

import config

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id   TEXT PRIMARY KEY,
    started_at   TEXT NOT NULL,
    ended_at     TEXT,
    hostname     TEXT,
    vision_model TEXT,
    solver_model TEXT,
    graph_model  TEXT,
    avg_solve_time_ms REAL,
    notes        TEXT
);

CREATE TABLE IF NOT EXISTS questions (
    question_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id       TEXT NOT NULL REFERENCES sessions(session_id),
    phash            TEXT NOT NULL,
    question_text    TEXT,
    answer_type      TEXT,
    question_type    TEXT DEFAULT 'standard',
    vision_json      TEXT,
    screenshot_path  TEXT,
    created_at       TEXT NOT NULL,
    UNIQUE(session_id, phash)
);

CREATE INDEX IF NOT EXISTS idx_questions_phash ON questions(phash);

CREATE TABLE IF NOT EXISTS answers (
    answer_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id          INTEGER NOT NULL REFERENCES questions(question_id),
    answer_value         TEXT NOT NULL,
    answer_working       TEXT,
    answer_unit          TEXT,
    verification_working TEXT,
    recheck_passed       INTEGER NOT NULL DEFAULT 1,
    original_answer      TEXT,
    confidence           REAL,
    solve_json           TEXT,
    submitted_at         TEXT NOT NULL,
    accepted             INTEGER,
    UNIQUE(question_id)
);

CREATE INDEX IF NOT EXISTS idx_answers_question ON answers(question_id);
CREATE INDEX IF NOT EXISTS idx_answers_recheck ON answers(recheck_passed);
"""


def _utc_now() -> str:
    """Return current UTC time as ISO8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _retry_db(operation: Callable[[], Any]) -> Any:
    """Run DB operation with retries on lock."""
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            return operation()
        except sqlite3.OperationalError as exc:
            last_exc = exc
            if "locked" not in str(exc).lower():
                raise
            time.sleep(0.15 * (attempt + 1))
    raise last_exc  # type: ignore[misc]


class MemoryStore:
    """SQLite store for questions, verified answers, and verification recall."""

    def __init__(self, db_path: Path | None = None) -> None:
        """
        Open or create mathbot.sqlite and apply schema.

        Args:
            db_path: Override path (defaults to config.DB_PATH).
        """
        self._path = db_path or config.DB_PATH
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = self._open_connection()
        self._init_schema()

    def _open_connection(self) -> sqlite3.Connection:
        """Connect to SQLite with row factory."""
        try:
            conn = sqlite3.connect(self._path, timeout=10)
            conn.row_factory = sqlite3.Row
            return conn
        except sqlite3.Error as exc:
            raise RuntimeError(f"Could not open database {self._path}: {exc}") from exc

    def _init_schema(self) -> None:
        """Create tables or rebuild after corrupt DB backup."""
        try:
            self._conn.executescript(_SCHEMA_SQL)
            self._conn.commit()
        except sqlite3.Error as exc:
            backup = self._path.with_suffix(".sqlite.bak")
            try:
                if self._path.exists():
                    self._path.replace(backup)
                print(f"Database error — backed up to {backup}: {exc}")
            except OSError:
                print(f"Database corrupt and backup failed: {exc}")
            self._conn = self._open_connection()
            self._conn.executescript(_SCHEMA_SQL)
            self._conn.commit()

    def start_session(self) -> str:
        """
        Insert a new session row from current config.

        Returns:
            New session UUID string.
        """
        session_id = str(uuid.uuid4())
        cfg = config.get_config()

        def _insert() -> None:
            self._conn.execute(
                """
                INSERT INTO sessions (
                    session_id, started_at, hostname,
                    vision_model, solver_model, graph_model
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    _utc_now(),
                    socket.gethostname(),
                    cfg["vision_model"],
                    cfg["solver_model"],
                    cfg["graph_model"],
                ),
            )
            self._conn.commit()

        _retry_db(_insert)
        return session_id

    def end_session(self, session_id: str) -> None:
        """
        Mark session ended_at timestamp.

        Args:
            session_id: Active session UUID.
        """

        def _end() -> None:
            self._conn.execute(
                "UPDATE sessions SET ended_at = ? WHERE session_id = ?",
                (_utc_now(), session_id),
            )
            self._conn.commit()

        _retry_db(_end)

    def compute_phash(self, image: Image.Image) -> str:
        """
        Compute perceptual hash hex for an image.

        Args:
            image: Question-region PIL image.

        Returns:
            Hex string of phash.
        """
        return str(imagehash.phash(image))

    def hamming_distance(self, hash_a: str, hash_b: str) -> int:
        """
        Hamming distance between two phash hex strings.

        Args:
            hash_a: First phash hex.
            hash_b: Second phash hex.

        Returns:
            Integer distance.
        """
        return imagehash.hex_to_hash(hash_a) - imagehash.hex_to_hash(hash_b)

    def find_similar_question(
        self,
        image: Image.Image,
        max_distance: int | None = None,
    ) -> dict[str, Any] | None:
        """
        Find nearest stored question by phash similarity.

        Args:
            image: Current question-region image.
            max_distance: Hamming threshold (default from config).

        Returns:
            Dict with question + answer fields, or None.
        """
        limit = max_distance if max_distance is not None else config.IMAGE_HASH_MATCH_THRESHOLD
        target = imagehash.hex_to_hash(self.compute_phash(image))
        rows = self._conn.execute(
            """
            SELECT q.question_id, q.phash, q.question_text, q.answer_type, q.question_type,
                   a.answer_value, a.answer_working, a.verification_working,
                   a.recheck_passed, a.original_answer, a.confidence, a.answer_unit
            FROM questions q
            JOIN answers a ON a.question_id = q.question_id
            ORDER BY q.created_at DESC
            """
        ).fetchall()

        best: dict[str, Any] | None = None
        best_dist = limit + 1
        for row in rows:
            try:
                dist = target - imagehash.hex_to_hash(row["phash"])
            except Exception:
                continue
            if dist <= limit and dist < best_dist:
                best_dist = dist
                best = dict(row)
                best["hamming_distance"] = dist
        return best

    def recall_for_verification(self, image: Image.Image) -> dict[str, Any] | None:
        """
        Recall a prior verified answer for a visually similar question.

        Args:
            image: Current question-region screenshot.

        Returns:
            Answer package dict or None.
        """
        hit = self.find_similar_question(image)
        if not hit:
            return None
        if not hit.get("recheck_passed", 0):
            return None
        return hit

    def get_cached_answer(self, question_hash: str) -> dict[str, Any] | None:
        """
        Exact phash match for a previously stored verified answer.

        Args:
            question_hash: phash hex string.

        Returns:
            Answer dict with verified=True, or None.
        """
        row = self._conn.execute(
            """
            SELECT a.answer_value, a.answer_working, a.verification_working,
                   a.confidence, a.recheck_passed, a.original_answer, a.answer_unit
            FROM questions q
            JOIN answers a ON a.question_id = q.question_id
            WHERE q.phash = ? AND a.recheck_passed = 1
            ORDER BY a.submitted_at DESC
            LIMIT 1
            """,
            (question_hash,),
        ).fetchone()
        if not row:
            return None
        data = dict(row)
        data["verified"] = True
        return data

    def store_question_answer(
        self,
        session_id: str,
        question_image: Image.Image,
        vision_json: dict[str, Any],
        solve_result: Any,
        screenshot_path: Path,
        question_type: str = "standard",
        accepted: bool | None = None,
    ) -> int:
        """
        Persist question + verified answer with recheck metadata.

        Args:
            session_id: Active session UUID.
            question_image: Cropped question image for phash.
            vision_json: Vision model output.
            solve_result: math_solver.SolveResult instance.
            screenshot_path: Path to full screenshot PNG.
            question_type: 'standard' or 'graph'.
            accepted: Automation success flag if known.

        Returns:
            question_id integer.
        """
        phash = self.compute_phash(question_image)
        payload = _solve_result_blob(solve_result)

        def _insert() -> int:
            cur = self._conn.execute(
                """
                INSERT INTO questions (
                    session_id, phash, question_text, answer_type, question_type,
                    vision_json, screenshot_path, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id, phash) DO UPDATE SET
                    question_text = excluded.question_text,
                    vision_json = excluded.vision_json,
                    screenshot_path = excluded.screenshot_path
                """,
                (
                    session_id,
                    phash,
                    vision_json.get("question_text"),
                    vision_json.get("answer_type"),
                    question_type,
                    json.dumps(vision_json),
                    str(screenshot_path),
                    _utc_now(),
                ),
            )
            qid = cur.lastrowid
            if qid == 0:
                row = self._conn.execute(
                    "SELECT question_id FROM questions WHERE session_id = ? AND phash = ?",
                    (session_id, phash),
                ).fetchone()
                qid = int(row["question_id"])

            self._conn.execute(
                """
                INSERT INTO answers (
                    question_id, answer_value, answer_working, answer_unit,
                    verification_working, recheck_passed, original_answer,
                    confidence, solve_json, submitted_at, accepted
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(question_id) DO UPDATE SET
                    answer_value = excluded.answer_value,
                    answer_working = excluded.answer_working,
                    verification_working = excluded.verification_working,
                    recheck_passed = excluded.recheck_passed,
                    original_answer = excluded.original_answer,
                    confidence = excluded.confidence,
                    solve_json = excluded.solve_json,
                    submitted_at = excluded.submitted_at,
                    accepted = excluded.accepted
                """,
                (
                    qid,
                    solve_result.answer,
                    solve_result.working,
                    solve_result.answer_unit,
                    solve_result.verification_working,
                    1 if solve_result.recheck_passed else 0,
                    solve_result.original_answer,
                    solve_result.confidence,
                    payload,
                    _utc_now(),
                    None if accepted is None else (1 if accepted else 0),
                ),
            )
            self._conn.commit()
            return int(qid)

        return int(_retry_db(_insert))

    def update_answer_accepted(self, question_id: int, accepted: bool) -> None:
        """
        Set automation accepted flag for a stored answer.

        Args:
            question_id: questions.question_id
            accepted: Whether UI automation reported success.
        """

        def _upd() -> None:
            self._conn.execute(
                "UPDATE answers SET accepted = ? WHERE question_id = ?",
                (1 if accepted else 0, question_id),
            )
            self._conn.commit()

        _retry_db(_upd)

    def export_session_csv(self, session_id: str, output_path: Path | None = None) -> Path:
        """
        Export session Q&A rows to CSV.

        Args:
            session_id: Session UUID.
            output_path: Optional file path (default under exports/).

        Returns:
            Path to written CSV file.
        """
        out = output_path or (
            config.EXPORTS_DIR / f"session_{session_id[:8]}.csv"
        )
        out.parent.mkdir(parents=True, exist_ok=True)
        rows = self._conn.execute(
            """
            SELECT q.question_id, q.phash, q.question_text, q.answer_type, q.question_type,
                   a.answer_value, a.answer_working, a.verification_working,
                   a.recheck_passed, a.original_answer, a.confidence,
                   q.created_at, q.screenshot_path, a.accepted
            FROM questions q
            JOIN answers a ON a.question_id = q.question_id
            WHERE q.session_id = ?
            ORDER BY q.question_id
            """,
            (session_id,),
        ).fetchall()

        headers = [
            "question_id",
            "phash",
            "question_text",
            "answer_type",
            "question_type",
            "answer_value",
            "answer_working",
            "verification_working",
            "recheck_passed",
            "original_answer",
            "confidence",
            "created_at",
            "screenshot_path",
            "accepted",
        ]
        with out.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=headers)
            writer.writeheader()
            for row in rows:
                writer.writerow(
                    {
                        "question_id": row["question_id"],
                        "phash": row["phash"],
                        "question_text": row["question_text"],
                        "answer_type": row["answer_type"],
                        "question_type": row["question_type"],
                        "answer_value": row["answer_value"],
                        "answer_working": row["answer_working"],
                        "verification_working": row["verification_working"],
                        "recheck_passed": bool(row["recheck_passed"]),
                        "original_answer": row["original_answer"],
                        "confidence": row["confidence"],
                        "created_at": row["created_at"],
                        "screenshot_path": row["screenshot_path"],
                        "accepted": row["accepted"],
                    }
                )
        return out

    def close(self) -> None:
        """Close the database connection."""
        try:
            self._conn.close()
        except sqlite3.Error:
            pass


def _solve_result_blob(solve_result: Any) -> str:
    """Serialize SolveResult to JSON for storage."""
    return json.dumps(
        {
            "answer": solve_result.answer,
            "working": solve_result.working,
            "verification_working": solve_result.verification_working,
            "confidence": solve_result.confidence,
            "recheck_passed": solve_result.recheck_passed,
            "original_answer": solve_result.original_answer,
            "was_corrected": solve_result.was_corrected,
            "answer_unit": solve_result.answer_unit,
            "ready_for_submit": solve_result.ready_for_submit,
        }
    )


def recall_to_solve_result(hit: dict[str, Any]) -> "math_solver.SolveResult":
    """
    Build SolveResult from a memory recall / cache dict.

    Args:
        hit: Row dict from recall_for_verification or get_cached_answer.

    Returns:
        SolveResult ready for display and automation.
    """
    import math_solver

    return math_solver.SolveResult(
        answer=str(hit["answer_value"]),
        working=str(hit.get("answer_working") or ""),
        verification_working=str(hit.get("verification_working") or ""),
        confidence=float(hit.get("confidence") or 1.0),
        recheck_passed=bool(hit.get("recheck_passed", 1)),
        original_answer=hit.get("original_answer"),
        was_corrected=False,
        answer_unit=hit.get("answer_unit"),
        ready_for_submit=True,
    )
