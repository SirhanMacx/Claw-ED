"""Conversation state management for teacher sessions.

Each teacher (identified by their Telegram user ID or web session)
has a persistent session that remembers:
- Their persona (teaching style, preferences)
- What they're currently working on
- Recent conversation context
- Configuration

This is what makes the bot feel like a real assistant — it knows
what you were doing last time and picks up where you left off.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from clawed.models import DailyLesson, TeacherPersona, UnitPlan

logger = logging.getLogger(__name__)

# Pattern for validating migration identifiers: alphanumeric, underscore,
# space, parentheses, single-quotes, and periods only.
_SAFE_SQL_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_ ()'.\[\]]+$")

# Default data directory
def _default_data_dir():
    from clawed.paths import data_dir
    return data_dir()

DEFAULT_DATA_DIR = None  # resolved lazily via _default_data_dir()


def _db_path() -> Path:
    dd = _default_data_dir()
    dd.mkdir(parents=True, exist_ok=True)
    return dd / "state.db"


@contextmanager
def _get_conn():
    """Context manager that yields a SQLite connection.

    Commits on success, rolls back on exception, and always closes.
    """
    conn = sqlite3.connect(str(_db_path()))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Initialize the database schema."""
    with _get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS teacher_sessions (
                teacher_id TEXT PRIMARY KEY,
                name TEXT,
                persona_json TEXT,
                config_json TEXT,
                current_unit_json TEXT,
                current_lesson_json TEXT,
                context_json TEXT DEFAULT '[]',
                school_id TEXT,
                last_activity TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS generated_units (
                id TEXT PRIMARY KEY,
                teacher_id TEXT NOT NULL,
                title TEXT,
                subject TEXT,
                grade_level TEXT,
                topic TEXT,
                unit_json TEXT NOT NULL,
                rating INTEGER,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS generated_lessons (
                id TEXT PRIMARY KEY,
                unit_id TEXT,
                teacher_id TEXT NOT NULL,
                lesson_number INTEGER,
                title TEXT,
                lesson_json TEXT NOT NULL,
                materials_json TEXT,
                quality_score_json TEXT,
                rating INTEGER,
                edit_count INTEGER DEFAULT 0,
                share_token TEXT UNIQUE,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS feedback (
                id TEXT PRIMARY KEY,
                lesson_id TEXT,
                teacher_id TEXT,
                rating INTEGER,
                notes TEXT,
                sections_edited TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS prompt_versions (
                id TEXT PRIMARY KEY,
                prompt_type TEXT NOT NULL,
                version INTEGER NOT NULL,
                prompt_text TEXT NOT NULL,
                avg_rating REAL DEFAULT 0.0,
                usage_count INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS classes (
                class_code TEXT PRIMARY KEY,
                teacher_id TEXT NOT NULL,
                name TEXT DEFAULT '',
                topic TEXT DEFAULT '',
                allowed_lesson_ids TEXT DEFAULT '[]',
                expires_at TEXT,
                active_lesson_id TEXT,
                active_lesson_json TEXT,
                hint_mode INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS student_sessions (
                id TEXT PRIMARY KEY,
                student_id TEXT NOT NULL,
                class_code TEXT NOT NULL,
                message_count INTEGER DEFAULT 0,
                last_activity TEXT
            );

            CREATE TABLE IF NOT EXISTS student_questions (
                id TEXT PRIMARY KEY,
                student_id TEXT,
                class_code TEXT,
                question TEXT,
                answer TEXT,
                lesson_topic TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS registered_students (
                id TEXT PRIMARY KEY,
                student_id TEXT NOT NULL,
                class_code TEXT NOT NULL,
                display_name TEXT,
                registered_at TEXT DEFAULT (datetime('now')),
                UNIQUE(student_id, class_code)
            );
        """)
        # Migrate: add new columns to classes table if missing
        _migrate_classes(conn)


def _migrate_classes(conn: sqlite3.Connection) -> None:
    """Add new columns to the classes table for existing databases."""
    existing = {
        row[1] for row in conn.execute("PRAGMA table_info(classes)").fetchall()
    }
    migrations = [
        ("name", "TEXT DEFAULT ''"),
        ("topic", "TEXT DEFAULT ''"),
        ("allowed_lesson_ids", "TEXT DEFAULT '[]'"),
        ("expires_at", "TEXT"),
    ]
    for col, typedef in migrations:
        if col not in existing:
            if not _SAFE_SQL_IDENTIFIER_RE.match(col):
                raise ValueError(f"Unsafe migration column name: {col!r}")
            if not _SAFE_SQL_IDENTIFIER_RE.match(typedef):
                raise ValueError(f"Unsafe migration type definition: {typedef!r}")
            conn.execute(f"ALTER TABLE classes ADD COLUMN {col} {typedef}")
    conn.commit()


class TeacherSession:
    """A teacher's persistent conversation session."""

    def __init__(
        self,
        teacher_id: str,
        name: Optional[str] = None,
        persona: Optional[TeacherPersona] = None,
        config: Optional[dict] = None,
        current_unit: Optional[UnitPlan] = None,
        current_lesson: Optional[DailyLesson] = None,
        context: Optional[list] = None,
        school_id: Optional[str] = None,
    ):
        self.teacher_id = teacher_id
        self.name = name
        self.persona = persona
        self.config = config or {}
        self.current_unit = current_unit
        self.current_lesson = current_lesson
        self.context: list[dict] = context or []  # Recent conversation turns
        self.last_activity = datetime.now(timezone.utc)
        self.school_id = school_id

    @classmethod
    def load(cls, teacher_id: str) -> "TeacherSession":
        """Load a session from DB, or create a new one."""
        init_db()
        with _get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM teacher_sessions WHERE teacher_id = ?",
                (teacher_id,),
            ).fetchone()

        if not row:
            return cls(teacher_id=teacher_id)

        persona = None
        if row["persona_json"]:
            try:
                persona = TeacherPersona.model_validate_json(row["persona_json"])
            except (json.JSONDecodeError, ValueError, TypeError, KeyError) as exc:
                logger.warning("Failed to parse persona_json for %s: %s", teacher_id, exc)

        current_unit = None
        if row["current_unit_json"]:
            try:
                current_unit = UnitPlan.model_validate_json(row["current_unit_json"])
            except (json.JSONDecodeError, ValueError, TypeError, KeyError) as exc:
                logger.warning("Failed to parse current_unit_json for %s: %s", teacher_id, exc)

        current_lesson = None
        if row["current_lesson_json"]:
            try:
                current_lesson = DailyLesson.model_validate_json(row["current_lesson_json"])
            except (json.JSONDecodeError, ValueError, TypeError, KeyError) as exc:
                logger.warning("Failed to parse current_lesson_json for %s: %s", teacher_id, exc)

        config = {}
        if row["config_json"]:
            try:
                config = json.loads(row["config_json"])
            except (json.JSONDecodeError, ValueError, TypeError) as exc:
                logger.warning("Failed to parse config_json for %s: %s", teacher_id, exc)

        context = []
        if row["context_json"]:
            try:
                context = json.loads(row["context_json"])
            except (json.JSONDecodeError, ValueError, TypeError) as exc:
                logger.warning("Failed to parse context_json for %s: %s", teacher_id, exc)

        school_id = None
        try:
            school_id = row["school_id"]
        except (IndexError, KeyError):
            pass

        return cls(
            teacher_id=teacher_id,
            name=row["name"],
            persona=persona,
            config=config,
            current_unit=current_unit,
            current_lesson=current_lesson,
            context=context,
            school_id=school_id,
        )

    def save(self) -> None:
        """Persist this session to DB."""
        init_db()
        with _get_conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO teacher_sessions
                    (teacher_id, name, persona_json, config_json,
                     current_unit_json, current_lesson_json, context_json,
                     school_id, last_activity)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self.teacher_id,
                    self.name,
                    self.persona.model_dump_json() if self.persona else None,
                    json.dumps(self.config),
                    self.current_unit.model_dump_json() if self.current_unit else None,
                    self.current_lesson.model_dump_json() if self.current_lesson else None,
                    json.dumps(self.context[-20:]),  # Keep last 20 turns
                    self.school_id,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def add_context(self, role: str, content: str) -> None:
        """Add a turn to the conversation context."""
        self.context.append({
            "role": role,
            "content": content[:2000],  # Cap per-turn length
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def save_unit(self, unit: UnitPlan) -> str:
        """Save a generated unit, return its ID."""
        unit_id = str(uuid.uuid4())
        self.current_unit = unit
        init_db()
        with _get_conn() as conn:
            conn.execute(
                """
                INSERT INTO generated_units (id, teacher_id, title, subject, grade_level, topic, unit_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    unit_id, self.teacher_id, unit.title, unit.subject,
                    unit.grade_level, unit.topic, unit.model_dump_json(),
                ),
            )
        self.save()
        return unit_id

    def save_lesson(self, lesson: DailyLesson, unit_id: Optional[str] = None) -> str:
        """Save a generated lesson, return its ID."""
        lesson_id = str(uuid.uuid4())
        share_token = str(uuid.uuid4())[:8]  # Short share token
        self.current_lesson = lesson
        init_db()
        with _get_conn() as conn:
            conn.execute(
                """
                INSERT INTO generated_lessons (id, unit_id, teacher_id, lesson_number, title, lesson_json, share_token)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    lesson_id, unit_id, self.teacher_id,
                    lesson.lesson_number, lesson.title,
                    lesson.model_dump_json(), share_token,
                ),
            )
        self.save()
        return lesson_id

    def get_recent_units(self, limit: int = 5) -> list[dict]:
        """Get the teacher's most recent generated units."""
        init_db()
        with _get_conn() as conn:
            rows = conn.execute(
                "SELECT id, title, subject, grade_level, topic, created_at"
                " FROM generated_units"
                " WHERE teacher_id = ? ORDER BY created_at DESC LIMIT ?",
                (self.teacher_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    @property
    def is_new(self) -> bool:
        """True if this teacher hasn't set up their persona yet."""
        return self.persona is None

    @property
    def has_materials(self) -> bool:
        """True if we have curriculum materials to learn from."""
        return bool(self.config.get("materials_path") or self.config.get("drive_url"))

    def get_context_for_llm(self, max_turns: int = 5) -> list[dict]:
        """Get recent conversation context formatted for LLM input."""
        return [
            {"role": turn["role"], "content": turn["content"]}
            for turn in self.context[-max_turns:]
        ]
