"""Unit and curriculum planner — generates structured unit plans via LLM."""

from __future__ import annotations

from pathlib import Path

from clawed.corpus import get_few_shot_context
from clawed.llm import LLMClient
from clawed.model_router import route as route_model
from clawed.models import AppConfig, TeacherPersona, UnitPlan

PROMPT_PATH = Path(__file__).parent / "prompts" / "unit_plan.txt"


async def plan_unit(
    subject: str,
    grade_level: str,
    topic: str,
    duration_weeks: int,
    persona: TeacherPersona,
    standards: list[str] | None = None,
    config: AppConfig | None = None,
    task_type: str = "unit_plan",
) -> UnitPlan:
    """Generate a complete unit plan aligned to the teacher's persona.

    Args:
        subject: The academic subject (e.g., "Science", "ELA").
        grade_level: Grade level string (e.g., "8", "K", "11-12").
        topic: The unit topic (e.g., "Photosynthesis").
        duration_weeks: Number of weeks for the unit.
        persona: The teacher persona to match in voice and style.
        standards: Optional list of standards to align to.
        config: Optional app config override.

    Returns:
        A fully populated UnitPlan.
    """
    # Estimate ~5 lessons per week
    total_lessons = duration_weeks * 5

    # Pull few-shot examples from the corpus for this subject/grade
    few_shot_context = get_few_shot_context(
        content_type="unit_plan",
        subject=subject.lower(),
        grade_level=grade_level,
    )

    # Auto-resolve standards if none were provided
    if not standards:
        from clawed.standards import get_standards_for_lesson

        effective_state = ""
        if config:
            effective_state = (getattr(config, "teacher_profile", None) and config.teacher_profile.state) or ""
        standards = get_standards_for_lesson(
            subject=subject,
            grade=grade_level,
            state=effective_state,
            topic=topic,
        )

    prompt_template = PROMPT_PATH.read_text(encoding="utf-8")
    prompt = (
        prompt_template
        .replace("{persona}", persona.to_prompt_context())
        .replace("{subject}", subject)
        .replace("{grade_level}", grade_level)
        .replace("{topic}", topic)
        .replace("{duration_weeks}", str(duration_weeks))
        .replace("{total_lessons}", str(total_lessons))
        .replace("{standards}", "\n".join(f"  - {s}" for s in standards))
        .replace("{few_shot_context}", few_shot_context)
    )

    if task_type and config:
        config = route_model(task_type, config)
    client = LLMClient(config)
    return await client.safe_generate_json(
        prompt=prompt,
        model_class=UnitPlan,
        system=(
            "You are an expert curriculum designer. "
            "Respond only with valid JSON matching the specified format."
        ),
        temperature=0.5,
        max_tokens=6000,
    )


def save_unit(unit: UnitPlan, output_dir: Path) -> Path:
    """Save a unit plan to disk as JSON."""
    from clawed.io import safe_filename, write_text

    output_dir.mkdir(parents=True, exist_ok=True)
    safe_title = safe_filename(unit.title, max_len=50)
    path = output_dir / f"unit_{safe_title}.json"
    write_text(path, unit.model_dump_json(indent=2))
    return path


def load_unit(path: Path) -> UnitPlan:
    """Load a unit plan from a JSON file."""
    if not path.exists():
        raise FileNotFoundError(f"Unit plan file not found: {path}")
    return UnitPlan.model_validate_json(path.read_text(encoding="utf-8"))
