"""Feedback routes — rating, analysis, and prompt improvement."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from clawed.api.deps import get_db, require_auth
from clawed.corpus import contribute_example
from clawed.feedback import analyze_feedback, collect_feedback
from clawed.improver import improve_prompts

logger = logging.getLogger(__name__)

router = APIRouter(tags=["feedback"], dependencies=[Depends(require_auth)])


class FeedbackRequest(BaseModel):
    lesson_id: str
    rating: int
    notes: str = ""
    sections_edited: list[str] = Field(default_factory=list)


class ImproveRequest(BaseModel):
    feedback_window_days: int = 7


@router.post("/feedback")
async def submit_feedback(req: FeedbackRequest):
    """Teacher rates generated content."""
    if not 1 <= req.rating <= 5:
        return JSONResponse({"error": "Rating must be 1-5."}, status_code=400)

    db = get_db()

    lesson = db.get_lesson(req.lesson_id)
    if not lesson:
        return JSONResponse({"error": "Lesson not found."}, status_code=404)

    feedback_id = collect_feedback(
        db=db,
        lesson_id=req.lesson_id,
        rating=req.rating,
        notes=req.notes,
        sections_edited=req.sections_edited,
    )

    db.rate_lesson(req.lesson_id, req.rating)

    # Auto-contribute high-quality lessons to the corpus (rating >= 4)
    corpus_contributed = False
    if req.rating >= 4 and lesson.get("lesson_json"):
        try:
            teacher = db.get_default_teacher()
            lesson_data = json.loads(lesson["lesson_json"])
            # Extract metadata from the lesson row / lesson data
            grade_level = lesson_data.get("grade_level", "")
            subject = lesson_data.get("subject", "")
            topic = lesson_data.get("topic", lesson_data.get("title", ""))

            # Fall back to unit metadata if not in lesson directly
            if not subject or not grade_level:
                unit_row = db.get_unit(lesson.get("unit_id", "")) if hasattr(db, "get_unit") else None
                if unit_row and unit_row.get("unit_json"):
                    unit_data = json.loads(unit_row["unit_json"])
                    subject = subject or unit_data.get("subject", "")
                    grade_level = grade_level or unit_data.get("grade_level", "")

            if subject:
                contribute_example(
                    content_type="lesson_plan",
                    subject=subject.lower(),
                    grade_level=grade_level,
                    content=lesson_data,
                    topic=topic,
                    quality_score=float(req.rating),
                    teacher_id=teacher["id"] if teacher else None,
                    source="teacher",
                )
                corpus_contributed = True
        except Exception:
            pass  # Corpus contribution is best-effort; never block feedback submission

    msg = "Feedback recorded. Thank you!"
    if corpus_contributed:
        msg += " This lesson has been added to your teaching corpus to improve future generations."

    return {"feedback_id": feedback_id, "message": msg, "corpus_contributed": corpus_contributed}


@router.get("/feedback/{lesson_id}")
async def get_feedback(lesson_id: str):
    """Get all feedback for a lesson."""
    db = get_db()
    feedback_list = db.get_feedback_for_lesson(lesson_id)
    return {"feedback": feedback_list}


@router.get("/feedback-analysis")
async def feedback_analysis(days: int = 7):
    """Get feedback analysis summary."""
    db = get_db()
    analysis = analyze_feedback(db, days)
    return {"analysis": analysis}


def _server_side_teacher_id() -> str:
    """Resolve the authenticated caller's teacher_id.

    v4.11.2026.1 security fix (P1-6 remainder): the previous routes
    accepted ``teacher_id`` as a free-form path / query parameter, so
    any authed caller could read analytics for any other teacher in a
    multi-teacher deployment. We now always resolve from the identity
    module and ignore caller-supplied values.
    """
    try:
        from clawed.agent_core.identity import get_teacher_id as _gtid
        return _gtid() or "default"
    except Exception:
        return "default"


@router.get("/stats")
async def teacher_stats():
    """Get comprehensive teacher analytics for the authenticated caller."""
    from clawed.analytics import get_teacher_stats
    return get_teacher_stats(_server_side_teacher_id())


@router.get("/stats/{teacher_id}")
async def teacher_stats_by_id(teacher_id: str):
    """Get analytics for the authenticated caller.

    The ``teacher_id`` path parameter is retained for URL-shape
    backwards compatibility but is **ignored**. The server resolves
    the caller's identity internally.
    """
    from clawed.analytics import get_teacher_stats
    # teacher_id from the URL is intentionally ignored.
    del teacher_id
    return get_teacher_stats(_server_side_teacher_id())


@router.post("/improve")
async def trigger_improvement(req: ImproveRequest | None = None):
    """Trigger a prompt improvement cycle."""
    db = get_db()
    days = req.feedback_window_days if req else 7

    try:
        result = await improve_prompts(db, feedback_window_days=days)
    except Exception:
        # v4.11.2026.1 security fix (P2-8): don't leak raw exception
        # text to the client. Log it with exc_info for the operator.
        logger.error("Prompt improvement cycle failed", exc_info=True)
        return JSONResponse(
            {"error": "Improvement cycle failed. See server logs for details."},
            status_code=500,
        )

    return result
