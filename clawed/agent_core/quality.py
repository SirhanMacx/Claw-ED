"""Quality tracker — Ed tracks and improves his own output quality.

Records every generation, scores it, detects patterns in teacher edits,
and updates his soul.md with learned patterns.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

logger = logging.getLogger(__name__)

_initialized = False


def _db_path() -> Path:
    data_dir = os.environ.get("EDUAGENT_DATA_DIR", str(Path.home() / ".eduagent"))
    return Path(data_dir) / "memory" / "quality.db"


@contextmanager
def _get_conn() -> Iterator[sqlite3.Connection]:
    """Open a quality DB connection with commit/rollback and guaranteed close."""
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _ensure_db() -> None:
    global _initialized
    if _initialized:
        return
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS generations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_id TEXT NOT NULL,
                generation_type TEXT NOT NULL,
                topic TEXT NOT NULL DEFAULT '',
                subject TEXT NOT NULL DEFAULT '',
                grade TEXT NOT NULL DEFAULT '',
                score_json TEXT NOT NULL DEFAULT '{}',
                teacher_rating INTEGER,
                teacher_feedback TEXT,
                was_edited INTEGER NOT NULL DEFAULT 0,
                edit_summary TEXT,
                timestamp TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_id TEXT NOT NULL,
                pattern_type TEXT NOT NULL,
                description TEXT NOT NULL,
                occurrences INTEGER NOT NULL DEFAULT 1,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                UNIQUE(teacher_id, pattern_type, description)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_gen_teacher
            ON generations(teacher_id, timestamp DESC)
        """)
    _initialized = True


def record_generation(
    teacher_id: str,
    generation_type: str,
    topic: str = "",
    subject: str = "",
    grade: str = "",
    scores: dict[str, float] | None = None,
) -> int:
    """Record a generation with optional self-evaluation scores.

    Returns the generation ID for later rating/feedback.
    """
    _ensure_db()
    with _get_conn() as conn:
        cursor = conn.execute(
            "INSERT INTO generations (teacher_id, generation_type, topic, subject, grade, score_json, timestamp)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                teacher_id,
                generation_type,
                topic,
                subject,
                grade,
                json.dumps(scores or {}),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        return cursor.lastrowid or 0


def record_rating(
    generation_id: int,
    rating: int,
    feedback: str = "",
) -> None:
    """Record a teacher's rating and feedback for a generation."""
    _ensure_db()
    with _get_conn() as conn:
        conn.execute(
            "UPDATE generations SET teacher_rating = ?, teacher_feedback = ? WHERE id = ?",
            (rating, feedback, generation_id),
        )


def record_edit(
    generation_id: int,
    edit_summary: str,
) -> None:
    """Record that the teacher edited a generation, with a summary."""
    _ensure_db()
    with _get_conn() as conn:
        conn.execute(
            "UPDATE generations SET was_edited = 1, edit_summary = ? WHERE id = ?",
            (edit_summary, generation_id),
        )


def get_rolling_average(
    teacher_id: str,
    generation_type: str | None = None,
    limit: int = 20,
) -> dict[str, float]:
    """Get rolling average scores for recent generations."""
    _ensure_db()
    query = "SELECT score_json FROM generations WHERE teacher_id = ?"
    params: list[Any] = [teacher_id]
    if generation_type:
        query += " AND generation_type = ?"
        params.append(generation_type)
    query += " AND score_json != '{}' ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)

    with _get_conn() as conn:
        rows = conn.execute(query, params).fetchall()

    if not rows:
        return {}

    # Aggregate scores
    totals: dict[str, float] = {}
    counts: dict[str, int] = {}
    for row in rows:
        try:
            scores = json.loads(row["score_json"])
            for key, val in scores.items():
                if isinstance(val, (int, float)):
                    totals[key] = totals.get(key, 0) + val
                    counts[key] = counts.get(key, 0) + 1
        except (json.JSONDecodeError, TypeError):
            continue

    return {k: totals[k] / counts[k] for k in totals if counts[k] > 0}


def get_edit_patterns(teacher_id: str, limit: int = 50) -> list[str]:
    """Get edit summaries to detect recurring patterns."""
    _ensure_db()
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT edit_summary FROM generations"
            " WHERE teacher_id = ? AND was_edited = 1 AND edit_summary IS NOT NULL"
            " ORDER BY timestamp DESC LIMIT ?",
            (teacher_id, limit),
        ).fetchall()
    return [row["edit_summary"] for row in rows]


def record_pattern(
    teacher_id: str,
    pattern_type: str,
    description: str,
) -> None:
    """Record or increment a detected pattern."""
    _ensure_db()
    now = datetime.now(timezone.utc).isoformat()
    with _get_conn() as conn:
        existing = conn.execute(
            "SELECT id, occurrences FROM patterns WHERE teacher_id = ? AND pattern_type = ? AND description = ?",
            (teacher_id, pattern_type, description),
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE patterns SET occurrences = occurrences + 1, last_seen = ? WHERE id = ?",
                (now, existing["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO patterns (teacher_id, pattern_type, description, first_seen, last_seen)"
                " VALUES (?, ?, ?, ?, ?)",
                (teacher_id, pattern_type, description, now, now),
            )


def get_patterns(teacher_id: str, min_occurrences: int = 2) -> list[dict]:
    """Get detected patterns with at least N occurrences."""
    _ensure_db()
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT pattern_type, description, occurrences, first_seen, last_seen"
            " FROM patterns WHERE teacher_id = ? AND occurrences >= ?"
            " ORDER BY occurrences DESC",
            (teacher_id, min_occurrences),
        ).fetchall()
    return [dict(r) for r in rows]


def get_stats(teacher_id: str) -> dict[str, Any]:
    """Get quality stats summary."""
    _ensure_db()
    with _get_conn() as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM generations WHERE teacher_id = ?",
            (teacher_id,),
        ).fetchone()[0]
        rated = conn.execute(
            "SELECT COUNT(*) FROM generations WHERE teacher_id = ? AND teacher_rating IS NOT NULL",
            (teacher_id,),
        ).fetchone()[0]
        edited = conn.execute(
            "SELECT COUNT(*) FROM generations WHERE teacher_id = ? AND was_edited = 1",
            (teacher_id,),
        ).fetchone()[0]
        avg_rating_row = conn.execute(
            "SELECT AVG(teacher_rating) FROM generations WHERE teacher_id = ? AND teacher_rating IS NOT NULL",
            (teacher_id,),
        ).fetchone()
        avg_rating = avg_rating_row[0] if avg_rating_row[0] is not None else 0.0

    return {
        "total_generations": total,
        "rated": rated,
        "edited": edited,
        "edit_rate": edited / total if total > 0 else 0.0,
        "avg_rating": round(avg_rating, 2),
        "patterns": len(get_patterns(teacher_id)),
    }


def self_distill(teacher_id: str, llm_generate=None) -> str:
    """Self-distillation: analyze best outputs to improve future generations.

    Implements the core insight from "Embarrassingly Simple Self-Distillation
    Improves Code Generation" (Zhang et al., 2025) — adapted for teaching:

    1. Find highest-rated generations (teacher 4-5 stars)
    2. Find lowest-rated or most-edited generations
    3. Ask LLM to identify what made the good ones good
    4. Produce actionable rules for soul.md

    Returns the distilled insights as text for soul.md injection.
    """
    _ensure_db()

    with _get_conn() as conn:
        conn.row_factory = sqlite3.Row

        # Best generations (rated 4-5 by teacher)
        best = conn.execute(
            "SELECT generation_type, topic, subject, grade, "
            "score_json, teacher_feedback "
            "FROM generations "
            "WHERE teacher_id = ? AND teacher_rating >= 4 "
            "ORDER BY teacher_rating DESC, timestamp DESC LIMIT 10",
            (teacher_id,),
        ).fetchall()

        # Worst generations (rated 1-2 OR heavily edited)
        worst = conn.execute(
            "SELECT generation_type, topic, subject, grade, "
            "score_json, teacher_feedback, edit_summary "
            "FROM generations "
            "WHERE teacher_id = ? AND "
            "(teacher_rating <= 2 OR was_edited = 1) "
            "ORDER BY timestamp DESC LIMIT 10",
            (teacher_id,),
        ).fetchall()

        # Confirmed patterns (3+ occurrences)
        patterns = conn.execute(
            "SELECT pattern_type, description, occurrences "
            "FROM patterns "
            "WHERE teacher_id = ? AND occurrences >= 3 "
            "ORDER BY occurrences DESC LIMIT 10",
            (teacher_id,),
        ).fetchall()

    if not best and not worst and not patterns:
        return ""

    # Build distillation summary without LLM (deterministic)
    insights = []

    if best:
        insights.append("## What Works (from highest-rated lessons)")
        for row in best:
            topic = row["topic"] or "unknown"
            feedback = row["teacher_feedback"] or ""
            scores = json.loads(row["score_json"]) if row["score_json"] else {}
            line = f"- {topic}"
            if feedback:
                line += f': "{feedback}"'
            if scores:
                top_score = max(scores.items(), key=lambda x: x[1])
                line += f" (best: {top_score[0]}={top_score[1]:.1f})"
            insights.append(line)

    if worst:
        insights.append("\n## What to Avoid (from edited/low-rated lessons)")
        for row in worst:
            topic = row["topic"] or "unknown"
            edit = row["edit_summary"] or ""
            feedback = row["teacher_feedback"] or ""
            detail = edit or feedback or "teacher edited heavily"
            insights.append(f"- {topic}: {detail}")

    if patterns:
        insights.append("\n## Confirmed Patterns (recurring teacher behaviors)")
        for row in patterns:
            insights.append(f"- [{row['pattern_type']}] {row['description']} (seen {row['occurrences']}x)")

    # If LLM is available, generate actionable rules
    if llm_generate and (best or worst):
        try:
            prompt = (
                "You are Ed, a self-improving teaching agent. Based on "
                "teacher feedback patterns, generate 3-5 specific, "
                "actionable rules for improving future lesson generation. "
                "Be concrete — reference specific formats, structures, "
                "or approaches.\n\n" + "\n".join(insights) + "\n\nRules (one per line, start each with 'RULE:'):"
            )
            rules_text = llm_generate(prompt)
            if rules_text:
                insights.append("\n## Self-Distilled Rules")
                for line in rules_text.split("\n"):
                    line = line.strip()
                    if line.startswith("RULE:"):
                        insights.append(f"- {line[5:].strip()}")
        except Exception as e:
            logger.debug("LLM distillation failed: %s", e)

    distilled = "\n".join(insights)

    # Auto-update soul.md with distilled insights
    if distilled:
        try:
            data_dir = os.environ.get("EDUAGENT_DATA_DIR", str(Path.home() / ".eduagent"))
            soul_path = Path(data_dir) / "workspace" / "soul.md"
            if soul_path.exists():
                current = soul_path.read_text(encoding="utf-8")
                # Replace or append distillation section
                marker = "## Self-Distilled Insights"
                if marker in current:
                    # Replace existing section
                    before = current.split(marker)[0].rstrip()
                    updated = f"{before}\n\n{marker}\n{distilled}\n"
                else:
                    updated = f"{current}\n\n{marker}\n{distilled}\n"
                soul_path.write_text(updated, encoding="utf-8")
                logger.info(
                    "Soul.md updated with %d distilled insights",
                    len(insights),
                )
        except Exception as e:
            logger.warning("Failed to update soul.md: %s", e)

    return distilled


def reset_db() -> None:
    """Reset initialized flag. For testing."""
    global _initialized
    _initialized = False
