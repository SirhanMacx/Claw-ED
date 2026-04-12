"""Session compression — compress old conversation turns into structured summaries.

Keeps the last KEEP_RECENT turns verbatim for immediate context. Older turns
are compressed in batches of COMPRESS_BATCH into structured summaries with
semantic embeddings for future recall. Original turns are deleted after
compression to prevent unbounded DB growth.

Inspired by MemPalace's AAAK compression concept, adapted for teaching sessions.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

KEEP_RECENT = 20
COMPRESS_BATCH = 20
COMPRESS_THRESHOLD = 40


def _db_path() -> Path:
    data_dir = os.environ.get(
        "EDUAGENT_DATA_DIR", str(Path.home() / ".eduagent")
    )
    return Path(data_dir) / "memory" / "sessions.db"


def _ensure_summaries_table() -> None:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(path)) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS session_summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_id TEXT NOT NULL,
                session_date TEXT NOT NULL,
                turn_count INTEGER NOT NULL,
                topics TEXT NOT NULL DEFAULT '[]',
                materials_generated TEXT DEFAULT '[]',
                decisions TEXT DEFAULT '[]',
                feedback TEXT DEFAULT '[]',
                compressed_text TEXT NOT NULL,
                embedding BLOB,
                original_turn_ids TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_summaries_teacher
                ON session_summaries(teacher_id);
            CREATE INDEX IF NOT EXISTS idx_summaries_date
                ON session_summaries(teacher_id, session_date DESC);
        """)


# ── Structured field extraction (regex, no LLM) ─────────────────────

_TOPIC_INDICATORS = re.compile(
    r"(?:lesson|unit|topic|about|teach|cover(?:ing)?|"
    r"make\s+(?:a|me)\s+lesson)\s+(?:on|about|for)?\s*(.+?)(?:\.|$)",
    re.IGNORECASE,
)

_MATERIAL_INDICATORS = re.compile(
    r"(?:generated?|created?|saved?|exported?|built)\s*:?\s*(.+?\.(?:docx|pptx|pdf|html|mp4))",
    re.IGNORECASE,
)

_DECISION_INDICATORS = re.compile(
    r"(?:prefer|want|don'?t\s+like|always|never|switch|use|chose|"
    r"rather|instead|please\s+(?:don'?t|always))\s+(.+?)(?:\.|$)",
    re.IGNORECASE,
)

_FEEDBACK_INDICATORS = re.compile(
    r"(?:rated?\s*\d|great|terrible|perfect|awful|good|bad|love|hate|"
    r"excellent|poor|amazing|horrible|better|worse)",
    re.IGNORECASE,
)


def extract_structured_fields(turns: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Extract structured information from conversation turns.

    Returns {topics, materials_generated, decisions, feedback}
    """
    topics: list[str] = []
    materials: list[str] = []
    decisions: list[str] = []
    feedback: list[str] = []

    for turn in turns:
        content = turn.get("content", "")
        role = turn.get("role", "")

        # Topics from user messages
        if role == "user":
            for m in _TOPIC_INDICATORS.finditer(content):
                topic = m.group(1).strip()[:80]
                if topic and topic not in topics:
                    topics.append(topic)

            # Decisions from user preferences
            for m in _DECISION_INDICATORS.finditer(content):
                dec = m.group(0).strip()[:100]
                if dec and dec not in decisions:
                    decisions.append(dec)

            # Feedback from user messages
            if _FEEDBACK_INDICATORS.search(content):
                snippet = content[:80].strip()
                if snippet and snippet not in feedback:
                    feedback.append(snippet)

        # Materials from assistant messages
        if role == "assistant":
            for m in _MATERIAL_INDICATORS.finditer(content):
                mat = m.group(1).strip()[:100]
                if mat and mat not in materials:
                    materials.append(mat)

    return {
        "topics": topics[:10],
        "materials_generated": materials[:10],
        "decisions": decisions[:5],
        "feedback": feedback[:5],
    }


def _heuristic_summary(turns: list[dict[str, Any]], fields: dict[str, list[str]]) -> str:
    """Build a summary string from structured fields (no LLM)."""
    parts = [f"Session with {len(turns)} turns"]

    if fields["topics"]:
        parts.append(f"covering {', '.join(fields['topics'][:3])}")

    if fields["materials_generated"]:
        parts.append(f"Generated: {', '.join(fields['materials_generated'][:3])}")

    if fields["decisions"]:
        parts.append(f"Preferences noted: {fields['decisions'][0]}")

    if fields["feedback"]:
        parts.append("Teacher gave feedback")

    return ". ".join(parts) + "."


# ── Core compression ─────────────────────────────────────────────────

def compress_old_sessions(teacher_id: str, keep_recent: int = KEEP_RECENT) -> int:
    """Compress oldest conversation turns into a structured summary.

    Returns number of turns compressed (0 if nothing to compress).
    """
    _ensure_summaries_table()
    db = _db_path()

    with sqlite3.connect(str(db)) as conn:
        conn.row_factory = sqlite3.Row

        # Count total turns
        total = conn.execute(
            "SELECT COUNT(*) FROM sessions WHERE teacher_id = ?",
            (teacher_id,),
        ).fetchone()[0]

        if total <= COMPRESS_THRESHOLD:
            return 0

        # How many to compress: everything beyond keep_recent
        to_compress = total - keep_recent
        if to_compress < COMPRESS_BATCH:
            return 0

        # Get the oldest batch
        batch_size = min(to_compress, COMPRESS_BATCH)
        rows = conn.execute(
            "SELECT id, role, content, timestamp, transport "
            "FROM sessions WHERE teacher_id = ? "
            "ORDER BY timestamp ASC LIMIT ?",
            (teacher_id, batch_size),
        ).fetchall()

    if not rows:
        return 0

    turns = [dict(r) for r in rows]
    turn_ids = [t["id"] for t in turns]

    # Extract structured fields
    fields = extract_structured_fields(turns)

    # Build summary
    summary_text = _heuristic_summary(turns, fields)

    # Embed the summary for semantic search
    embedding_blob = None
    try:
        import struct

        from clawed.agent_core.memory.embeddings import get_embedder
        vec = get_embedder().embed(summary_text)
        embedding_blob = struct.pack(f"<{len(vec)}f", *vec)
    except Exception:
        pass

    # Determine session date from the turns
    first_ts = turns[0].get("timestamp", "")
    session_date = first_ts[:10] if first_ts else datetime.now(timezone.utc).isoformat()[:10]
    now = datetime.now(timezone.utc).isoformat()

    # Write summary and delete originals in a single transaction
    with sqlite3.connect(str(db)) as conn:
        conn.execute(
            "INSERT INTO session_summaries "
            "(teacher_id, session_date, turn_count, topics, "
            "materials_generated, decisions, feedback, "
            "compressed_text, embedding, original_turn_ids, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                teacher_id, session_date, len(turns),
                json.dumps(fields["topics"]),
                json.dumps(fields["materials_generated"]),
                json.dumps(fields["decisions"]),
                json.dumps(fields["feedback"]),
                summary_text, embedding_blob,
                json.dumps(turn_ids), now,
            ),
        )

        # Delete the compressed turns
        placeholders = ",".join("?" * len(turn_ids))
        conn.execute(
            f"DELETE FROM sessions WHERE id IN ({placeholders})",
            turn_ids,
        )

    logger.info(
        "Compressed %d turns for %s into summary (date: %s)",
        len(turns), teacher_id, session_date,
    )
    return len(turns)


def maybe_compress_sessions(teacher_id: str) -> int:
    """Check if compression is needed and run it. Non-blocking safe."""
    try:
        return compress_old_sessions(teacher_id)
    except Exception as e:
        logger.debug("Session compression failed: %s", e)
        return 0


# ── Search and recall ────────────────────────────────────────────────

def search_session_history(
    teacher_id: str,
    query: str,
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """Semantic search over compressed session summaries."""
    _ensure_summaries_table()

    try:
        import struct

        import numpy as np

        from clawed.agent_core.memory.embeddings import get_embedder
    except ImportError:
        return []

    embedder = get_embedder()
    query_vec = np.array(embedder.embed(query), dtype=np.float32)

    db = _db_path()
    with sqlite3.connect(str(db)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM session_summaries "
            "WHERE teacher_id = ? AND embedding IS NOT NULL "
            "ORDER BY session_date DESC LIMIT 100",
            (teacher_id,),
        ).fetchall()

    if not rows:
        return []

    summaries = []
    vecs = []
    for r in rows:
        try:
            blob = r["embedding"]
            n = len(blob) // 4
            vec = list(struct.unpack(f"<{n}f", blob))
            vecs.append(vec)
            summaries.append(dict(r))
        except Exception:
            continue

    if not vecs:
        return []

    mat = np.array(vecs, dtype=np.float32)
    q_norm = query_vec / (np.linalg.norm(query_vec) + 1e-8)
    m_norms = mat / (np.linalg.norm(mat, axis=1, keepdims=True) + 1e-8)
    sims = m_norms @ q_norm

    ranked = sorted(zip(sims, summaries, strict=False), key=lambda x: x[0], reverse=True)
    results = []
    for sim, summary in ranked[:top_k]:
        if sim < 0.15:
            break
        summary["similarity"] = float(sim)
        # Don't return the raw embedding blob
        summary.pop("embedding", None)
        results.append(summary)

    return results


def get_full_session_timeline(
    teacher_id: str,
    recent_limit: int = KEEP_RECENT,
    summary_limit: int = 20,
) -> list[dict[str, Any]]:
    """Get merged timeline of recent turns + compressed summaries."""
    _ensure_summaries_table()
    db = _db_path()

    timeline: list[dict[str, Any]] = []

    with sqlite3.connect(str(db)) as conn:
        conn.row_factory = sqlite3.Row

        # Compressed summaries (older)
        summaries = conn.execute(
            "SELECT session_date, turn_count, topics, compressed_text "
            "FROM session_summaries WHERE teacher_id = ? "
            "ORDER BY session_date DESC LIMIT ?",
            (teacher_id, summary_limit),
        ).fetchall()
        for s in reversed(summaries):
            timeline.append({
                "type": "summary",
                "date": s["session_date"],
                "turn_count": s["turn_count"],
                "topics": json.loads(s["topics"] or "[]"),
                "text": s["compressed_text"],
            })

        # Recent verbatim turns (newer)
        turns = conn.execute(
            "SELECT role, content, timestamp, transport "
            "FROM sessions WHERE teacher_id = ? "
            "ORDER BY timestamp DESC LIMIT ?",
            (teacher_id, recent_limit),
        ).fetchall()
        for t in reversed(turns):
            timeline.append({
                "type": "turn",
                "role": t["role"],
                "content": t["content"],
                "timestamp": t["timestamp"],
                "transport": t["transport"],
            })

    return timeline
