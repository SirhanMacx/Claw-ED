"""Analytics dashboard — rating trends, effectiveness metrics, and usage streaks."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from clawed.state import _get_conn, init_db

logger = logging.getLogger(__name__)


def average_rating_by_subject(teacher_id: str) -> dict[str, float]:
    """Average lesson rating grouped by subject.

    Returns:
        {"Science": 4.2, "Math": 3.8, ...}
    """
    init_db()
    with _get_conn() as conn:
        rows = conn.execute(
            """
            SELECT json_extract(gl.lesson_json, '$.subject') as subject, AVG(gl.rating) as avg_rating
            FROM generated_lessons gl
            LEFT JOIN generated_units gu ON gl.unit_id = gu.id
            WHERE gl.teacher_id = ? AND gl.rating IS NOT NULL
            GROUP BY subject
            """,
            (teacher_id,),
        ).fetchall()

    result: dict[str, float] = {}
    for row in rows:
        subject = row["subject"] or "General"
        result[subject] = round(row["avg_rating"], 2)

    # Also try extracting subject from unit if lesson doesn't have it
    if not result:
        with _get_conn() as conn:
            rows = conn.execute(
                """
                SELECT gu.subject, AVG(gl.rating) as avg_rating
                FROM generated_lessons gl
                JOIN generated_units gu ON gl.unit_id = gu.id
                WHERE gl.teacher_id = ? AND gl.rating IS NOT NULL AND gu.subject IS NOT NULL
                GROUP BY gu.subject
                """,
                (teacher_id,),
            ).fetchall()
        for row in rows:
            if row["subject"]:
                result[row["subject"]] = round(row["avg_rating"], 2)

    return result


def most_effective_topics(teacher_id: str, limit: int = 10) -> list[dict[str, Any]]:
    """Topics with highest average ratings.

    Returns:
        [{"topic": "Photosynthesis", "avg_rating": 4.8, "count": 3}, ...]
    """
    init_db()
    with _get_conn() as conn:
        rows = conn.execute(
            """
            SELECT gl.title as topic, AVG(gl.rating) as avg_rating, COUNT(*) as count
            FROM generated_lessons gl
            WHERE gl.teacher_id = ? AND gl.rating IS NOT NULL
            GROUP BY gl.title
            HAVING count >= 1
            ORDER BY avg_rating DESC, count DESC
            LIMIT ?
            """,
            (teacher_id, limit),
        ).fetchall()

    return [{"topic": row["topic"], "avg_rating": round(row["avg_rating"], 2), "count": row["count"]} for row in rows]


def lessons_needing_improvement(teacher_id: str, threshold: int = 3) -> list[dict[str, Any]]:
    """Lessons rated below the threshold that need rework.

    Returns:
        [{"lesson_id": "...", "title": "...", "rating": 2, "created_at": "..."}, ...]
    """
    init_db()
    with _get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id as lesson_id, title, rating, created_at
            FROM generated_lessons
            WHERE teacher_id = ? AND rating IS NOT NULL AND rating < ?
            ORDER BY rating ASC, created_at DESC
            """,
            (teacher_id, threshold),
        ).fetchall()

    return [dict(row) for row in rows]


def usage_streak(teacher_id: str) -> int:
    """Count consecutive days (ending today) the teacher used Claw-ED.

    Returns:
        Number of consecutive days (0 if not used today).
    """
    init_db()
    with _get_conn() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT date(created_at) as day
            FROM generated_lessons
            WHERE teacher_id = ?
            UNION
            SELECT DISTINCT date(created_at) as day
            FROM feedback
            WHERE teacher_id = ?
            ORDER BY day DESC
            """,
            (teacher_id, teacher_id),
        ).fetchall()

    if not rows:
        return 0

    today = datetime.now(timezone.utc).date()
    days = sorted({datetime.strptime(row["day"], "%Y-%m-%d").date() for row in rows if row["day"]}, reverse=True)

    if not days or days[0] < today - timedelta(days=1):
        return 0

    streak = 0
    expected = today
    for day in days:
        if day == expected:
            streak += 1
            expected -= timedelta(days=1)
        elif day == expected + timedelta(days=1):
            # today hasn't been counted yet but yesterday was
            continue
        else:
            break

    return streak


def get_teacher_stats(teacher_id: str) -> dict[str, Any]:
    """Comprehensive stats summary for a teacher.

    Returns a dict with all analytics rolled up.
    """
    init_db()
    with _get_conn() as conn:
        total_lessons = conn.execute(
            "SELECT COUNT(*) as c FROM generated_lessons WHERE teacher_id = ?", (teacher_id,)
        ).fetchone()["c"]

        rated_lessons = conn.execute(
            "SELECT COUNT(*) as c FROM generated_lessons WHERE teacher_id = ? AND rating IS NOT NULL", (teacher_id,)
        ).fetchone()["c"]

        avg_rating_row = conn.execute(
            "SELECT AVG(rating) as avg FROM generated_lessons"
            " WHERE teacher_id = ? AND rating IS NOT NULL",
            (teacher_id,),
        ).fetchone()
        overall_avg = round(avg_rating_row["avg"], 2) if avg_rating_row["avg"] else 0.0

        total_units = conn.execute(
            "SELECT COUNT(*) as c FROM generated_units WHERE teacher_id = ?", (teacher_id,)
        ).fetchone()["c"]

        total_feedback = conn.execute(
            "SELECT COUNT(*) as c FROM feedback WHERE teacher_id = ?", (teacher_id,)
        ).fetchone()["c"]

        # Rating distribution
        distribution: dict[int, int] = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        dist_rows = conn.execute(
            "SELECT rating, COUNT(*) as c FROM generated_lessons"
            " WHERE teacher_id = ? AND rating IS NOT NULL GROUP BY rating",
            (teacher_id,),
        ).fetchall()
        for row in dist_rows:
            if 1 <= row["rating"] <= 5:
                distribution[row["rating"]] = row["c"]

    return {
        "total_lessons": total_lessons,
        "rated_lessons": rated_lessons,
        "overall_avg_rating": overall_avg,
        "total_units": total_units,
        "total_feedback": total_feedback,
        "rating_distribution": distribution,
        "by_subject": average_rating_by_subject(teacher_id),
        "top_topics": most_effective_topics(teacher_id, limit=5),
        "needs_improvement": lessons_needing_improvement(teacher_id),
        "streak": usage_streak(teacher_id),
    }


def rate_lesson(teacher_id: str, lesson_id: str, rating: int, notes: str = "") -> bool:
    """Rate a generated lesson and optionally save feedback.

    Returns True if the lesson was found and rated.
    """
    import uuid

    rating = max(1, min(5, rating))
    init_db()

    with _get_conn() as conn:
        # Update the lesson rating
        cursor = conn.execute(
            "UPDATE generated_lessons SET rating = ? WHERE id = ? AND teacher_id = ?",
            (rating, lesson_id, teacher_id),
        )
        if cursor.rowcount == 0:
            return False

        # Also insert a feedback record
        conn.execute(
            "INSERT INTO feedback (id, lesson_id, teacher_id, rating, notes) VALUES (?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), lesson_id, teacher_id, rating, notes),
        )

    # Auto-queue low-rated lessons for improvement analysis
    from clawed.improver import queue_low_rated_for_improvement

    queue_low_rated_for_improvement(rating, lesson_id, teacher_id)

    # Feed into the memory engine for prompt-level RLHF
    try:
        from clawed.memory_engine import process_feedback as memory_process

        # Load the lesson data to extract patterns
        lesson_json = None
        with _get_conn() as conn2:
            row2 = conn2.execute(
                "SELECT lesson_json FROM generated_lessons WHERE id = ?",
                (lesson_id,),
            ).fetchone()
            if row2:
                lesson_json = row2["lesson_json"]

        if lesson_json:
            from clawed.models import DailyLesson
            lesson_obj = DailyLesson.model_validate_json(lesson_json)
            # Resolve subject from the lesson's unit (not teacher profile)
            # so a History lesson gets tagged [History] even if the teacher
            # also teaches Science.
            subject = ""
            try:
                with _get_conn() as conn3:
                    unit_row = conn3.execute(
                        "SELECT u.subject FROM generated_units u "
                        "JOIN generated_lessons l ON l.unit_id = u.id "
                        "WHERE l.id = ?",
                        (lesson_id,),
                    ).fetchone()
                    if unit_row and unit_row["subject"]:
                        subject = unit_row["subject"]
            except (ConnectionError, OSError):
                pass
            # Fallback to teacher profile if no unit subject found
            if not subject:
                try:
                    from clawed.models import AppConfig
                    cfg = AppConfig.load()
                    if cfg.teacher_profile and cfg.teacher_profile.subjects:
                        subject = cfg.teacher_profile.subjects[0]
                except ImportError:
                    pass
            memory_process(lesson_obj, rating, notes, subject=subject)
            # Track lesson metadata for rule-based quality insights
            from clawed.memory_engine import track_lesson_metadata
            track_lesson_metadata(lesson_obj, rating)
    except Exception as exc:
        # Memory engine is best-effort -- never block rating
        logger.debug("Memory engine feedback processing failed: %s", exc)

    return True
