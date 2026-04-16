"""Materials generator — produces worksheets, assessments, rubrics, slides, and IEP notes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel as PydanticBaseModel
from pydantic import Field, model_validator

from clawed.llm import LLMClient
from clawed.model_router import route as route_model
from clawed.models import (
    AppConfig,
    AssessmentQuestion,
    DailyLesson,
    LessonMaterials,
    RubricCriterion,
    SlideOutline,
    TeacherPersona,
    WorksheetItem,
)

PROMPT_DIR = Path(__file__).parent / "prompts"


# ── Wrapper models for safe_generate_json (list-returning generators) ────


class _WorksheetResult(PydanticBaseModel):
    items: list[WorksheetItem]

    @model_validator(mode="before")
    @classmethod
    def _wrap_list(cls, data: Any) -> Any:
        if isinstance(data, list):
            return {"items": data}
        return data


class _AssessmentResult(PydanticBaseModel):
    questions: list[AssessmentQuestion] = Field(default_factory=list)
    rubric: list[RubricCriterion] = Field(default_factory=list)


class _SlidesResult(PydanticBaseModel):
    slides: list[SlideOutline]

    @model_validator(mode="before")
    @classmethod
    def _wrap_list(cls, data: Any) -> Any:
        if isinstance(data, list):
            return {"slides": data}
        return data


class _IEPNotesResult(PydanticBaseModel):
    notes: list[str]

    @model_validator(mode="before")
    @classmethod
    def _wrap_list(cls, data: Any) -> Any:
        if isinstance(data, list):
            return {"notes": data}
        return data


def _lesson_key_concepts(lesson: DailyLesson) -> str:
    """Extract key concepts from a lesson for prompt context."""
    return f"{lesson.objective}. Topics: {lesson.title}."


# ── Worksheet generation ─────────────────────────────────────────────────


async def generate_worksheet(
    lesson: DailyLesson,
    persona: TeacherPersona,
    config: AppConfig | None = None,
    task_type: str = "materials",
) -> list[WorksheetItem]:
    """Generate a student worksheet for a lesson."""
    prompt_template = (PROMPT_DIR / "worksheet.txt").read_text(encoding="utf-8")
    prompt = (
        prompt_template
        .replace("{persona}", persona.to_prompt_context())
        .replace("{lesson_title}", lesson.title)
        .replace("{objective}", lesson.objective)
        .replace("{grade_level}", ", ".join(persona.grade_levels) or "Not specified")
        .replace("{subject}", persona.subject_area or "General")
        .replace("{key_concepts}", _lesson_key_concepts(lesson))
    )

    if task_type and config:
        config = route_model(task_type, config)
    client = LLMClient(config)
    result = await client.safe_generate_json(
        prompt=prompt,
        model_class=_WorksheetResult,
        system="You are an expert worksheet designer. Respond only with a valid JSON array.",
        temperature=0.5,
    )
    return result.items


# ── Assessment generation ────────────────────────────────────────────────


async def generate_assessment(
    lesson: DailyLesson,
    persona: TeacherPersona,
    config: AppConfig | None = None,
    task_type: str = "materials",
) -> tuple[list[AssessmentQuestion], list[RubricCriterion]]:
    """Generate a quiz/assessment with optional rubric for a lesson."""
    prompt_template = (PROMPT_DIR / "assessment.txt").read_text(encoding="utf-8")
    prompt = (
        prompt_template
        .replace("{persona}", persona.to_prompt_context())
        .replace("{lesson_title}", lesson.title)
        .replace("{objective}", lesson.objective)
        .replace("{grade_level}", ", ".join(persona.grade_levels) or "Not specified")
        .replace("{subject}", persona.subject_area or "General")
        .replace("{key_concepts}", _lesson_key_concepts(lesson))
    )

    if task_type and config:
        config = route_model(task_type, config)
    client = LLMClient(config)
    result = await client.safe_generate_json(
        prompt=prompt,
        model_class=_AssessmentResult,
        system="You are an expert assessment designer. Respond only with valid JSON.",
        temperature=0.4,
    )
    return result.questions, result.rubric


# ── Slide outline generation ─────────────────────────────────────────────


async def generate_slides(
    lesson: DailyLesson,
    persona: TeacherPersona,
    config: AppConfig | None = None,
    task_type: str = "materials",
) -> list[SlideOutline]:
    """Generate a slide deck outline for a lesson."""
    prompt = (
        f"You are creating a slide deck outline for a lesson.\n\n"
        f"## Teacher Persona\n{persona.to_prompt_context()}\n\n"
        f"## Lesson\n"
        f"- Title: {lesson.title}\n"
        f"- Objective: {lesson.objective}\n"
        f"- Direct Instruction Content:\n{lesson.direct_instruction[:1500]}\n\n"
        f"## Task\n"
        f"Create a slide deck with a title slide and 6-8 content slides.\n"
        f"Each slide should have a clear title, 3-5 bullet points, and speaker notes.\n\n"
        f"## Output Format\n"
        f"Respond with ONLY a JSON array:\n"
        f'[{{"slide_number": 1, "title": "Title", "content_bullets": ["..."], "speaker_notes": "..."}}]'
    )

    if task_type and config:
        config = route_model(task_type, config)
    client = LLMClient(config)
    result = await client.safe_generate_json(
        prompt=prompt,
        model_class=_SlidesResult,
        system="You are a presentation designer. Respond only with a valid JSON array.",
        temperature=0.5,
    )
    return result.slides


# ── IEP / Differentiation notes ─────────────────────────────────────────


async def generate_iep_notes(
    lesson: DailyLesson,
    persona: TeacherPersona,
    config: AppConfig | None = None,
    task_type: str = "differentiation",
) -> list[str]:
    """Generate IEP accommodation and differentiation notes for a lesson."""
    prompt_template = (PROMPT_DIR / "differentiation.txt").read_text(encoding="utf-8")

    lesson_activities = (
        f"Do-Now: {lesson.do_now[:200]}\n"
        f"Direct Instruction: {lesson.direct_instruction[:300]}\n"
        f"Guided Practice: {lesson.guided_practice[:300]}\n"
        f"Independent Work: {lesson.independent_work[:200]}"
    )

    prompt = (
        prompt_template
        .replace("{persona}", persona.to_prompt_context())
        .replace("{lesson_title}", lesson.title)
        .replace("{objective}", lesson.objective)
        .replace("{grade_level}", ", ".join(persona.grade_levels) or "Not specified")
        .replace("{subject}", persona.subject_area or "General")
        .replace("{lesson_activities}", lesson_activities)
    )

    if task_type and config:
        config = route_model(task_type, config)
    client = LLMClient(config)
    result = await client.safe_generate_json(
        prompt=prompt,
        model_class=_IEPNotesResult,
        system="You are a differentiation specialist. Respond only with a valid JSON array of strings.",
        temperature=0.5,
    )
    return result.notes


# ── Full materials generation ────────────────────────────────────────────


async def generate_all_materials(
    lesson: DailyLesson,
    persona: TeacherPersona,
    config: AppConfig | None = None,
) -> LessonMaterials:
    """Generate all materials for a lesson: worksheet, assessment, rubric, slides, IEP notes."""
    worksheet = await generate_worksheet(lesson, persona, config)
    questions, rubric = await generate_assessment(lesson, persona, config)
    slides = await generate_slides(lesson, persona, config)
    iep_notes = await generate_iep_notes(lesson, persona, config)

    return LessonMaterials(
        lesson_title=lesson.title,
        worksheet_items=worksheet,
        assessment_questions=questions,
        rubric=rubric,
        slide_outline=slides,
        iep_notes=iep_notes,
    )


def save_materials(materials: LessonMaterials, output_dir: Path) -> Path:
    """Save materials to disk as JSON."""
    from clawed.io import safe_filename, write_text

    output_dir.mkdir(parents=True, exist_ok=True)
    safe_title = safe_filename(materials.lesson_title, max_len=50)
    path = output_dir / f"materials_{safe_title}.json"
    write_text(path, materials.model_dump_json(indent=2))
    return path
