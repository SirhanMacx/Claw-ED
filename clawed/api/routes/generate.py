"""Generation routes — unit plans, lessons, materials, full pipeline."""

from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from clawed.api.deps import get_db, limiter, require_auth
from clawed.models import DailyLesson, TeacherPersona, UnitPlan

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["generate"],
    dependencies=[Depends(require_auth)],
)


def _sse(event: str, **kwargs) -> dict:
    """Build an SSE message dict."""
    return {"event": event, "data": json.dumps(kwargs)}


class UnitRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=500)
    grade_level: str = Field("8", min_length=1, max_length=20)
    subject: str = Field("Science", min_length=1, max_length=100)
    duration_weeks: int = Field(3, ge=1, le=52)
    standards: list[str] = Field(default_factory=list)


class LessonRequest(BaseModel):
    unit_id: str
    lesson_number: int = Field(1, ge=1, le=100)


class MaterialsRequest(BaseModel):
    lesson_id: str


class FullRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=500)
    grade_level: str = Field("8", min_length=1, max_length=20)
    subject: str = Field("Science", min_length=1, max_length=100)
    duration_weeks: int = Field(3, ge=1, le=52)
    standards: list[str] = Field(default_factory=list)
    include_homework: bool = True
    max_lessons: Optional[int] = Field(None, ge=1, le=100)
    template_slug: Optional[str] = None


class CourseRequest(BaseModel):
    subject: str = Field(..., min_length=1, max_length=100)
    grade_level: str = Field(..., min_length=1, max_length=20)
    topics: list[str]
    weeks_per_topic: int = Field(2, ge=1, le=52)


def _get_persona(db) -> tuple[Optional[TeacherPersona], Optional[str]]:
    """Load persona from the default teacher in the DB."""
    teacher = db.get_default_teacher()
    if not teacher or not teacher.get("persona_json"):
        return None, None
    persona = TeacherPersona.model_validate_json(teacher["persona_json"])
    return persona, teacher["id"]


@router.post("/unit")
@limiter.limit("10/minute")
async def create_unit(request: Request, req: UnitRequest):
    """Generate a unit plan."""
    from clawed.planner import plan_unit

    db = get_db()
    persona, teacher_id = _get_persona(db)
    if not persona:
        return JSONResponse(
            {"error": "No persona found. Upload teaching materials first."},
            status_code=400,
        )

    try:
        unit = await plan_unit(
            subject=req.subject,
            grade_level=req.grade_level,
            topic=req.topic,
            duration_weeks=req.duration_weeks,
            persona=persona,
            standards=req.standards or None,
        )
    except Exception:
        logger.error("Unit generation failed", exc_info=True)
        return JSONResponse({"error": "Unit generation failed. Please try again."}, status_code=500)

    unit_id = db.insert_unit(
        teacher_id=teacher_id,
        title=unit.title,
        subject=unit.subject,
        grade_level=unit.grade_level,
        topic=unit.topic,
        unit_json=unit.model_dump_json(),
    )

    return {"unit_id": unit_id, "unit": unit.model_dump()}


@router.post("/lesson")
@limiter.limit("10/minute")
async def create_lesson(request: Request, req: LessonRequest):
    """Generate a single lesson plan for a unit."""
    from clawed.lesson import generate_lesson

    db = get_db()
    persona, _ = _get_persona(db)
    if not persona:
        return JSONResponse({"error": "No persona found."}, status_code=400)

    unit_row = db.get_unit(req.unit_id)
    if not unit_row:
        return JSONResponse({"error": "Unit not found."}, status_code=404)

    unit = UnitPlan.model_validate_json(unit_row["unit_json"])

    try:
        lesson = await generate_lesson(
            lesson_number=req.lesson_number,
            unit=unit,
            persona=persona,
        )
    except Exception:
        logger.error("Lesson generation failed", exc_info=True)
        return JSONResponse({"error": "Lesson generation failed. Please try again."}, status_code=500)

    lesson_id = db.insert_lesson(
        unit_id=req.unit_id,
        lesson_number=lesson.lesson_number,
        title=lesson.title,
        lesson_json=lesson.model_dump_json(),
    )

    return {"lesson_id": lesson_id, "lesson": lesson.model_dump()}


@router.post("/materials")
@limiter.limit("10/minute")
async def create_materials(request: Request, req: MaterialsRequest):
    """Generate materials for a lesson."""
    from clawed.materials import generate_all_materials

    db = get_db()
    persona, _ = _get_persona(db)
    if not persona:
        return JSONResponse({"error": "No persona found."}, status_code=400)

    lesson_row = db.get_lesson(req.lesson_id)
    if not lesson_row:
        return JSONResponse({"error": "Lesson not found."}, status_code=404)

    lesson = DailyLesson.model_validate_json(lesson_row["lesson_json"])

    try:
        materials = await generate_all_materials(lesson, persona)
    except Exception:
        logger.error("Materials generation failed", exc_info=True)
        return JSONResponse(
            {"error": "Materials generation failed. Please try again."},
            status_code=500,
        )

    db.update_lesson_materials(req.lesson_id, materials.model_dump_json())

    return {
        "lesson_id": req.lesson_id,
        "materials": materials.model_dump(),
    }


@router.post("/full")
@limiter.limit("10/minute")
async def full_pipeline(request: Request, req: FullRequest):
    """End-to-end: generate unit + all lessons + materials. Returns SSE progress events."""
    from clawed.lesson import generate_lesson
    from clawed.materials import generate_all_materials
    from clawed.planner import plan_unit

    db = get_db()
    persona, teacher_id = _get_persona(db)
    if not persona:
        return JSONResponse({"error": "No persona found."}, status_code=400)

    async def event_stream():
        yield _sse(
            "progress",
            step="unit",
            status="generating",
            message="Generating unit plan...",
        )

        try:
            unit = await plan_unit(
                subject=req.subject,
                grade_level=req.grade_level,
                topic=req.topic,
                duration_weeks=req.duration_weeks,
                persona=persona,
                standards=req.standards or None,
            )
        except Exception:
            logger.error("Unit generation failed in SSE stream", exc_info=True)
            yield _sse("error", error="Unit generation failed. Please try again.")
            return

        unit_id = db.insert_unit(
            teacher_id=teacher_id,
            title=unit.title,
            subject=unit.subject,
            grade_level=unit.grade_level,
            topic=unit.topic,
            unit_json=unit.model_dump_json(),
        )

        yield _sse(
            "progress",
            step="unit",
            status="done",
            unit_id=unit_id,
            title=unit.title,
            lesson_count=len(unit.daily_lessons),
        )

        briefs = unit.daily_lessons
        if req.max_lessons:
            briefs = briefs[: req.max_lessons]

        lesson_ids = []
        for brief in briefs:
            yield _sse(
                "progress",
                step="lesson",
                status="generating",
                lesson_number=brief.lesson_number,
                topic=brief.topic,
            )

            try:
                lesson = await generate_lesson(
                    lesson_number=brief.lesson_number,
                    unit=unit,
                    persona=persona,
                    include_homework=req.include_homework,
                )
            except Exception:
                logger.error("Lesson %d generation failed", brief.lesson_number, exc_info=True)
                yield _sse(
                    "progress",
                    step="lesson",
                    status="error",
                    lesson_number=brief.lesson_number,
                    error="Lesson generation failed.",
                )
                continue

            lid = db.insert_lesson(
                unit_id=unit_id,
                lesson_number=lesson.lesson_number,
                title=lesson.title,
                lesson_json=lesson.model_dump_json(),
            )
            lesson_ids.append(lid)

            yield _sse(
                "progress",
                step="lesson",
                status="done",
                lesson_id=lid,
                lesson_number=lesson.lesson_number,
                title=lesson.title,
            )

        for lid in lesson_ids:
            lesson_row = db.get_lesson(lid)
            if not lesson_row:
                continue

            yield _sse(
                "progress",
                step="materials",
                status="generating",
                lesson_id=lid,
            )

            lesson_obj = DailyLesson.model_validate_json(lesson_row["lesson_json"])

            try:
                materials = await generate_all_materials(lesson_obj, persona)
                db.update_lesson_materials(lid, materials.model_dump_json())
            except Exception:
                pass

            yield _sse(
                "progress",
                step="materials",
                status="done",
                lesson_id=lid,
            )

        yield _sse(
            "done",
            unit_id=unit_id,
            lesson_count=len(lesson_ids),
        )

    return EventSourceResponse(event_stream())


@router.get("/stream/unit")
@limiter.limit("10/minute")
async def stream_unit(
    request: Request,
    topic: str,
    grade_level: str = "8",
    subject: str = "Science",
    duration_weeks: int = 3,
):
    """Stream unit plan generation via SSE (GET for EventSource)."""
    from clawed.planner import plan_unit

    db = get_db()
    persona, teacher_id = _get_persona(db)
    if not persona:
        return JSONResponse({"error": "No persona found."}, status_code=400)

    async def event_stream():
        yield _sse(
            "progress",
            status="planning_unit",
            progress=10,
            message="Planning unit structure...",
        )

        try:
            unit = await plan_unit(
                subject=subject,
                grade_level=grade_level,
                topic=topic,
                duration_weeks=duration_weeks,
                persona=persona,
            )
        except Exception:
            logger.error("Stream unit generation failed", exc_info=True)
            yield _sse("error", error="Unit generation failed. Please try again.")
            return

        unit_id = db.insert_unit(
            teacher_id=teacher_id,
            title=unit.title,
            subject=unit.subject,
            grade_level=unit.grade_level,
            topic=unit.topic,
            unit_json=unit.model_dump_json(),
        )

        yield _sse(
            "progress",
            status="unit_complete",
            progress=100,
            unit_id=unit_id,
            title=unit.title,
            lesson_count=len(unit.daily_lessons),
        )
        yield _sse("done", unit_id=unit_id)

    return EventSourceResponse(event_stream())


@router.get("/stream/lesson")
@limiter.limit("10/minute")
async def stream_lesson(request: Request, unit_id: str, lesson_number: int = 1):
    """Stream single lesson generation via SSE (GET for EventSource)."""
    from clawed.lesson import generate_lesson

    db = get_db()
    persona, _ = _get_persona(db)
    if not persona:
        return JSONResponse({"error": "No persona found."}, status_code=400)

    unit_row = db.get_unit(unit_id)
    if not unit_row:
        return JSONResponse({"error": "Unit not found."}, status_code=404)

    unit = UnitPlan.model_validate_json(unit_row["unit_json"])

    async def event_stream():
        yield _sse(
            "progress",
            status=f"generating_lesson_{lesson_number}",
            progress=20,
            message=f"Generating Lesson {lesson_number}...",
        )

        try:
            lesson = await generate_lesson(
                lesson_number=lesson_number,
                unit=unit,
                persona=persona,
            )
        except Exception:
            logger.error("Stream lesson generation failed", exc_info=True)
            yield _sse("error", error="Lesson generation failed. Please try again.")
            return

        lid = db.insert_lesson(
            unit_id=unit_id,
            lesson_number=lesson.lesson_number,
            title=lesson.title,
            lesson_json=lesson.model_dump_json(),
        )

        yield _sse(
            "progress",
            status="lesson_complete",
            progress=100,
            lesson_id=lid,
            title=lesson.title,
        )
        yield _sse("done", lesson_id=lid)

    return EventSourceResponse(event_stream())


@router.post("/course")
@limiter.limit("10/minute")
async def create_course(request: Request, req: CourseRequest):
    """Generate a full course structure — year plan from a list of topics."""
    from clawed.planner import plan_unit

    db = get_db()
    persona, teacher_id = _get_persona(db)
    if not persona:
        return JSONResponse({"error": "No persona found."}, status_code=400)

    async def event_stream():
        total = len(req.topics)
        course_units = []

        for i, topic in enumerate(req.topics, 1):
            pct = int((i - 1) / total * 100)
            yield _sse(
                "progress",
                status="generating_unit",
                progress=pct,
                message=f"Planning unit {i}/{total}: {topic}...",
            )

            try:
                unit = await plan_unit(
                    subject=req.subject,
                    grade_level=req.grade_level,
                    topic=topic,
                    duration_weeks=req.weeks_per_topic,
                    persona=persona,
                )
            except Exception:
                logger.error("Failed to plan topic '%s'", topic, exc_info=True)
                yield _sse(
                    "progress",
                    status="error",
                    message=f"Failed to plan '{topic}'. Skipping.",
                )
                course_units.append({"topic": topic, "error": "Generation failed."})
                continue

            unit_id = db.insert_unit(
                teacher_id=teacher_id,
                title=unit.title,
                subject=unit.subject,
                grade_level=unit.grade_level,
                topic=unit.topic,
                unit_json=unit.model_dump_json(),
            )

            unit_summary = {
                "unit_id": unit_id,
                "title": unit.title,
                "topic": topic,
                "lesson_titles": [b.topic for b in unit.daily_lessons],
            }
            course_units.append(unit_summary)

            yield _sse(
                "progress",
                status="unit_done",
                progress=int(i / total * 100),
                unit=unit_summary,
            )

        successful = [u for u in course_units if "unit_id" in u]
        yield _sse(
            "done",
            course=course_units,
            total_units=len(successful),
        )

    return EventSourceResponse(event_stream())


@router.get("/score/{lesson_id}")
@limiter.limit("60/minute")
async def score_lesson(request: Request, lesson_id: str):
    """Score a lesson on quality dimensions."""
    from clawed.quality import LessonQualityScore

    db = get_db()
    lesson_row = db.get_lesson(lesson_id)
    if not lesson_row:
        return JSONResponse({"error": "Lesson not found."}, status_code=404)

    lesson = DailyLesson.model_validate_json(lesson_row["lesson_json"])
    materials = None
    if lesson_row.get("materials_json"):
        from clawed.models import LessonMaterials

        materials = LessonMaterials.model_validate_json(lesson_row["materials_json"])

    scorer = LessonQualityScore()
    scores = await scorer.score(lesson, materials)

    # Store scores in DB
    db.update_lesson_scores(lesson_id, json.dumps(scores))

    return {"lesson_id": lesson_id, "scores": scores}


@router.post("/suggest/{lesson_id}")
@limiter.limit("10/minute")
async def suggest_improvements_endpoint(request: Request, lesson_id: str):
    """Generate improvement suggestions for a lesson."""
    from clawed.improver import suggest_improvements

    db = get_db()
    lesson_row = db.get_lesson(lesson_id)
    if not lesson_row:
        return JSONResponse({"error": "Lesson not found."}, status_code=404)

    lesson = DailyLesson.model_validate_json(lesson_row["lesson_json"])

    # Check for feedback notes
    feedback_list = db.get_feedback_for_lesson(lesson_id)
    notes = " | ".join(f["notes"] for f in feedback_list if f.get("notes"))

    suggestions = await suggest_improvements(lesson, feedback_notes=notes)
    return {"lesson_id": lesson_id, "suggestions": suggestions}


@router.get("/templates")
@limiter.limit("60/minute")
async def list_templates_endpoint(request: Request):
    """List all available lesson structure templates."""
    from clawed.templates_lib import list_templates

    templates = list_templates()
    return {
        "templates": [
            {
                "name": t.name,
                "slug": t.slug,
                "description": t.description,
                "best_for": t.best_for,
            }
            for t in templates
        ]
    }


@router.get("/units")
@limiter.limit("60/minute")
async def list_units(request: Request):
    """List all generated units."""
    db = get_db()
    units = db.list_units()
    for u in units:
        u["lesson_count"] = len(db.list_lessons(u["id"]))
    return {"units": units}


@router.get("/lessons/{unit_id}")
@limiter.limit("60/minute")
async def list_lessons(request: Request, unit_id: str):
    """List all lessons for a unit."""
    db = get_db()
    lessons = db.list_lessons(unit_id)
    return {"lessons": lessons}
