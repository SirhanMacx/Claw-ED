"""Layer 3: Episodic memory — embedding-based semantic search over interactions."""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from clawed.agent_core.memory.curriculum_kb import _blob_to_embed, _embed_to_blob
from clawed.agent_core.memory.embeddings import get_embedder

logger = logging.getLogger(__name__)

def _default_db() -> Path:
    from clawed.paths import episodes_db_path
    return episodes_db_path()

_DEFAULT_DB = None  # resolved lazily via _default_db()


class EpisodicMemory:
    """Stores and recalls teacher interaction episodes with semantic search."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or _default_db()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._embedder = get_embedder()
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS episodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    teacher_id TEXT NOT NULL,
                    text TEXT NOT NULL,
                    embedding TEXT NOT NULL,
                    metadata TEXT DEFAULT '{}',
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_episodes_teacher ON episodes(teacher_id)"
            )

    def store(
        self,
        teacher_id: str,
        text: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Store an episode with its embedding as compact binary."""
        embedding = self._embedder.embed(text)
        blob = _embed_to_blob(embedding)
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "INSERT INTO episodes (teacher_id, text, embedding, metadata, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    teacher_id,
                    text,
                    blob,
                    json.dumps(metadata or {}),
                    datetime.now().isoformat(),
                ),
            )

    def recall(
        self,
        teacher_id: str,
        query: str,
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """Recall the most relevant episodes using semantic similarity."""
        query_embedding = self._embedder.embed(query)

        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT text, embedding, metadata, created_at "
                "FROM episodes WHERE teacher_id = ? "
                "AND created_at > date('now', '-90 days') "
                "ORDER BY created_at DESC LIMIT 200",
                (teacher_id,),
            ).fetchall()

        if not rows:
            return []

        scored = []
        for row in rows:
            raw = row["embedding"]
            stored_embedding = (
                _blob_to_embed(raw) if isinstance(raw, bytes)
                else json.loads(raw)
            )
            sim = self._embedder.cosine_similarity(query_embedding, stored_embedding)
            scored.append({
                "text": row["text"],
                "metadata": json.loads(row["metadata"]),
                "created_at": row["created_at"],
                "similarity": sim,
            })

        scored.sort(key=lambda x: x["similarity"], reverse=True)
        return scored[:top_k]

    def get_latest_episode(self, teacher_id: str) -> dict[str, Any] | None:
        """Return the most recent episode for a teacher, or None."""
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT text, metadata, created_at FROM episodes "
                "WHERE teacher_id = ? ORDER BY created_at DESC LIMIT 1",
                (teacher_id,),
            ).fetchone()
        if not row:
            return None
        return {
            "text": row["text"],
            "metadata": json.loads(row["metadata"]),
            "created_at": row["created_at"],
        }

    def count_episodes(self, teacher_id: str) -> int:
        """Return the total number of episodes stored for a teacher."""
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM episodes WHERE teacher_id = ?",
                (teacher_id,),
            ).fetchone()
        return row[0] if row else 0

    def get_all_episodes(
        self,
        teacher_id: str,
        limit: int = 500,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Return episodes in chronological order (oldest first)."""
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT text, metadata, created_at FROM episodes "
                "WHERE teacher_id = ? ORDER BY created_at ASC "
                "LIMIT ? OFFSET ?",
                (teacher_id, limit, offset),
            ).fetchall()
        return [
            {
                "text": row["text"],
                "metadata": json.loads(row["metadata"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]
