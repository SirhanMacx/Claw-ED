"""Rating and feedback handler with memory engine integration.

Extracted from tg.py lines 1501-1582.
"""
from __future__ import annotations

import logging
from typing import Any

from clawed.gateway_response import Button, GatewayResponse

logger = logging.getLogger(__name__)


def _lazy_rate_lesson(user_id: str, lesson_id: str, rating: int) -> Any:
    from clawed.analytics import rate_lesson
    return rate_lesson(user_id, lesson_id, rating)


def _lazy_get_teacher_stats(teacher_id: str) -> dict[str, Any]:
    from clawed.analytics import get_teacher_stats
    return get_teacher_stats(teacher_id)


rate_lesson = _lazy_rate_lesson
get_teacher_stats = _lazy_get_teacher_stats


def memory_process(
    lesson: Any,
    rating: int,
    notes: Any = None,
    edited_sections: Any = None,
    subject: Any = None,
) -> list[Any]:
    try:
        from clawed.memory_engine import process_feedback
        return process_feedback(lesson, rating, notes, edited_sections, subject)
    except Exception as e:
        logger.debug("Memory engine skipped: %s", e)
        return []


class FeedbackHandler:
    def rating_prompt(self, lesson_id: str) -> GatewayResponse:
        buttons = [
            Button(label=f"{'★' * i}{'☆' * (5 - i)}", callback_data=f"rate:{lesson_id}:{i}")
            for i in range(1, 6)
        ]
        buttons.append(Button(label="Skip", callback_data=f"rate:{lesson_id}:0"))
        return GatewayResponse(
            text="How was this lesson?",
            button_rows=[buttons[:3], buttons[3:]],
        )

    async def rate(self, lesson_id: str, teacher_id: str, rating: int) -> GatewayResponse:
        if rating == 0:
            return GatewayResponse(text="Skipped rating.")

        try:
            rate_lesson(teacher_id, lesson_id, rating)
        except Exception as e:
            logger.error("Rating save failed: %s", e)

        try:
            from clawed.state import _get_conn
            with _get_conn() as conn:
                row = conn.execute(
                    "SELECT lesson_json FROM generated_lessons WHERE id = ?",
                    (lesson_id,),
                ).fetchone()
                if row:
                    from clawed.models import DailyLesson
                    lesson = DailyLesson.model_validate_json(row["lesson_json"])
                    memory_process(lesson, rating)
        except Exception as e:
            logger.debug("Memory loop skipped: %s", e)

        stars = "\u2605" * rating + "\u2606" * (5 - rating)
        return GatewayResponse(text=f"Thanks! Rated {stars} ({rating}/5)")

    async def summary(self, teacher_id: str) -> GatewayResponse:
        try:
            stats = get_teacher_stats(teacher_id)
            avg = stats.get("overall_avg_rating", 0)
            total = stats.get("rated_lessons", 0)
            streak = stats.get("streak", 0)
            return GatewayResponse(
                text=(
                    f"Your feedback summary:\n"
                    f"Average rating: {avg:.1f}/5\n"
                    f"Lessons rated: {total}\n"
                    f"Current streak: {streak}"
                ),
            )
        except Exception as e:
            logger.error("Feedback summary failed: %s", e)
            return GatewayResponse(text="No feedback data yet. Rate some lessons first!")
