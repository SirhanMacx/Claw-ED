"""Assessment intelligence — DBQ, summative, formative, quiz, and rubric generation."""

from __future__ import annotations

from pathlib import Path

from clawed.llm import LLMClient
from clawed.model_router import route as route_model
from clawed.models import (
    AppConfig,
    DailyLesson,
    DBQAssessment,
    FormativeAssessment,
    Quiz,
    Rubric,
    SummativeAssessment,
    TeacherPersona,
    UnitPlan,
)

PROMPT_DIR = Path(__file__).parent / "prompts"


class AssessmentGenerator:
    """Generates various assessment types with rubrics and answer keys."""

    def __init__(self, config: AppConfig | None = None) -> None:
        self.config = config

    def _routed_client(self, task_type: str = "assessment") -> LLMClient:
        """Return an LLMClient routed for the given task type."""
        cfg = route_model(task_type, self.config) if self.config else self.config
        return LLMClient(cfg)

    # ── Formative (exit ticket) ─────────────────────────────────────────

    async def generate_formative(
        self,
        lesson: DailyLesson,
        persona: TeacherPersona,
        config: AppConfig | None = None,
    ) -> FormativeAssessment:
        """Exit ticket — 3-5 questions checking TODAY's objective."""
        cfg = config or self.config
        prompt_template = (PROMPT_DIR / "formative_assessment.txt").read_text(encoding="utf-8")
        prompt = (
            prompt_template.replace("{persona}", persona.to_prompt_context())
            .replace("{lesson_title}", lesson.title)
            .replace("{objective}", lesson.objective)
            .replace("{grade_level}", ", ".join(persona.grade_levels) or "Not specified")
            .replace("{subject}", persona.subject_area or "General")
        )

        client = LLMClient(route_model("assessment", cfg) if cfg else cfg)
        return await client.safe_generate_json(
            prompt=prompt,
            model_class=FormativeAssessment,
            system="You are an expert formative assessment designer. Respond only with valid JSON.",
            temperature=0.4,
        )

    # ── Summative (unit test) ───────────────────────────────────────────

    async def generate_summative(
        self,
        unit: UnitPlan,
        persona: TeacherPersona,
        config: AppConfig | None = None,
    ) -> SummativeAssessment:
        """Unit test: MC, short answer, essay — aligned to all unit objectives."""
        cfg = config or self.config
        prompt_template = (PROMPT_DIR / "summative_assessment.txt").read_text(encoding="utf-8")

        objectives_str = "\n".join(f"  - {obj}" for obj in unit.enduring_understandings) or "See unit overview"
        standards_str = ", ".join(unit.standards) or "Not specified"

        prompt = (
            prompt_template.replace("{persona}", persona.to_prompt_context())
            .replace("{unit_title}", unit.title)
            .replace("{subject}", unit.subject)
            .replace("{grade_level}", unit.grade_level)
            .replace("{objectives}", objectives_str)
            .replace("{standards}", standards_str)
        )

        client = LLMClient(route_model("assessment", cfg) if cfg else cfg)
        return await client.safe_generate_json(
            prompt=prompt,
            model_class=SummativeAssessment,
            system="You are an expert summative assessment designer. Respond only with valid JSON.",
            temperature=0.4,
        )

    # ── DBQ (Document-Based Question) ───────────────────────────────────

    async def generate_dbq(
        self,
        topic: str,
        persona: TeacherPersona,
        grade_level: str = "10",
        context: str = "",
        config: AppConfig | None = None,
    ) -> DBQAssessment:
        """Document-Based Question — NYS Regents style."""
        cfg = config or self.config
        prompt_template = (PROMPT_DIR / "dbq_assessment.txt").read_text(encoding="utf-8")
        prompt = (
            prompt_template.replace("{persona}", persona.to_prompt_context())
            .replace("{topic}", topic)
            .replace("{grade_level}", grade_level)
            .replace("{subject}", persona.subject_area or "Social Studies")
            .replace("{context}", context or "No additional context provided.")
        )

        client = LLMClient(route_model("assessment", cfg) if cfg else cfg)
        return await client.safe_generate_json(
            prompt=prompt,
            model_class=DBQAssessment,
            system="You are an expert DBQ designer in the NYS Regents tradition. Respond only with valid JSON.",
            temperature=0.5,
            max_tokens=16384,
        )

    # ── Rubric ──────────────────────────────────────────────────────────

    async def generate_rubric(
        self,
        task_description: str,
        persona: TeacherPersona,
        criteria_count: int = 4,
        grade_level: str = "",
        config: AppConfig | None = None,
    ) -> Rubric:
        """Generate a rubric for any written task. 4-point scale, specific descriptors."""
        cfg = config or self.config
        prompt_template = (PROMPT_DIR / "rubric.txt").read_text(encoding="utf-8")
        prompt = (
            prompt_template.replace("{persona}", persona.to_prompt_context())
            .replace("{task_description}", task_description)
            .replace("{criteria_count}", str(criteria_count))
            .replace("{grade_level}", grade_level or ", ".join(persona.grade_levels) or "Not specified")
            .replace("{subject}", persona.subject_area or "General")
        )

        client = LLMClient(route_model("assessment", cfg) if cfg else cfg)
        return await client.safe_generate_json(
            prompt=prompt,
            model_class=Rubric,
            system="You are an expert rubric designer. Respond only with valid JSON.",
            temperature=0.4,
        )

    # ── Quiz ────────────────────────────────────────────────────────────

    async def generate_quiz(
        self,
        topic: str,
        question_count: int = 10,
        question_types: str = "mixed",
        grade: str = "8",
        persona: TeacherPersona | None = None,
        config: AppConfig | None = None,
    ) -> Quiz:
        """Short quiz: mix of formats the teacher specifies."""
        cfg = config or self.config
        persona = persona or TeacherPersona()
        prompt_template = (PROMPT_DIR / "quiz.txt").read_text(encoding="utf-8")
        prompt = (
            prompt_template.replace("{persona}", persona.to_prompt_context())
            .replace("{topic}", topic)
            .replace("{grade_level}", grade)
            .replace("{subject}", persona.subject_area or "General")
            .replace("{question_count}", str(question_count))
            .replace("{question_types}", question_types)
        )

        client = LLMClient(route_model("assessment", cfg) if cfg else cfg)
        return await client.safe_generate_json(
            prompt=prompt,
            model_class=Quiz,
            system="You are an expert quiz designer. Respond only with valid JSON.",
            temperature=0.4,
        )


# ── Convenience functions (match materials.py pattern) ──────────────────


async def generate_formative(
    lesson: DailyLesson,
    persona: TeacherPersona,
    config: AppConfig | None = None,
) -> FormativeAssessment:
    """Convenience wrapper around AssessmentGenerator.generate_formative."""
    gen = AssessmentGenerator(config)
    return await gen.generate_formative(lesson, persona)


async def generate_summative(
    unit: UnitPlan,
    persona: TeacherPersona,
    config: AppConfig | None = None,
) -> SummativeAssessment:
    """Convenience wrapper around AssessmentGenerator.generate_summative."""
    gen = AssessmentGenerator(config)
    return await gen.generate_summative(unit, persona)


async def generate_dbq(
    topic: str,
    persona: TeacherPersona,
    grade_level: str = "10",
    context: str = "",
    config: AppConfig | None = None,
) -> DBQAssessment:
    """Convenience wrapper around AssessmentGenerator.generate_dbq."""
    gen = AssessmentGenerator(config)
    return await gen.generate_dbq(topic, persona, grade_level, context)


async def generate_rubric(
    task_description: str,
    persona: TeacherPersona,
    criteria_count: int = 4,
    grade_level: str = "",
    config: AppConfig | None = None,
) -> Rubric:
    """Convenience wrapper around AssessmentGenerator.generate_rubric."""
    gen = AssessmentGenerator(config)
    return await gen.generate_rubric(task_description, persona, criteria_count, grade_level)


async def generate_quiz(
    topic: str,
    question_count: int = 10,
    question_types: str = "mixed",
    grade: str = "8",
    persona: TeacherPersona | None = None,
    config: AppConfig | None = None,
) -> Quiz:
    """Convenience wrapper around AssessmentGenerator.generate_quiz."""
    gen = AssessmentGenerator(config)
    return await gen.generate_quiz(topic, question_count, question_types, grade, persona)


def save_assessment(
    assessment: FormativeAssessment | SummativeAssessment | DBQAssessment | Quiz | Rubric,
    output_dir: Path,
    label: str = "assessment",
) -> Path:
    """Save any assessment type to disk as JSON."""
    output_dir.mkdir(parents=True, exist_ok=True)
    # Build a safe filename from the assessment's primary identifier
    if hasattr(assessment, "topic"):
        name = assessment.topic
    elif hasattr(assessment, "lesson_title"):
        name = assessment.lesson_title
    elif hasattr(assessment, "unit_title"):
        name = assessment.unit_title
    elif hasattr(assessment, "task_description"):
        name = assessment.task_description
    else:
        name = "output"
    from clawed.io import safe_filename, write_text

    safe_name = safe_filename(name, max_len=50)
    path = output_dir / f"{label}_{safe_name}.json"
    write_text(path, assessment.model_dump_json(indent=2))
    return path
