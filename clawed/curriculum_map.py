"""Year-level curriculum mapping and pacing — the planning layer above units.

Teachers plan at three levels:
  1. Year map → full-year curriculum with 9-10 units, big ideas, assessment calendar
  2. Unit plan → detailed unit with lesson briefs (existing planner.py)
  3. Daily lessons → classroom-ready lesson plans (existing lesson.py)

This module provides level 1.
"""

from __future__ import annotations

from pathlib import Path

from clawed.corpus import get_few_shot_context
from clawed.llm import LLMClient
from clawed.model_router import route as route_model
from clawed.models import (
    AppConfig,
    CurriculumGap,
    PacingGuide,
    SchoolCalendarEvent,
    TeacherPersona,
    YearMap,
)

PROMPT_DIR = Path(__file__).parent / "prompts"


class CurriculumMapper:
    """Generates year-level curriculum plans: year maps, pacing guides, gap analysis."""

    def __init__(self, config: AppConfig | None = None):
        self.config = config or AppConfig.load()

    async def generate_year_map(
        self,
        subject: str,
        grade_level: str,
        standards: list[str] | None = None,
        persona: TeacherPersona | None = None,
        school_year: str = "",
        total_weeks: int = 36,
    ) -> YearMap:
        """Generate a full-year curriculum map.

        Args:
            subject: Academic subject (e.g., "Math", "Science").
            grade_level: Grade level string (e.g., "8", "K", "11-12").
            standards: Optional list of standards to align to.
            persona: Teacher persona for voice/style matching.
            school_year: School year label (e.g., "2025-26").
            total_weeks: Total instructional weeks in the year.

        Returns:
            A YearMap with units, big ideas, and assessment calendar.
        """
        persona = persona or TeacherPersona()

        few_shot_context = get_few_shot_context(
            content_type="year_map",
            subject=subject.lower(),
            grade_level=grade_level,
        )

        prompt_template = (PROMPT_DIR / "year_map.txt").read_text(encoding="utf-8")
        prompt = (
            prompt_template.replace("{persona}", persona.to_prompt_context())
            .replace("{subject}", subject)
            .replace("{grade_level}", grade_level)
            .replace("{standards}", ", ".join(standards) if standards else "Use appropriate grade-level standards")
            .replace("{school_year}", school_year or self.config.teacher_profile.school_year)
            .replace("{total_weeks}", str(total_weeks))
            .replace("{few_shot_context}", few_shot_context)
        )

        config = route_model("year_map", self.config)
        client = LLMClient(config)
        return await client.safe_generate_json(
            prompt=prompt,
            model_class=YearMap,
            system=(
                "You are an expert curriculum designer. Respond only with valid JSON matching the specified format."
            ),
            temperature=0.5,
            max_tokens=8192,
        )

    async def generate_pacing_guide(
        self,
        year_map: YearMap,
        start_date: str,
        school_calendar: list[SchoolCalendarEvent] | None = None,
        persona: TeacherPersona | None = None,
    ) -> PacingGuide:
        """Convert a YearMap into a week-by-week calendar with actual dates.

        Args:
            year_map: The year map to pace out.
            start_date: First instructional day (ISO format, e.g., "2025-09-04").
            school_calendar: Optional list of holidays, breaks, PD days.
            persona: Teacher persona for voice/style.

        Returns:
            A PacingGuide with weekly entries tied to real dates.
        """
        persona = persona or TeacherPersona()

        # Build a summary of the year map for the prompt
        unit_lines = []
        for u in year_map.units:
            unit_lines.append(f"  Unit {u.unit_number}: {u.title} ({u.duration_weeks} weeks) — {u.description}")
        year_map_summary = "\n".join(unit_lines)

        # Format calendar events
        if school_calendar:
            event_lines = []
            for evt in school_calendar:
                if evt.end_date and evt.end_date != evt.date:
                    event_lines.append(f"  {evt.date} to {evt.end_date}: {evt.event} ({evt.type})")
                else:
                    event_lines.append(f"  {evt.date}: {evt.event} ({evt.type})")
            calendar_events = "\n".join(event_lines)
        else:
            calendar_events = "No specific calendar events provided — use standard US school calendar assumptions."

        prompt_template = (PROMPT_DIR / "pacing_guide.txt").read_text(encoding="utf-8")
        prompt = (
            prompt_template.replace("{persona}", persona.to_prompt_context())
            .replace("{year_map_summary}", year_map_summary)
            .replace("{start_date}", start_date)
            .replace("{calendar_events}", calendar_events)
        )

        config = route_model("pacing_guide", self.config)
        client = LLMClient(config)
        return await client.safe_generate_json(
            prompt=prompt,
            model_class=PacingGuide,
            system=(
                "You are an expert curriculum pacing specialist. "
                "Respond only with valid JSON matching the specified format."
            ),
            temperature=0.4,
            max_tokens=12000,
        )

    async def identify_curriculum_gaps(
        self,
        existing_materials: list[str],
        standards: list[str],
        persona: TeacherPersona | None = None,
    ) -> list[CurriculumGap]:
        """Analyze a teacher's existing materials against standards and find gaps.

        Args:
            existing_materials: Summaries or titles of existing curriculum materials.
            standards: Standards codes/descriptions to check coverage against.
            persona: Teacher persona for context.

        Returns:
            A list of CurriculumGap objects describing what's missing.
        """
        persona = persona or TeacherPersona()

        if existing_materials:
            materials_summary = "\n".join(f"  - {m}" for m in existing_materials)
        else:
            materials_summary = "No materials provided."

        prompt_template = (PROMPT_DIR / "curriculum_gaps.txt").read_text(encoding="utf-8")
        prompt = (
            prompt_template.replace("{persona}", persona.to_prompt_context())
            .replace("{standards}", "\n".join(f"  - {s}" for s in standards))
            .replace("{materials_summary}", materials_summary)
        )

        config = route_model("curriculum_gaps", self.config)
        client = LLMClient(config)
        data = await client.generate_json(
            prompt=prompt,
            system=(
                "You are an expert curriculum alignment specialist. "
                "Respond only with a valid JSON array matching the specified format."
            ),
            temperature=0.3,
            max_tokens=8192,
        )

        # Response is a JSON array
        if isinstance(data, list):
            return [CurriculumGap.model_validate(item) for item in data]
        # Handle case where LLM wraps in an object
        if isinstance(data, dict) and "gaps" in data:
            return [CurriculumGap.model_validate(item) for item in data["gaps"]]
        return []


# ── Convenience functions ─────────────────────────────────────────────────


def save_year_map(year_map: YearMap, output_dir: Path) -> Path:
    """Save a year map to disk as JSON."""
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_name = f"year_map_{year_map.subject.lower().replace(' ', '_')}_{year_map.grade_level}"
    path = output_dir / f"{safe_name}.json"
    path.write_text(year_map.model_dump_json(indent=2), encoding="utf-8")
    return path


def load_year_map(path: Path) -> YearMap:
    """Load a year map from a JSON file."""
    if not path.exists():
        raise FileNotFoundError(f"Year map file not found: {path}")
    return YearMap.model_validate_json(path.read_text(encoding="utf-8"))


def save_pacing_guide(guide: PacingGuide, output_dir: Path) -> Path:
    """Save a pacing guide to disk as JSON."""
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_name = f"pacing_{guide.subject.lower().replace(' ', '_')}_{guide.grade_level}"
    path = output_dir / f"{safe_name}.json"
    path.write_text(guide.model_dump_json(indent=2), encoding="utf-8")
    return path


def load_pacing_guide(path: Path) -> PacingGuide:
    """Load a pacing guide from a JSON file."""
    if not path.exists():
        raise FileNotFoundError(f"Pacing guide file not found: {path}")
    return PacingGuide.model_validate_json(path.read_text(encoding="utf-8"))
