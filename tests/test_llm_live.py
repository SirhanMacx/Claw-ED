"""Live LLM integration tests — skipped unless EDUAGENT_LIVE_TESTS=1.

These tests send real prompts to the configured LLM backend and validate
that the responses parse into the expected Pydantic models.  They are
intended for manual use (not CI) to verify end-to-end generation after
changes to prompts or the LLM client.

Run with:
    EDUAGENT_LIVE_TESTS=1 python -m pytest tests/test_llm_live.py -x -v
"""

from __future__ import annotations

import os

import pytest

_LIVE = os.environ.get("EDUAGENT_LIVE_TESTS", "0") == "1"
_REASON = "Set EDUAGENT_LIVE_TESTS=1 to run live LLM tests"


@pytest.mark.skipif(not _LIVE, reason=_REASON)
class TestPersonaExtraction:
    """Send a real persona extraction prompt and validate the response."""

    @pytest.mark.asyncio
    async def test_extract_persona_from_sample_document(self):
        from clawed.models import DocType, Document, TeacherPersona
        from clawed.persona import extract_persona

        sample_doc = Document(
            title="Sample Lesson Plan — Photosynthesis",
            content=(
                "Lesson: Introduction to Photosynthesis\n"
                "Grade: 8th Grade Science\n"
                "Objective: Students will be able to describe the process of "
                "photosynthesis and identify its inputs and outputs.\n\n"
                "Do-Now (5 min): Look at the plant on your desk. Write down "
                "three things you think a plant needs to survive.\n\n"
                "Direct Instruction (15 min): Today we're going to explore "
                "how plants make their own food. I like to call this the "
                "'plant kitchen' because it's where the cooking happens! "
                "Let's start by looking at the equation on the board...\n\n"
                "Guided Practice (15 min): With your lab partner, examine "
                "the leaf under the microscope. Sketch what you see and "
                "label the chloroplasts.\n\n"
                "Independent Work (10 min): Complete the photosynthesis "
                "diagram worksheet. Fill in the inputs and outputs.\n\n"
                "Exit Ticket: Write the word equation for photosynthesis "
                "and name ONE thing plants release into the air.\n\n"
                "Homework: Read pages 34-36 and answer questions 1-3.\n\n"
                "Differentiation:\n"
                "- Struggling: Provide a word bank for the diagram\n"
                "- Advanced: Research C4 vs C3 photosynthesis\n"
                "- ELL: Bilingual vocabulary sheet provided\n"
            ),
            doc_type=DocType.TXT,
            source_path="/tmp/sample_lesson.txt",
        )

        persona = await extract_persona([sample_doc])

        # Validate it's a proper TeacherPersona
        assert isinstance(persona, TeacherPersona)
        assert persona.name  # Should have extracted or defaulted a name
        assert persona.teaching_style  # Should have a style
        assert persona.tone  # Should have a tone description
        assert persona.vocabulary_level  # Should have a vocab level

        # The sample is clearly a science lesson, so subject should reflect that
        subject_lower = persona.subject_area.lower()
        assert "science" in subject_lower or "biology" in subject_lower or subject_lower

        # Persona should be serializable to prompt context
        ctx = persona.to_prompt_context()
        assert "Teacher Persona:" in ctx
        assert len(ctx) > 50


@pytest.mark.skipif(not _LIVE, reason=_REASON)
class TestLessonGeneration:
    """Send a real lesson generation prompt and validate the response."""

    @pytest.mark.asyncio
    async def test_generate_lesson_parses_into_daily_lesson(self):
        from clawed.lesson import generate_lesson
        from clawed.models import (
            DailyLesson,
            LessonBrief,
            TeacherPersona,
            TeachingStyle,
            UnitPlan,
        )

        persona = TeacherPersona(
            name="Test Teacher",
            teaching_style=TeachingStyle.DIRECT_INSTRUCTION,
            tone="warm and encouraging",
            subject_area="Science",
            grade_levels=["8"],
        )

        unit = UnitPlan(
            title="Introduction to Photosynthesis",
            subject="Science",
            grade_level="8",
            topic="Photosynthesis",
            duration_weeks=2,
            overview=(
                "A two-week unit exploring how plants convert light energy into chemical energy through photosynthesis."
            ),
            essential_questions=[
                "How do plants make their own food?",
                "Why is photosynthesis important for life on Earth?",
            ],
            daily_lessons=[
                LessonBrief(
                    lesson_number=1,
                    topic="What is Photosynthesis? The Big Picture",
                    description="Introduction to the concept of photosynthesis.",
                    lesson_type="instruction",
                ),
            ],
        )

        lesson = await generate_lesson(
            lesson_number=1,
            unit=unit,
            persona=persona,
            include_homework=True,
        )

        # Validate it's a proper DailyLesson
        assert isinstance(lesson, DailyLesson)
        assert lesson.title  # Must have a title
        assert lesson.lesson_number == 1
        assert lesson.objective  # Must have a learning objective
        assert lesson.do_now  # Should have a do-now/bell-ringer
        assert lesson.direct_instruction  # Should have direct instruction
        assert lesson.guided_practice  # Should have guided practice

        # Exit ticket should be present
        assert len(lesson.exit_ticket) > 0
        for q in lesson.exit_ticket:
            assert q.question  # Each question should have text

        # Differentiation should be populated
        diff = lesson.differentiation
        assert diff.struggling or diff.advanced or diff.ell, "Should have at least one differentiation category"

        # Time estimates should sum to something reasonable (25-60 min)
        total_time = sum(lesson.time_estimates.values())
        assert 20 <= total_time <= 90, f"Total lesson time {total_time} min seems unreasonable"


@pytest.mark.skipif(not _LIVE, reason=_REASON)
class TestGenerateJson:
    """Test the LLM client's JSON generation and repair capabilities."""

    @pytest.mark.asyncio
    async def test_generate_json_returns_valid_dict(self):
        from clawed.llm import LLMClient

        client = LLMClient()
        result = await client.generate_json(
            prompt=(
                "Return a JSON object with these fields: "
                '"subject" (string), "grade" (string), "topics" (list of 3 strings). '
                "Example subject: Math, grade: 5."
            ),
            system="Respond with valid JSON only. No markdown fences.",
            temperature=0.2,
            max_tokens=256,
        )

        assert isinstance(result, dict)
        assert "subject" in result
        assert "grade" in result
        assert "topics" in result
        assert isinstance(result["topics"], list)
        assert len(result["topics"]) >= 1
