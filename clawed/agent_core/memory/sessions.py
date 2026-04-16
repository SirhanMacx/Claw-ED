"""Cross-transport session store.

Tracks conversation turns with transport metadata so Ed can see
what was said on CLI vs Telegram and reference it naturally.

Separate from state.py's TeacherSession (which stores persona,
config, units). This module only handles conversation turns.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_initialized = False


def _db_path() -> Path:
    data_dir = os.environ.get(
        "EDUAGENT_DATA_DIR", str(Path.home() / ".eduagent")
    )
    return Path(data_dir) / "memory" / "sessions.db"


def _get_conn() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_db() -> None:
    global _initialized
    if _initialized:
        return
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_id TEXT NOT NULL,
                transport TEXT NOT NULL DEFAULT 'cli',
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_sessions_teacher_ts
            ON sessions(teacher_id, timestamp DESC)
        """)
    _initialized = True


def save_turn(
    teacher_id: str,
    role: str,
    content: str,
    transport: str = "cli",
) -> None:
    """Save a single conversation turn with transport metadata."""
    _ensure_db()
    with _get_conn() as conn:
        conn.execute(
            "INSERT INTO sessions (teacher_id, transport, role, content, timestamp)"
            " VALUES (?, ?, ?, ?, ?)",
            (
                teacher_id,
                transport,
                role,
                content[:4000],
                datetime.now(UTC).isoformat(),
            ),
        )


def load_recent(teacher_id: str, limit: int = 10) -> list[dict[str, Any]]:
    """Load most recent conversation turns, newest last."""
    _ensure_db()
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT transport, role, content, timestamp"
            " FROM sessions"
            " WHERE teacher_id = ?"
            " ORDER BY timestamp DESC LIMIT ?",
            (teacher_id, limit),
        ).fetchall()
    # Reverse so oldest first (chronological)
    return [dict(r) for r in reversed(rows)]


def load_recent_for_llm(teacher_id: str, limit: int = 10) -> list[dict[str, Any]]:
    """Load recent turns formatted for LLM message history.

    Returns list of {"role": "user"|"assistant", "content": "..."}.
    """
    turns = load_recent(teacher_id, limit)
    return [
        {"role": t["role"], "content": t["content"]}
        for t in turns
    ]


def format_for_prompt(teacher_id: str, limit: int = 10) -> str:
    """Format recent conversation for system prompt injection.

    Shows transport origin so Ed can reference cross-transport context:
    'Earlier on Telegram you asked about the Civil War...'
    """
    turns = load_recent(teacher_id, limit)
    if not turns:
        return ""

    lines = []
    for turn in turns:
        transport = turn["transport"]
        role = turn["role"]
        content = turn["content"]
        tag = f" (via {transport})" if transport != "cli" else ""
        if role == "user":
            lines.append(f"Teacher{tag}: {content[:800]}")
        else:
            lines.append(f"Ed: {content[:800]}")

    return "\n".join(lines)


def reset_db() -> None:
    """Reset the initialized flag. For testing only."""
    global _initialized
    _initialized = False
