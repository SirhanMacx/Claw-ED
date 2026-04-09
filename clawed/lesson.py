"""Lesson plan generator — creates detailed daily lesson plans via LLM."""

from __future__ import annotations

from pathlib import Path

from clawed.corpus import get_few_shot_context
from clawed.llm import LLMClient
from clawed.master_content import MasterContent
from clawed.model_router import route as route_model
from clawed.models import AppConfig, DailyLesson, TeacherPersona, UnitPlan

# NOTE: lesson_plan.txt is kept for reference / backward compatibility but is
# NOT used for primary lesson generation.  All lesson generation goes through
# generate_lesson() → generate_master_content() which uses master_content.txt.
#
# ⚠️  master_content.txt IS SUPERIOR to lesson_plan.txt — it requires:
#   - Stimulus-based Do Nows (never recall)
#   - Mandatory image_spec fields for every direct-instruction section
#   - Full primary-source excerpts with scaffolding questions
#   - Guided notes with fill-in-the-blank entries
#   - Station tasks referencing primary sources
#   - Richer exit-ticket schema (StimulusQuestion with cognitive_level)
#
# If you are debugging generation quality, edit master_content.txt — changes to
# lesson_plan.txt will NOT affect the live output.
PROMPT_PATH = Path(__file__).parent / "prompts" / "lesson_plan.txt"
MASTER_PROMPT_PATH = Path(__file__).parent / "prompts" / "master_content.txt"


def _build_system_prompt(
    persona: TeacherPersona,
    config: AppConfig | None,
    subject: str = "",
) -> str:
    """Build the rich system prompt shared by both generation paths.

    The prompt is subject-aware: it loads the appropriate SubjectSkill
    for the lesson's subject (not just the persona's default subject),
    preventing Social Studies patterns from bleeding into Math lessons.
    """
    persona_context = persona.to_prompt_context() if persona else ""
    soul_context = ""
    try:
        import os
        data_dir = os.environ.get(
            "EDUAGENT_DATA_DIR", str(Path.home() / ".eduagent")
        )
        soul_path = Path(data_dir) / "workspace" / "soul.md"
        if soul_path.exists():
            soul_context = soul_path.read_text(encoding="utf-8")[:2000]
    except Exception:
        pass

    # Base prompt — subject-neutral. Specific pedagogy comes from skills.
    system_parts = [
        "You are an expert lesson plan writer who EXACTLY replicates "
        "this teacher's pedagogical fingerprint in EVERY lesson. "
        "Match their voice, tone, scaffolding patterns, activity structures, "
        "Do Now format, and signature teaching moves. If the persona describes "
        "specific techniques, use those EXACT techniques — not generic alternatives.",
    ]

    # Load subject-specific skill for THIS lesson's subject
    effective_subject = subject or (persona.subject_area if persona else "")
    if effective_subject:
        try:
            from clawed.skills import SkillLibrary
            library = SkillLibrary()
            skill = library.get(effective_subject)
            if skill:
                system_parts.append(skill.to_system_context())
        except Exception:
            pass

    if persona_context:
        system_parts.append(persona_context)
    if soul_context:
        system_parts.append(soul_context)
    system_parts.append(
        "Respond only with valid JSON matching the specified format. "
        "Do NOT use XML tags, angle brackets, or markdown formatting "
        "in the JSON values."
    )

    # NYS Regents assessment format for Social Studies
    if (config and hasattr(config, "teacher_profile") and config.teacher_profile
            and getattr(config.teacher_profile, "state", "") == "NY"
            and "social studies" in effective_subject.lower()):
        system_parts.append(
            "NYS Regents Assessment Format Requirements:\n"
            "- Exit ticket questions MUST use Stimulus-Based Multiple "
            "Choice Question (SBMCQ) format:\n"
            "  Each question includes a stimulus (primary source excerpt, "
            "map, chart, or political cartoon) followed by 4 answer choices.\n"
            "- Include at least one Constructed Response Question (CRQ):\n"
            "  Context → Source → Questions (identify, explain, "
            "analyze/evaluate).\n"
            "- All assessment items must reference specific historical "
            "evidence from the sources provided."
        )

    return "\n\n".join(system_parts)


async def generate_master_content(
    lesson_number: int,
    unit: UnitPlan,
    persona: TeacherPersona,
    include_homework: bool = True,
    config: AppConfig | None = None,
    task_type: str = "master_content",
    state: str = "",
    teacher_materials: str = "",
    objective: str = "",
) -> MasterContent:
    """Generate a MasterContent object — single source-of-truth for a lesson.

    All output documents (teacher plan, student packet, slides) are compiled
    as views of the returned ``MasterContent``.  Parameters mirror
    ``generate_lesson()`` for drop-in compatibility, with the addition of
    *objective*.

    Args:
        lesson_number: Which lesson in the unit (1-indexed).
        unit: The parent unit plan for context.
        persona: Teacher persona to match.
        include_homework: Whether to generate a homework assignment.
        config: Optional app config override.
        task_type: Model-routing hint.
        state: US state code for standards lookup.
        teacher_materials: Pre-formatted teacher materials context.
        objective: Explicit lesson objective (derived from brief if empty).

    Returns:
        A fully populated MasterContent.
    """
    # Find the matching lesson brief from the unit plan
    lesson_brief = None
    for brief in unit.daily_lessons:
        if brief.lesson_number == lesson_number:
            lesson_brief = brief
            break

    if lesson_brief is None:
        raise ValueError(
            f"Lesson {lesson_number} not found in unit plan. "
            f"Unit has {len(unit.daily_lessons)} lessons."
        )

    # Auto-populate unit standards from teacher profile if missing
    if not unit.standards:
        try:
            config = config or AppConfig.load()
            if config.teacher_profile and config.teacher_profile.state:
                from clawed.standards import get_standards
                results = get_standards(unit.subject, unit.grade_level)
                unit.standards = [
                    f"{code}: {desc}" for code, desc, _ in results[:5]
                ]
        except Exception:
            pass

    # Pull few-shot examples from the corpus for this subject/grade
    few_shot_context = get_few_shot_context(
        content_type="lesson_plan",
        subject=unit.subject.lower(),
        grade_level=unit.grade_level,
    )

    # Look up applicable standards for this lesson
    from clawed.standards import format_standards_for_prompt, get_standards_for_lesson

    effective_state = state
    if not effective_state and config:
        effective_state = getattr(config, "teacher_profile", None) and config.teacher_profile.state or ""
    standards_list = get_standards_for_lesson(
        subject=unit.subject,
        grade=unit.grade_level,
        state=effective_state,
        topic=lesson_brief.topic,
    )
    standards_text = format_standards_for_prompt(standards_list)

    # Derive objective from lesson brief if not explicitly provided
    effective_objective = objective or getattr(lesson_brief, "description", "")

    prompt_template = MASTER_PROMPT_PATH.read_text(encoding="utf-8")
    prompt = (
        prompt_template
        .replace("{unit_title}", unit.title)
        .replace("{unit_overview}", unit.overview[:1500])
        .replace("{subject}", unit.subject)
        .replace("{grade_level}", unit.grade_level)
        .replace("{topic}", lesson_brief.topic)
        .replace("{objective}", effective_objective)
        .replace("{lesson_number}", str(lesson_number))
        .replace("{total_lessons}", str(len(unit.daily_lessons)))
        .replace("{duration_minutes}", "45")
        .replace("{standards}", standards_text)
        .replace("{few_shot_context}", few_shot_context)
        .replace("{teacher_materials}", teacher_materials)
        .replace("{standards_framework}", (
            config.teacher_profile.standards_framework
            if config and config.teacher_profile
            else "state standards"
        ))
        .replace("{state}", (
            config.teacher_profile.state
            if config and config.teacher_profile
            else ""
        ))
    )

    system = _build_system_prompt(persona, config, subject=unit.subject)

    if task_type and config:
        config = route_model(task_type, config)
    client = LLMClient(config)
    return await client.safe_generate_json(
        prompt=prompt,
        model_class=MasterContent,
        system=system,
        temperature=0.6,
        max_tokens=12000,
    )


async def generate_lesson(
    lesson_number: int,
    unit: UnitPlan,
    persona: TeacherPersona,
    include_homework: bool = True,
    config: AppConfig | None = None,
    task_type: str = "master_content",
    state: str = "",
    teacher_materials: str = "",
) -> DailyLesson:
    """Generate a complete daily lesson plan for a specific lesson in a unit.

    Internally generates a ``MasterContent`` object and converts it to a
    ``DailyLesson`` for backward compatibility with all existing callers.

    Args:
        lesson_number: Which lesson in the unit (1-indexed).
        unit: The parent unit plan for context.
        persona: Teacher persona to match.
        include_homework: Whether to generate a homework assignment.
        config: Optional app config override.
        task_type: Model-routing hint.
        state: US state code for standards lookup.
        teacher_materials: Pre-formatted teacher materials context.

    Returns:
        A fully populated DailyLesson.
    """
    master = await generate_master_content(
        lesson_number=lesson_number,
        unit=unit,
        persona=persona,
        include_homework=include_homework,
        config=config,
        task_type=task_type,
        state=state,
        teacher_materials=teacher_materials,
    )
    daily = master.to_daily_lesson()
    daily.lesson_number = lesson_number
    return daily


async def generate_all_lessons(
    unit: UnitPlan,
    persona: TeacherPersona,
    include_homework: bool = True,
    config: AppConfig | None = None,
    teacher_materials: str = "",
) -> list[DailyLesson]:
    """Generate lesson plans for every lesson in a unit sequentially."""
    lessons: list[DailyLesson] = []
    for brief in unit.daily_lessons:
        lesson = await generate_lesson(
            lesson_number=brief.lesson_number,
            unit=unit,
            persona=persona,
            include_homework=include_homework,
            config=config,
            teacher_materials=teacher_materials,
        )
        lessons.append(lesson)
    return lessons


def save_lesson(lesson: DailyLesson, output_dir: Path) -> Path:
    """Save a lesson plan to disk as JSON."""
    from clawed.io import write_text

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"lesson_{lesson.lesson_number:02d}.json"
    write_text(path, lesson.model_dump_json(indent=2))
    return path


def load_lesson(path: Path) -> DailyLesson:
    """Load a lesson plan from a JSON file."""
    if not path.exists():
        raise FileNotFoundError(f"Lesson file not found: {path}")
    return DailyLesson.model_validate_json(path.read_text(encoding="utf-8"))
