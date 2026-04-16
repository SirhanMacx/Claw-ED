"""Persistent bot state storage backed by SQLite.

Stores Telegram bot conversation states so they survive restarts.
Used by both telegram_bot.py (teacher bot) and student_telegram_bot.py.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_BASE_DIR = Path(os.environ.get("EDUAGENT_DATA_DIR", str(Path.home() / ".eduagent")))


class BotStateStore:
    """Read/write ChatState rows to the data directory's bot_state.db."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or (_BASE_DIR / "bot_state.db")
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._ensure_table()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self._db_path))
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _ensure_table(self) -> None:
        conn = self._get_conn()
        conn.execute(
            """CREATE TABLE IF NOT EXISTS chat_states (
                chat_id INTEGER PRIMARY KEY,
                state TEXT NOT NULL DEFAULT 'idle',
                pending_topic TEXT NOT NULL DEFAULT '',
                last_lesson_id TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
            )"""
        )
        conn.commit()

    def get(self, chat_id: int) -> dict[str, Any] | None:
        """Load a chat state row, or None if not found."""
        row = self._get_conn().execute(
            "SELECT state, pending_topic, last_lesson_id, updated_at "
            "FROM chat_states WHERE chat_id = ?",
            (chat_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "state": row["state"],
            "pending_topic": row["pending_topic"],
            "last_lesson_id": row["last_lesson_id"],
            "updated_at": row["updated_at"],
        }

    def save(self, chat_id: int, *, state: str, pending_topic: str = "", last_lesson_id: str = "") -> None:
        """Upsert a chat state row."""
        now = datetime.now(UTC).isoformat()
        self._get_conn().execute(
            """INSERT INTO chat_states (chat_id, state, pending_topic, last_lesson_id, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                state = excluded.state,
                pending_topic = excluded.pending_topic,
                last_lesson_id = excluded.last_lesson_id,
                updated_at = excluded.updated_at""",
            (chat_id, state, pending_topic, last_lesson_id, now),
        )
        self._get_conn().commit()

    def delete(self, chat_id: int) -> None:
        """Remove a chat state row."""
        self._get_conn().execute(
            "DELETE FROM chat_states WHERE chat_id = ?", (chat_id,)
        )
        self._get_conn().commit()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None


class StudentProgressStore:
    """Read/write student progress rows to ~/.eduagent/bot_state.db."""

    def __init__(self, db_path: Path | None = None) -> None:
        if db_path is None:
            from clawed.paths import data_dir
            db_path = data_dir() / "bot_state.db"
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._ensure_table()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self._db_path))
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _ensure_table(self) -> None:
        conn = self._get_conn()
        conn.execute(
            """CREATE TABLE IF NOT EXISTS student_progress (
                id TEXT PRIMARY KEY,
                student_id TEXT NOT NULL,
                class_code TEXT NOT NULL,
                student_name TEXT NOT NULL DEFAULT '',
                topics_asked_json TEXT NOT NULL DEFAULT '{}',
                total_questions INTEGER NOT NULL DEFAULT 0,
                last_active TEXT NOT NULL DEFAULT '',
                struggle_topics_json TEXT NOT NULL DEFAULT '[]'
            )"""
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_sp_class ON student_progress(class_code)"
        )
        conn.commit()

    def get(self, student_id: str, class_code: str) -> dict[str, Any] | None:
        """Load a student progress row."""
        import json
        row_id = f"{student_id}:{class_code}"
        row = self._get_conn().execute(
            "SELECT * FROM student_progress WHERE id = ?", (row_id,)
        ).fetchone()
        if row is None:
            return None
        return {
            "student_id": row["student_id"],
            "class_code": row["class_code"],
            "student_name": row["student_name"],
            "topics_asked": json.loads(row["topics_asked_json"]),
            "total_questions": row["total_questions"],
            "last_active": row["last_active"],
            "struggle_topics": json.loads(row["struggle_topics_json"]),
        }

    def save(
        self,
        student_id: str,
        class_code: str,
        *,
        student_name: str = "",
        topics_asked: dict[str, Any] | None = None,
        total_questions: int = 0,
        last_active: str = "",
        struggle_topics: list[str] | None = None,
    ) -> None:
        """Upsert a student progress row."""
        import json
        row_id = f"{student_id}:{class_code}"
        topics_json = json.dumps(topics_asked or {})
        struggle_json = json.dumps(struggle_topics or [])
        self._get_conn().execute(
            """INSERT INTO student_progress
            (id, student_id, class_code, student_name, topics_asked_json,
             total_questions, last_active, struggle_topics_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                student_name = excluded.student_name,
                topics_asked_json = excluded.topics_asked_json,
                total_questions = excluded.total_questions,
                last_active = excluded.last_active,
                struggle_topics_json = excluded.struggle_topics_json""",
            (row_id, student_id, class_code, student_name,
             topics_json, total_questions, last_active, struggle_json),
        )
        self._get_conn().commit()

    def get_class_progress(self, class_code: str) -> list[dict[str, Any]]:
        """Get all student progress entries for a class."""
        import json
        rows = self._get_conn().execute(
            "SELECT * FROM student_progress WHERE class_code = ? ORDER BY total_questions DESC",
            (class_code,),
        ).fetchall()
        return [
            {
                "student_id": r["student_id"],
                "class_code": r["class_code"],
                "student_name": r["student_name"],
                "topics_asked": json.loads(r["topics_asked_json"]),
                "total_questions": r["total_questions"],
                "last_active": r["last_active"],
                "struggle_topics": json.loads(r["struggle_topics_json"]),
            }
            for r in rows
        ]

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None


class StudentBotStateStore:
    """Read/write student session rows to ~/.eduagent/bot_state.db."""

    def __init__(self, db_path: Path | None = None) -> None:
        if db_path is None:
            from clawed.paths import data_dir
            db_path = data_dir() / "bot_state.db"
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._ensure_table()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self._db_path))
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _ensure_table(self) -> None:
        conn = self._get_conn()
        conn.execute(
            """CREATE TABLE IF NOT EXISTS student_bot_sessions (
                chat_id INTEGER PRIMARY KEY,
                class_code TEXT NOT NULL DEFAULT '',
                student_id TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
            )"""
        )
        conn.commit()

    def get(self, chat_id: int) -> dict[str, str] | None:
        """Load a student session row, or None if not found."""
        row = self._get_conn().execute(
            "SELECT class_code, student_id, updated_at "
            "FROM student_bot_sessions WHERE chat_id = ?",
            (chat_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "class_code": row["class_code"],
            "student_id": row["student_id"],
            "updated_at": row["updated_at"],
        }

    def save(self, chat_id: int, *, class_code: str = "", student_id: str = "") -> None:
        """Upsert a student session row."""
        now = datetime.now(UTC).isoformat()
        self._get_conn().execute(
            """INSERT INTO student_bot_sessions (chat_id, class_code, student_id, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                class_code = excluded.class_code,
                student_id = excluded.student_id,
                updated_at = excluded.updated_at""",
            (chat_id, class_code, student_id, now),
        )
        self._get_conn().commit()

    def delete(self, chat_id: int) -> None:
        """Remove a student session row."""
        self._get_conn().execute(
            "DELETE FROM student_bot_sessions WHERE chat_id = ?", (chat_id,)
        )
        self._get_conn().commit()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
