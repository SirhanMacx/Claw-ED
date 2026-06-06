"""Generation routes — unit plans, lessons, materials, full pipeline."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from clawed.api.deps import get_db, limiter, require_auth
from clawed.database import Database
from clawed.models import DailyLesson, TeacherPersona, UnitPlan

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["generate"],
    dependencies=[Depends(require_auth)],
)


def _sse(event: str, **kwargs: Any) -> dict[str, str]:
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


class ImproveRequest(BaseModel):
    instruction: str = Field(..., min_length=1, max_length=1000)


class FullRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=500)
    grade_level: str = Field("8", min_length=1, max_length=20)
    subject: str = Field("Science", min_length=1, max_length=100)
    duration_weeks: int = Field(3, ge=1, le=52)
    standards: list[str] = Field(default_factory=list)
    include_homework: bool = True
    max_lessons: int | None = Field(None, ge=1, le=100)
    template_slug: str | None = None


class CourseRequest(BaseModel):
    subject: str = Field(..., min_length=1, max_length=100)
    grade_level: str = Field(..., min_length=1, max_length=20)
    topics: list[str]
    weeks_per_topic: int = Field(2, ge=1, le=52)


class QuizRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=500)
    grade_level: str = Field("8", min_length=1, max_length=20)
    subject: str = Field("General", min_length=1, max_length=100)
    num_questions: int = Field(10, ge=1, le=50)


DifferentiationProfile = Literal["struggling", "advanced", "ell", "iep"]


class DifferentiateRequest(BaseModel):
    profile: DifferentiationProfile = "struggling"


class GameRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=500)
    grade_level: str = Field("8", min_length=1, max_length=20)
    subject: str = Field("General", min_length=1, max_length=100)
    game_type: str = Field("", max_length=50)


# Each profile maps to a synthetic IEPProfile that drives the existing
# differentiation engine (clawed.differentiation). The keys mirror the
# four profiles the Create UI offers.
_DIFFERENTIATION_PROFILES: dict[str, dict[str, list[str]]] = {
    "struggling": {
        "accommodations": [
            "Chunk instructions into one step at a time",
            "Provide a word bank and sentence starters",
            "Extend time and reduce the number of required items",
        ],
        "modifications": [
            "Simplify reading level while keeping the same objective",
            "Add a partially completed graphic organizer",
        ],
        "goals": ["Access grade-level content with scaffolds"],
    },
    "advanced": {
        "accommodations": [
            "Offer an open-ended extension that deepens analysis",
            "Encourage independent inquiry and synthesis",
        ],
        "modifications": [
            "Raise the rigor with higher-order, evaluative prompts",
            "Add a challenge task that connects to a broader theme",
        ],
        "goals": ["Stretch beyond grade-level expectations"],
    },
    "ell": {
        "accommodations": [
            "Provide bilingual glossary and visual supports",
            "Use sentence frames and pre-teach key vocabulary",
            "Pair written text with images and simplified language",
        ],
        "modifications": [
            "Reduce linguistic load while keeping the content goal",
        ],
        "goals": ["Build academic language alongside content"],
    },
    "iep": {
        "accommodations": [
            "Apply extended time and chunked tasks",
            "Provide explicit step-by-step models and checklists",
            "Offer alternative response formats",
        ],
        "modifications": [
            "Adjust complexity to meet IEP goals while keeping the standard",
        ],
        "goals": ["Meet individualized learning goals with supports"],
    },
}

_PROFILE_LABELS: dict[str, str] = {
    "struggling": "Struggling Learners",
    "advanced": "Advanced Learners",
    "ell": "English Language Learners",
    "iep": "IEP",
}


def _get_persona(db: Database) -> tuple[TeacherPersona | None, str | None]:
    """Load persona from the default teacher in the DB.

    Single-operator model (ED-4 audit): this app is designed for one
    teacher per instance. ``get_default_teacher()`` returns the single
    operator's row. Multi-teacher isolation requires per-request teacher
    identity, which is a v5.0 goal.  See docs/ARCHITECTURE.md.
    """
    teacher = db.get_default_teacher()
    if not teacher or not teacher.get("persona_json"):
        return None, None
    persona = TeacherPersona.model_validate_json(teacher["persona_json"])
    return persona, teacher["id"]


@router.post("/unit")
@limiter.limit("10/minute")
async def create_unit(request: Request, req: UnitRequest) -> Any:
    """Generate a unit plan."""
    from clawed.planner import plan_unit

    db = get_db()
    persona, teacher_id = _get_persona(db)
    if not persona or teacher_id is None:
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
        return JSONResponse(
            {"error": "Unit generation failed. Please try again."}, status_code=500
        )

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
async def create_lesson(request: Request, req: LessonRequest) -> Any:
    """Generate a single lesson plan for a unit."""
    from clawed.lesson import generate_lesson

    db = get_db()
    persona, _ = _get_persona(db)
    if not persona:
        return JSONResponse(
            {"error": "No persona found."}, status_code=400
        )

    unit_row = db.get_unit(req.unit_id)
    if not unit_row:
        return JSONResponse(
            {"error": "Unit not found."}, status_code=404
        )

    unit = UnitPlan.model_validate_json(unit_row["unit_json"])

    try:
        lesson = await generate_lesson(
            lesson_number=req.lesson_number,
            unit=unit,
            persona=persona,
        )
    except Exception:
        logger.error("Lesson generation failed", exc_info=True)
        return JSONResponse(
            {"error": "Lesson generation failed. Please try again."}, status_code=500
        )

    lesson_id = db.insert_lesson(
        unit_id=req.unit_id,
        lesson_number=lesson.lesson_number,
        title=lesson.title,
        lesson_json=lesson.model_dump_json(),
    )

    return {"lesson_id": lesson_id, "lesson": lesson.model_dump()}


@router.post("/materials")
@limiter.limit("10/minute")
async def create_materials(request: Request, req: MaterialsRequest) -> Any:
    """Generate materials for a lesson."""
    from clawed.materials import generate_all_materials

    db = get_db()
    persona, _ = _get_persona(db)
    if not persona:
        return JSONResponse(
            {"error": "No persona found."}, status_code=400
        )

    lesson_row = db.get_lesson(req.lesson_id)
    if not lesson_row:
        return JSONResponse(
            {"error": "Lesson not found."}, status_code=404
        )

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


@router.post("/quiz")
@limiter.limit("10/minute")
async def create_quiz(request: Request, req: QuizRequest) -> Any:
    """Generate a standalone quiz/assessment on a topic.

    Reuses ``clawed.assessment.AssessmentGenerator``. Assessments are not
    persisted (no assessment table exists), so the full quiz is returned
    inline for the UI to render and copy.
    """
    from clawed.assessment import AssessmentGenerator

    db = get_db()
    # Persona is optional for quizzes — generate_quiz defaults to a blank
    # persona, so a missing persona is not a hard error here.
    persona, _ = _get_persona(db)

    try:
        gen = AssessmentGenerator()
        quiz = await gen.generate_quiz(
            topic=req.topic,
            question_count=req.num_questions,
            grade=req.grade_level,
            persona=persona,
        )
    except Exception:
        logger.error("Quiz generation failed", exc_info=True)
        return JSONResponse(
            {"error": "Quiz generation failed. Please try again."},
            status_code=500,
        )

    return {
        "topic": quiz.topic,
        "subject": req.subject,
        "grade_level": quiz.grade_level,
        "total_points": quiz.total_points,
        "question_count": len(quiz.questions),
        "quiz": quiz.model_dump(),
    }


@router.post("/differentiate/{lesson_id}")
@limiter.limit("10/minute")
async def differentiate_lesson_endpoint(
    request: Request, lesson_id: str, req: DifferentiateRequest
) -> Any:
    """Produce a differentiated version of an existing lesson.

    Reuses ``clawed.differentiation.generate_iep_lesson_modifications`` by
    building a synthetic profile for the requested learner type. The result
    is persisted as a new lesson under the same unit so it gets its own
    viewable page and export links.
    """
    from clawed.differentiation import generate_iep_lesson_modifications
    from clawed.models import IEPProfile

    db = get_db()
    lesson_row = db.get_lesson(lesson_id)
    if not lesson_row:
        return JSONResponse({"error": "Lesson not found."}, status_code=404)

    try:
        lesson = DailyLesson.model_validate_json(lesson_row["lesson_json"])
    except Exception:
        logger.error(
            "Could not parse lesson %s for differentiation", lesson_id, exc_info=True
        )
        return JSONResponse(
            {"error": "This lesson's data is corrupted and cannot be differentiated."},
            status_code=400,
        )

    spec = _DIFFERENTIATION_PROFILES[req.profile]
    label = _PROFILE_LABELS[req.profile]
    profile = IEPProfile(
        student_name=label,
        disability_type=label,
        accommodations=spec["accommodations"],
        modifications=spec["modifications"],
        goals=spec["goals"],
    )

    try:
        modified = await generate_iep_lesson_modifications(lesson, [profile])
    except Exception:
        logger.error("Differentiation failed for lesson %s", lesson_id, exc_info=True)
        return JSONResponse(
            {"error": "Differentiation failed. Please try again."},
            status_code=500,
        )

    new_lesson = modified.get(label)
    if new_lesson is None:
        return JSONResponse(
            {"error": "Differentiation produced no output. Please try again."},
            status_code=502,
        )

    new_lesson.title = f"{lesson.title} ({label})"
    new_id = db.insert_lesson(
        unit_id=lesson_row["unit_id"],
        lesson_number=lesson.lesson_number,
        title=new_lesson.title,
        lesson_json=new_lesson.model_dump_json(),
    )

    return {
        "lesson_id": new_id,
        "source_lesson_id": lesson_id,
        "profile": req.profile,
        "title": new_lesson.title,
        "lesson": new_lesson.model_dump(),
    }


@router.post("/game")
@limiter.limit("5/minute")
async def create_game(request: Request, req: GameRequest) -> Any:
    """Generate an interactive HTML review game.

    Reuses ``clawed.compile_game.compile_game``. The generated single-file
    HTML game is written to the output directory; we return a URL that
    serves it via ``GET /api/game/file``.
    """
    from clawed.compile_game import compile_game
    from clawed.master_content import MasterContent

    db = get_db()
    persona, _ = _get_persona(db)

    # compile_game accepts MasterContent or any object exposing the lesson
    # fields it reads. A minimal stub is sufficient — the compiler fills the
    # rest with defaults (matching the agent_core game tool).
    master = MasterContent(  # type: ignore[call-arg]
        title=f"{req.topic} Review Game",
        subject=req.subject,
        grade_level=req.grade_level,
        topic=req.topic,
        objective=f"Review and reinforce {req.topic} concepts",
    )

    try:
        game_path = await compile_game(
            master=master,
            persona=persona,
            output_dir=None,
            game_style=req.game_type,
        )
    except Exception:
        logger.error("Game generation failed", exc_info=True)
        return JSONResponse(
            {"error": "Game generation failed. Please try again."},
            status_code=500,
        )

    from urllib.parse import quote

    return {
        "topic": req.topic,
        "filename": game_path.name,
        "game_url": f"/api/game/file?name={quote(game_path.name)}",
    }


@router.get("/game/file")
@limiter.limit("60/minute")
async def serve_game_file(request: Request, name: str) -> Any:
    """Serve a generated game HTML file by name from the output directory.

    Only plain ``.html`` filenames inside the output directory are served;
    any path separators or traversal attempts are rejected.
    """
    from fastapi.responses import FileResponse

    from clawed.io import output_dir as get_output_dir

    # Reject anything that is not a bare filename to prevent path traversal.
    if name != Path(name).name or "/" in name or "\\" in name:
        return JSONResponse({"error": "Invalid file name."}, status_code=400)
    if not name.endswith(".html"):
        return JSONResponse({"error": "Invalid file type."}, status_code=400)

    base = get_output_dir().resolve()
    target = (base / name).resolve()
    # Confine to the output directory and require the file to exist.
    if base not in target.parents or not target.is_file():
        return JSONResponse({"error": "Game not found."}, status_code=404)

    return FileResponse(str(target), media_type="text/html")


@router.post("/full")
@limiter.limit("10/minute")
async def full_pipeline(request: Request, req: FullRequest) -> Any:
    """End-to-end: generate unit + all lessons + materials. Returns SSE progress events."""
    from clawed.lesson import generate_lesson
    from clawed.materials import generate_all_materials
    from clawed.planner import plan_unit

    db = get_db()
    persona, teacher_id = _get_persona(db)
    if not persona or teacher_id is None:
        return JSONResponse(
            {"error": "No persona found."}, status_code=400
        )

    async def event_stream() -> AsyncGenerator[dict[str, str], None]:
        yield _sse(
            "progress", step="unit", status="generating",
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
            yield _sse(
                "error", error="Unit generation failed. Please try again."
            )
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
            "progress", step="unit", status="done",
            unit_id=unit_id, title=unit.title,
            lesson_count=len(unit.daily_lessons),
        )

        briefs = unit.daily_lessons
        if req.max_lessons:
            briefs = briefs[: req.max_lessons]

        lesson_ids: list[str] = []
        for brief in briefs:
            yield _sse(
                "progress", step="lesson", status="generating",
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
                    "progress", step="lesson", status="error",
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
                "progress", step="lesson", status="done",
                lesson_id=lid,
                lesson_number=lesson.lesson_number,
                title=lesson.title,
            )

        # ED-6 audit fix: track material generation failures instead of
        # silently swallowing them. Emit warnings and include a summary.
        materials_total = 0
        materials_failed = 0

        for lid in lesson_ids:
            lesson_row = db.get_lesson(lid)
            if not lesson_row:
                continue

            materials_total += 1
            yield _sse(
                "progress", step="materials",
                status="generating", lesson_id=lid,
            )

            lesson_obj = DailyLesson.model_validate_json(
                lesson_row["lesson_json"]
            )
            lesson_title = lesson_obj.title or f"Lesson {lid}"

            try:
                materials = await generate_all_materials(
                    lesson_obj, persona
                )
                db.update_lesson_materials(
                    lid, materials.model_dump_json()
                )
            except Exception as exc:
                materials_failed += 1
                logger.warning(
                    "materials generation failed for lesson %s: %s",
                    lid, exc,
                )
                yield _sse(
                    "warning",
                    message=f"Materials generation failed for {lesson_title}",
                )

            yield _sse(
                "progress", step="materials",
                status="done", lesson_id=lid,
            )

        yield _sse(
            "summary",
            total=materials_total,
            failed=materials_failed,
        )

        yield _sse(
            "done", unit_id=unit_id,
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
) -> Any:
    """Stream unit plan generation via SSE (GET for EventSource)."""
    from clawed.planner import plan_unit

    db = get_db()
    persona, teacher_id = _get_persona(db)
    if not persona or teacher_id is None:
        return JSONResponse(
            {"error": "No persona found."}, status_code=400
        )

    async def event_stream() -> AsyncGenerator[dict[str, str], None]:
        yield _sse(
            "progress", status="planning_unit",
            progress=10, message="Planning unit structure...",
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
            "progress", status="unit_complete", progress=100,
            unit_id=unit_id, title=unit.title,
            lesson_count=len(unit.daily_lessons),
        )
        yield _sse("done", unit_id=unit_id)

    return EventSourceResponse(event_stream())


@router.get("/stream/lesson")
@limiter.limit("10/minute")
async def stream_lesson(request: Request, unit_id: str, lesson_number: int = 1) -> Any:
    """Stream single lesson generation via SSE (GET for EventSource)."""
    from clawed.lesson import generate_lesson

    db = get_db()
    persona, _ = _get_persona(db)
    if not persona:
        return JSONResponse(
            {"error": "No persona found."}, status_code=400
        )

    unit_row = db.get_unit(unit_id)
    if not unit_row:
        return JSONResponse(
            {"error": "Unit not found."}, status_code=404
        )

    unit = UnitPlan.model_validate_json(unit_row["unit_json"])

    async def event_stream() -> AsyncGenerator[dict[str, str], None]:
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
            "progress", status="lesson_complete",
            progress=100, lesson_id=lid, title=lesson.title,
        )
        yield _sse("done", lesson_id=lid)

    return EventSourceResponse(event_stream())


@router.post("/course")
@limiter.limit("10/minute")
async def create_course(request: Request, req: CourseRequest) -> Any:
    """Generate a full course structure — year plan from a list of topics."""
    from clawed.planner import plan_unit

    db = get_db()
    persona, teacher_id = _get_persona(db)
    if not persona or teacher_id is None:
        return JSONResponse(
            {"error": "No persona found."}, status_code=400
        )

    async def event_stream() -> AsyncGenerator[dict[str, str], None]:
        total = len(req.topics)
        course_units: list[dict[str, Any]] = []

        for i, topic in enumerate(req.topics, 1):
            pct = int((i - 1) / total * 100)
            yield _sse(
                "progress", status="generating_unit",
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
                    "progress", status="error",
                    message=f"Failed to plan '{topic}'. Skipping.",
                )
                course_units.append(
                    {"topic": topic, "error": "Generation failed."}
                )
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
                "lesson_titles": [
                    b.topic for b in unit.daily_lessons
                ],
            }
            course_units.append(unit_summary)

            yield _sse(
                "progress", status="unit_done",
                progress=int(i / total * 100),
                unit=unit_summary,
            )

        successful = [
            u for u in course_units if "unit_id" in u
        ]
        yield _sse(
            "done", course=course_units,
            total_units=len(successful),
        )

    return EventSourceResponse(event_stream())


@router.get("/score/{lesson_id}")
@limiter.limit("60/minute")
async def score_lesson(request: Request, lesson_id: str) -> Any:
    """Score a lesson on quality dimensions."""
    from clawed.quality import LessonQualityScore

    db = get_db()
    lesson_row = db.get_lesson(lesson_id)
    if not lesson_row:
        return JSONResponse(
            {"error": "Lesson not found."}, status_code=404
        )

    lesson = DailyLesson.model_validate_json(lesson_row["lesson_json"])
    materials = None
    if lesson_row.get("materials_json"):
        from clawed.models import LessonMaterials

        materials = LessonMaterials.model_validate_json(
            lesson_row["materials_json"]
        )

    scorer = LessonQualityScore()
    scores = await scorer.score(lesson, materials)

    # Store scores in DB
    db.update_lesson_scores(lesson_id, json.dumps(scores))

    return {"lesson_id": lesson_id, "scores": scores}


@router.post("/suggest/{lesson_id}")
@limiter.limit("10/minute")
async def suggest_improvements_endpoint(request: Request, lesson_id: str) -> Any:
    """Generate improvement suggestions for a lesson."""
    from clawed.improver import suggest_improvements

    db = get_db()
    lesson_row = db.get_lesson(lesson_id)
    if not lesson_row:
        return JSONResponse(
            {"error": "Lesson not found."}, status_code=404
        )

    lesson = DailyLesson.model_validate_json(lesson_row["lesson_json"])

    # Check for feedback notes
    feedback_list = db.get_feedback_for_lesson(lesson_id)
    notes = " | ".join(
        f["notes"] for f in feedback_list if f.get("notes")
    )

    suggestions = await suggest_improvements(
        lesson, feedback_notes=notes
    )
    return {"lesson_id": lesson_id, "suggestions": suggestions}


@router.post("/improve/{lesson_id}")
@limiter.limit("10/minute")
async def improve_lesson_endpoint(
    request: Request, lesson_id: str, req: ImproveRequest
) -> Any:
    """Apply a plain-English revision to a lesson in place ("Revise in plain English").

    The teacher types a natural-language change (e.g. "make it shorter",
    "add a primary source", "lower the reading level to 9th grade",
    "add Regents-style questions"). We load the existing lesson, ask the
    LLM to apply ONLY that change and return the full revised lesson as
    JSON, re-validate it against ``DailyLesson``, and persist it under the
    same ``lesson_id`` (``update_lesson_json`` bumps ``edit_count``). No
    full regeneration — unchanged sections are preserved verbatim.
    """
    from clawed.llm import LLMClient

    instruction = req.instruction.strip()
    if not instruction:
        return JSONResponse(
            {"error": "Please describe the change you want."}, status_code=400
        )

    db = get_db()
    lesson_row = db.get_lesson(lesson_id)
    if not lesson_row:
        return JSONResponse({"error": "Lesson not found."}, status_code=404)

    try:
        lesson = DailyLesson.model_validate_json(lesson_row["lesson_json"])
    except Exception:
        logger.error("Could not parse lesson %s for revision", lesson_id, exc_info=True)
        return JSONResponse(
            {"error": "This lesson's data is corrupted and cannot be revised."},
            status_code=400,
        )

    # Reuse the same persona-as-voice context the generation pipeline uses,
    # so revisions stay in the teacher's voice and grade band.
    persona, _ = _get_persona(db)
    persona_context = ""
    if persona is not None:
        try:
            persona_context = persona.to_prompt_context()
        except Exception:
            # Persona context is best-effort; revisions still work without it.
            persona_context = ""

    current_json = lesson.model_dump_json(indent=2)
    prompt = (
        "You are an expert curriculum editor. A teacher has an existing daily "
        "lesson (given below as JSON) and wants ONE specific change applied.\n\n"
        f"{persona_context}\n\n"
        f"## Existing lesson (JSON)\n{current_json}\n\n"
        f"## Teacher's requested change\n{instruction}\n\n"
        "## Instructions\n"
        "1. Apply ONLY the requested change. Leave every other section exactly "
        "as it is — do not rewrite content that the change does not touch.\n"
        "2. Keep the SAME JSON shape and keys as the input. Do not add, rename, "
        "or drop keys. Preserve the 'lesson_number' value unchanged.\n"
        "3. Keep the teacher's voice, formatting, and standards alignment.\n"
        "4. 'exit_ticket' is a list of objects with 'question' and "
        "'expected_response'. 'differentiation' has 'struggling', 'advanced', "
        "and 'ell' string lists.\n\n"
        "Return ONLY the complete revised lesson as a single JSON object — no "
        "prose, no markdown fences."
    )

    try:
        client = LLMClient()
        raw = await client.generate_json(
            prompt=prompt,
            system=(
                "You are a curriculum editor. Return only one JSON object: the "
                "full revised lesson, same schema as the input."
            ),
            temperature=0.4,
            max_tokens=8192,
        )
    except Exception:
        logger.error("Revision LLM call failed for lesson %s", lesson_id, exc_info=True)
        return JSONResponse(
            {"error": "Could not apply that change right now. Please try again."},
            status_code=502,
        )

    # generate_json returns a dict; force the lesson number to stay stable even
    # if the model changed it. (Any schema problems are caught by validation below.)
    raw["lesson_number"] = lesson.lesson_number

    try:
        revised = DailyLesson.model_validate(raw)
    except Exception:
        logger.warning("Revised lesson %s failed validation", lesson_id, exc_info=True)
        return JSONResponse(
            {"error": "The revision didn't pass validation. Try a simpler change."},
            status_code=502,
        )

    db.update_lesson_json(lesson_id, revised.model_dump_json())

    return {
        "lesson_id": lesson_id,
        "ok": True,
        "summary": f"Applied: {instruction}",
    }


@router.get("/templates")
@limiter.limit("60/minute")
async def list_templates_endpoint(request: Request) -> dict[str, Any]:
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
async def list_units(request: Request) -> dict[str, Any]:
    """List all generated units."""
    db = get_db()
    units = db.list_units()
    for u in units:
        u["lesson_count"] = len(db.list_lessons(u["id"]))
    return {"units": units}


@router.get("/lessons/{unit_id}")
@limiter.limit("60/minute")
async def list_lessons(request: Request, unit_id: str) -> dict[str, Any]:
    """List all lessons for a unit."""
    db = get_db()
    lessons = db.list_lessons(unit_id)
    return {"lessons": lessons}


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000)
    grade_level: str = Field("", max_length=20)
    subject: str = Field("", max_length=100)


@router.post("/ask/stream")
@limiter.limit("30/minute")
async def ask_stream(request: Request, req: AskRequest) -> EventSourceResponse:
    """Stream a co-teacher answer token-by-token (live, like Claude Code).

    Open-ended teaching help — lesson ideas, rewrites, examples,
    differentiation. Uses the teacher's persona for voice when one exists,
    but works without ingestion too. Streams via the configured provider
    (e.g. OpenRouter / minimax-m3) so the answer appears as it's written.
    """
    from clawed.llm import LLMClient

    db = get_db()
    persona, _ = _get_persona(db)
    style = ""
    if persona is not None:
        try:
            style = persona.to_prompt_context()
        except Exception:
            style = ""

    system = (
        "You are Claw-ED, a warm, practical co-teacher for a K-12 teacher. "
        "Give concrete, classroom-ready help: lesson ideas, rewrites, worked "
        "examples, explanations, and differentiation. Be concise and useful, "
        "and format with short paragraphs or lists a teacher can use as-is."
    )
    if style:
        system += f"\n\nMatch this teacher's style where it fits:\n{style}"

    qualifiers = ""
    if req.subject:
        qualifiers += f" Subject: {req.subject}."
    if req.grade_level:
        qualifiers += f" Grade level: {req.grade_level}."
    user_prompt = req.question + (f"\n\n({qualifiers.strip()})" if qualifiers else "")

    async def event_stream() -> AsyncGenerator[dict[str, str], None]:
        client = LLMClient()
        produced = False
        try:
            async for chunk in client.generate_stream(
                user_prompt, system=system, temperature=0.7, max_tokens=1500
            ):
                produced = True
                yield _sse("token", text=chunk)
        except Exception:
            logger.error("ask_stream failed", exc_info=True)
            yield _sse(
                "error",
                error="Generation failed. Check your provider/API key in Settings.",
            )
            return
        if not produced:
            yield _sse(
                "error",
                error="No response. Check your provider/API key in Settings.",
            )
            return
        yield _sse("done")

    return EventSourceResponse(event_stream())
