"""Integration tests — end-to-end flows with mocked LLM calls.

These tests verify the full pipeline: persona → unit plan → lesson → state
persistence → corpus contribution/retrieval — without making real API calls.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

from clawed.corpus import (
    contribute_example,
    get_examples,
    init_corpus_db,
)
from clawed.lesson import generate_lesson
from clawed.master_content import MasterContent
from clawed.models import (
    AppConfig,
    DailyLesson,
    ExitTicketQuestion,
    LessonBrief,
    LLMProvider,
    TeacherPersona,
    TeachingStyle,
    UnitPlan,
)
from clawed.planner import plan_unit
from clawed.router import Intent, parse_intent
from clawed.state import TeacherSession

# ── Helpers ─────────────────────────────────────────────────────────────────


def _run(coro):
    """Run an async coroutine synchronously."""
    return asyncio.run(coro)


def _mock_llm_client(mock_cls, mock_json, model_class=None):
    """Set up a mocked LLMClient with both generate_json and safe_generate_json.

    This is needed because safe_generate_json is the preferred call path but
    tests traditionally mock generate_json. Setting both ensures tests pass
    regardless of which path the production code uses.
    """
    inst = mock_cls.return_value
    inst.generate_json = AsyncMock(return_value=mock_json)
    if model_class is not None:
        inst.safe_generate_json = AsyncMock(
            return_value=model_class.model_validate(mock_json),
        )
    return inst


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture()
def persona():
    """A minimal direct-instruction Social Studies teacher persona."""
    return TeacherPersona(
        name="Ms. Rivera",
        teaching_style=TeachingStyle.DIRECT_INSTRUCTION,
        subject_area="Social Studies",
        grade_levels=["10"],
        tone="clear and structured",
        structural_preferences=["Do Now", "exit tickets", "guided notes"],
        favorite_strategies=[
            "primary source analysis",
            "Socratic questioning",
        ],
    )


@pytest.fixture()
def config():
    """AppConfig pointing at Ollama so no real API key is needed."""
    return AppConfig(
        provider=LLMProvider.OLLAMA,
        ollama_model="llama3.2",
        ollama_base_url="http://localhost:11434",
    )


def _lesson_briefs():
    """Ten lesson briefs for a 2-week WWI unit."""
    data = [
        (1, "Nationalism in Europe", "Nationalism fueled competition."),
        (2, "The Alliance System", "Map alliances dividing Europe."),
        (3, "Imperialism and Rivalries", "Imperial competition as tension."),
        (4, "Militarism and Arms Race", "Militarism escalated tensions."),
        (5, "Assassination of Franz Ferdinand", "Events of June 28 1914."),
        (6, "July Crisis and Ultimatums", "Diplomatic failures of July 1914."),
        (7, "Chain Reaction: War Spread", "Alliance system turned crisis global."),
        (8, "Perspectives: Who Was to Blame?", "Debate responsibility."),
        (9, "Document-Based Investigation", "Analyze primary sources on WWI."),
        (10, "Unit Assessment and Reflection", "Summative assessment."),
    ]
    return [LessonBrief(lesson_number=n, topic=t, description=d) for n, t, d in data]


@pytest.fixture()
def sample_unit() -> UnitPlan:
    """A realistic 2-week WWI unit plan (10 daily lessons)."""
    return UnitPlan(
        title="Chain Reaction: Unpacking the Causes of World War I",
        subject="Social Studies",
        grade_level="10",
        topic="Causes of WWI",
        duration_weeks=2,
        overview=(
            "Students explore the long-term and short-term causes of "
            "World War I, from rising nationalism and the alliance system "
            "to the assassination of Archduke Franz Ferdinand."
        ),
        essential_questions=[
            "Was WWI inevitable, or could it have been prevented?",
            "How do alliances protect nations versus provoke conflict?",
            "What role did nationalism play in the outbreak of WWI?",
        ],
        enduring_understandings=[
            "Complex events have multiple interconnected causes.",
            "Alliances can escalate local conflicts into global wars.",
        ],
        standards=["NYS-SS 10.5", "C3.D2.His.1.9-12"],
        daily_lessons=_lesson_briefs(),
        assessment_plan={
            "formative": ["Exit tickets", "Do Now responses"],
            "summative": ["DBQ essay on the causes of WWI"],
        },
        required_materials=["Primary source packets", "Map of 1914 Europe"],
    )


@pytest.fixture()
def sample_lesson() -> DailyLesson:
    """A realistic lesson 1 for the WWI unit."""
    return DailyLesson(
        title="Nationalism in 19th-Century Europe",
        lesson_number=1,
        objective=(
            "SWBAT analyze how nationalism fueled competition among European powers by examining primary sources."
        ),
        standards=["NYS-SS 10.5"],
        do_now=(
            "Look at the two political cartoons projected on the board. "
            "In 2-3 sentences, describe each cartoon's message."
        ),
        direct_instruction=(
            "Mini-lecture on nationalism in 19th-century Europe, focusing "
            "on unification movements in Germany and Italy."
        ),
        guided_practice=(
            "In pairs, students analyze three primary source documents and complete a SOAPS analysis chart."
        ),
        independent_work=(
            "Write a one-paragraph response to: How did nationalism "
            "contribute to tensions among European powers before WWI?"
        ),
        exit_ticket=[
            ExitTicketQuestion(
                question=("Name two ways nationalism increased tensions in Europe before 1914."),
                expected_response=("Competition for territory/resources; instability in multi-ethnic empires."),
            ),
        ],
        homework="Read pages 412-418 and complete guided reading.",
        differentiation={
            "struggling": ["Sentence starters for paragraph response"],
            "advanced": ["Compare nationalism across two countries"],
            "ell": ["Vocabulary list with L1 definitions"],
        },
        materials_needed=["Political cartoons", "Primary source packet"],
    )


@pytest.fixture()
def temp_db(tmp_path, monkeypatch):
    """Redirect both state DB and corpus DB to a temp directory."""
    monkeypatch.setattr("clawed.state.DEFAULT_DATA_DIR", tmp_path)
    monkeypatch.setattr(
        "clawed.corpus.CORPUS_DIR",
        tmp_path / "corpus",
    )
    monkeypatch.setattr(
        "clawed.corpus.CORPUS_DB",
        tmp_path / "corpus" / "corpus.db",
    )
    return tmp_path


def _mock_unit_json(topic: str = "Causes of WWI") -> dict:
    """Return a realistic unit-plan JSON the LLM would produce."""
    return {
        "title": f"Chain Reaction: Unpacking the {topic}",
        "subject": "Social Studies",
        "grade_level": "10",
        "topic": topic,
        "duration_weeks": 2,
        "overview": f"Students investigate the {topic}.",
        "essential_questions": [
            "Was WWI inevitable or preventable?",
            "How do alliances protect versus provoke?",
            "What role did nationalism play?",
        ],
        "enduring_understandings": [
            "Complex events have multiple interconnected causes.",
        ],
        "standards": ["NYS-SS 10.5"],
        "daily_lessons": [
            {
                "lesson_number": i,
                "topic": f"Lesson {i} Topic",
                "description": f"Description for lesson {i}",
            }
            for i in range(1, 11)
        ],
        "assessment_plan": {
            "formative": ["Exit tickets"],
            "summative": ["Unit test"],
        },
        "required_materials": ["Textbook"],
    }


def _mock_lesson_json(lesson_number: int = 1) -> dict:
    """Return a realistic lesson-plan JSON the LLM would produce."""
    return {
        "title": "Nationalism in 19th-Century Europe",
        "lesson_number": lesson_number,
        "objective": (
            "SWBAT analyze how nationalism fueled competition among European powers by examining primary sources."
        ),
        "standards": ["NYS-SS 10.5"],
        "do_now": "Examine the political cartoon on the board.",
        "direct_instruction": ("Mini-lecture on nationalism and the unification of Germany and Italy."),
        "guided_practice": "Pairs analyze three primary sources.",
        "independent_work": "Write a paragraph on nationalism tensions.",
        "exit_ticket": [
            {
                "question": "Name two ways nationalism increased tensions.",
                "expected_response": "Competition and instability.",
            },
        ],
        "homework": "Read pages 412-418.",
        "differentiation": {
            "struggling": ["Sentence starters provided"],
            "advanced": ["Compare nationalism across two countries"],
            "ell": ["Vocabulary list in L1"],
        },
        "materials_needed": ["Primary source packet"],
    }


def _mock_master_content_json() -> dict:
    """Return a realistic MasterContent JSON the LLM would produce."""
    return {
        "title": "Nationalism in 19th-Century Europe",
        "subject": "Social Studies",
        "grade_level": "10",
        "topic": "Nationalism in Europe",
        "standards": ["NYS-SS 10.5"],
        "objective": (
            "SWBAT analyze how nationalism fueled competition among European powers by examining primary sources."
        ),
        "duration_minutes": 45,
        "vocabulary": [
            {
                "term": "nationalism",
                "definition": "Extreme pride in one's nation",
                "context_sentence": "Nationalism drove competition among European powers.",
            },
        ],
        "primary_sources": [
            {
                "id": "source_a",
                "title": "Otto von Bismarck Speech, 1862",
                "source_type": "text_excerpt",
                "content_text": (
                    "The great questions of the day will not be settled by speeches "
                    "and majority decisions but by iron and blood."
                ),
                "attribution": "Otto von Bismarck, 1862",
                "scaffolding_questions": [
                    "What does Bismarck mean by 'iron and blood'?",
                    "How does this speech reflect nationalist sentiment?",
                ],
            },
            {
                "id": "source_b",
                "title": "Map of Europe, 1871",
                "source_type": "map",
                "content_text": (
                    "Map showing the newly unified German Empire and Kingdom of Italy "
                    "alongside older empires (Austria-Hungary, Ottoman, Russian)."
                ),
                "attribution": "Historical Atlas, 1871",
                "scaffolding_questions": [
                    "Which new nations appear on this map?",
                    "How might their formation affect the balance of power?",
                ],
            },
        ],
        "do_now": {
            "stimulus": (
                "Look at the two political cartoons projected on the board. "
                "One shows a German eagle spreading its wings over Europe; "
                "the other shows various European nations pulling at a map."
            ),
            "stimulus_type": "image",
            "questions": [
                "What message is each cartoon trying to convey?",
                "What emotions does each cartoon evoke about nationalism?",
            ],
            "answers": [
                "The eagle represents German expansionism and national pride.",
                "The pulling cartoon shows competition and rivalry among nations.",
            ],
        },
        "direct_instruction": [
            {
                "heading": "The Rise of Nationalism",
                "content": (
                    "Nationalism — the belief that a people sharing a common language, "
                    "history, and culture should form an independent nation — reshaped "
                    "19th-century Europe. Germany unified under Bismarck in 1871; "
                    "Italy unified through Garibaldi and Cavour."
                ),
                "teacher_script": (
                    "Today we are investigating how nationalism fueled competition. "
                    "Turn to your partner: what does it mean to feel national pride?"
                ),
                "key_points": [
                    "Nationalism drove unification movements in Germany and Italy",
                    "Multi-ethnic empires (Austria-Hungary, Ottoman) faced internal pressures",
                ],
            },
        ],
        "guided_notes": [
            {
                "prompt": "________ unified Germany through 'iron and blood' policies.",
                "answer": "Bismarck",
                "section_ref": "The Rise of Nationalism",
            },
            {
                "prompt": "Italy was unified through the efforts of Garibaldi and ________.",
                "answer": "Cavour",
                "section_ref": "The Rise of Nationalism",
            },
            {
                "prompt": "Multi-ethnic empires like ________ faced internal nationalist pressures.",
                "answer": "Austria-Hungary",
                "section_ref": "The Rise of Nationalism",
            },
            {
                "prompt": "Nationalism is the belief that people sharing a common ________ should form a nation.",
                "answer": "language",
                "section_ref": "The Rise of Nationalism",
            },
            {
                "prompt": "Germany was officially unified in the year ________.",
                "answer": "1871",
                "section_ref": "The Rise of Nationalism",
            },
        ],
        "stations": [
            {
                "title": "STATION A: Bismarck's Speech",
                "source_ref": "source_a",
                "task": "Sourcing and contextualizing Bismarck's 'iron and blood' speech.",
                "student_directions": (
                    "1. Read the excerpt. 2. Identify the speaker and date. "
                    "3. What does Bismarck mean by 'iron and blood'? "
                    "4. How does this reflect nationalist goals?"
                ),
                "teacher_answer_key": (
                    "Bismarck means military force. It reflects aggressive nationalism "
                    "and the desire to unify Germany through power, not diplomacy."
                ),
            },
        ],
        "independent_work": {
            "task": (
                "Write a one-paragraph response: How did nationalism contribute "
                "to tensions among European powers before WWI? Use at least two "
                "pieces of evidence from today's sources."
            ),
            "rubric_snippet": ("Proficient: Clear claim + 2 evidence citations + explanation of each"),
            "exemplar": (
                "Nationalism increased tensions by driving competition for territory "
                "and destabilizing multi-ethnic empires. Bismarck's 'iron and blood' "
                "speech shows Germany's aggressive pursuit of unification."
            ),
        },
        "exit_ticket": [
            {
                "stimulus": (
                    "Bismarck declared: 'The great questions of the day will not be "
                    "settled by speeches and majority decisions but by iron and blood.'"
                ),
                "stimulus_type": "text_excerpt",
                "question": "What policy approach does this quote describe?",
                "answer": "Military force and realpolitik over diplomacy.",
                "cognitive_level": "recall",
            },
            {
                "stimulus": (
                    "By 1871, both Germany and Italy had unified into nation-states after decades of fragmentation."
                ),
                "stimulus_type": "text_excerpt",
                "question": ("How did the unification of Germany and Italy change the balance of power in Europe?"),
                "answer": ("New powerful nations competed with established empires, increasing rivalry and tension."),
                "cognitive_level": "application",
            },
            {
                "stimulus": (
                    "Austria-Hungary contained over 11 major ethnic groups, many of whom sought independence."
                ),
                "stimulus_type": "text_excerpt",
                "question": ("Why might nationalism be a threat to multi-ethnic empires rather than a unifying force?"),
                "answer": (
                    "Ethnic groups within empires wanted their own nations, "
                    "leading to internal instability and separatist movements."
                ),
                "cognitive_level": "analysis",
            },
        ],
        "differentiation": {
            "struggling": ["Sentence starters provided for paragraph response"],
            "advanced": ["Compare nationalism across two countries using a Venn diagram"],
            "ell": ["Vocabulary list with L1 cognates and visual glossary"],
        },
        "homework": "Read pages 412-418.",
        "materials_needed": ["Primary source packet", "Political cartoons"],
    }


# ═══════════════════════════════════════════════════════════════════════════
# 1. Full Unit Generation Flow
# ═══════════════════════════════════════════════════════════════════════════


class TestFullUnitGenerationFlow:
    """End-to-end: persona → plan_unit() → verify UnitPlan structure."""

    def test_plan_unit_returns_valid_unit(self, persona, config):
        """plan_unit() with a mocked LLM produces a valid UnitPlan."""
        mock_json = _mock_unit_json()

        with patch("clawed.planner.LLMClient") as mock_cls:
            _mock_llm_client(mock_cls, mock_json, model_class=UnitPlan)

            unit = _run(
                plan_unit(
                    topic="Causes of WWI",
                    grade_level="10",
                    subject="Social Studies",
                    duration_weeks=2,
                    persona=persona,
                    config=config,
                )
            )

        assert isinstance(unit, UnitPlan)
        assert unit.title
        assert len(unit.essential_questions) >= 2
        assert len(unit.daily_lessons) >= 5
        for brief in unit.daily_lessons:
            assert brief.topic, f"Lesson {brief.lesson_number} has empty topic"

    def test_unit_has_correct_metadata(self, persona, config):
        """Unit plan preserves subject, grade, and duration."""
        mock_json = _mock_unit_json()

        with patch("clawed.planner.LLMClient") as mock_cls:
            _mock_llm_client(mock_cls, mock_json, model_class=UnitPlan)

            unit = _run(
                plan_unit(
                    topic="Causes of WWI",
                    grade_level="10",
                    subject="Social Studies",
                    duration_weeks=2,
                    persona=persona,
                    config=config,
                )
            )

        assert unit.subject == "Social Studies"
        assert unit.grade_level == "10"
        assert unit.duration_weeks == 2

    def test_unit_has_assessment_plan(self, persona, config):
        """Unit plan includes formative and summative assessments."""
        mock_json = _mock_unit_json()

        with patch("clawed.planner.LLMClient") as mock_cls:
            _mock_llm_client(mock_cls, mock_json, model_class=UnitPlan)

            unit = _run(
                plan_unit(
                    topic="Causes of WWI",
                    grade_level="10",
                    subject="Social Studies",
                    duration_weeks=2,
                    persona=persona,
                    config=config,
                )
            )

        assert unit.assessment_plan.formative
        assert unit.assessment_plan.summative

    def test_unit_persona_injected_into_prompt(self, persona, config):
        """Persona context is passed to the LLM prompt."""
        mock_json = _mock_unit_json()

        with patch("clawed.planner.LLMClient") as mock_cls:
            inst = _mock_llm_client(mock_cls, mock_json, model_class=UnitPlan)

            _run(
                plan_unit(
                    topic="Causes of WWI",
                    grade_level="10",
                    subject="Social Studies",
                    duration_weeks=2,
                    persona=persona,
                    config=config,
                )
            )

            call_args = inst.safe_generate_json.call_args
            prompt_text = call_args.kwargs.get(
                "prompt",
                call_args.args[0] if call_args.args else "",
            )
            assert "Ms. Rivera" in prompt_text or "Direct Instruction" in prompt_text


# ═══════════════════════════════════════════════════════════════════════════
# 2. Lesson Generation from Unit
# ═══════════════════════════════════════════════════════════════════════════


class TestLessonGenerationFromUnit:
    """End-to-end: unit plan → generate_lesson() → verify DailyLesson."""

    def test_generate_lesson_returns_valid_lesson(
        self,
        sample_unit,
        persona,
        config,
    ):
        """generate_lesson() with mocked LLM produces a valid DailyLesson."""
        mock_json = _mock_master_content_json()

        with patch("clawed.lesson.LLMClient") as mock_cls:
            _mock_llm_client(mock_cls, mock_json, model_class=MasterContent)

            lesson = _run(
                generate_lesson(
                    lesson_number=1,
                    unit=sample_unit,
                    persona=persona,
                    config=config,
                )
            )

        assert isinstance(lesson, DailyLesson)
        assert lesson.title
        assert lesson.do_now
        assert lesson.direct_instruction
        assert lesson.exit_ticket

    def test_lesson_objective_contains_swbat(
        self,
        sample_unit,
        persona,
        config,
    ):
        """Lesson objective includes SWBAT or 'will be able to'."""
        mock_json = _mock_master_content_json()

        with patch("clawed.lesson.LLMClient") as mock_cls:
            _mock_llm_client(mock_cls, mock_json, model_class=MasterContent)

            lesson = _run(
                generate_lesson(
                    lesson_number=1,
                    unit=sample_unit,
                    persona=persona,
                    config=config,
                )
            )

        obj_lower = lesson.objective.lower()
        assert "swbat" in obj_lower or "will be able to" in obj_lower, f"Objective missing SWBAT: {lesson.objective}"

    def test_lesson_has_all_required_sections(
        self,
        sample_unit,
        persona,
        config,
    ):
        """Every key section of a DailyLesson is populated."""
        mock_json = _mock_master_content_json()

        with patch("clawed.lesson.LLMClient") as mock_cls:
            _mock_llm_client(mock_cls, mock_json, model_class=MasterContent)

            lesson = _run(
                generate_lesson(
                    lesson_number=1,
                    unit=sample_unit,
                    persona=persona,
                    config=config,
                )
            )

        assert lesson.title
        assert lesson.objective
        assert lesson.do_now
        assert lesson.direct_instruction
        assert lesson.exit_ticket
        assert lesson.lesson_number == 1

    def test_invalid_lesson_number_raises(
        self,
        sample_unit,
        persona,
        config,
    ):
        """Requesting a lesson number outside the unit raises ValueError."""
        with pytest.raises(ValueError, match="Lesson 99 not found"):
            _run(
                generate_lesson(
                    lesson_number=99,
                    unit=sample_unit,
                    persona=persona,
                    config=config,
                )
            )

    def test_lesson_exit_ticket_has_question(
        self,
        sample_unit,
        persona,
        config,
    ):
        """Exit ticket contains at least one question with text."""
        mock_json = _mock_master_content_json()

        with patch("clawed.lesson.LLMClient") as mock_cls:
            _mock_llm_client(mock_cls, mock_json, model_class=MasterContent)

            lesson = _run(
                generate_lesson(
                    lesson_number=1,
                    unit=sample_unit,
                    persona=persona,
                    config=config,
                )
            )

        assert len(lesson.exit_ticket) >= 1
        assert lesson.exit_ticket[0].question


# ═══════════════════════════════════════════════════════════════════════════
# 3. Router Accuracy
# ═══════════════════════════════════════════════════════════════════════════


class TestRouterAccuracy:
    """Verify parse_intent() correctly classifies 20+ teacher messages."""

    CASES = [
        # Unit generation
        ("plan a unit on the Industrial Revolution for 3 weeks", Intent.GENERATE_UNIT),
        ("I need a unit plan on photosynthesis", Intent.GENERATE_UNIT),
        ("create a 2-week curriculum unit on the Civil War", Intent.GENERATE_UNIT),
        # Lesson generation
        ("make a lesson on fractions", Intent.GENERATE_LESSON),
        ("I need a lesson plan for tomorrow on the water cycle", Intent.GENERATE_LESSON),
        ("generate a daily lesson on mitosis", Intent.GENERATE_LESSON),
        # Assessment
        ("make a test on chapter 5", Intent.GENERATE_ASSESSMENT),
        ("create a quiz about photosynthesis", Intent.GENERATE_ASSESSMENT),
        ("write an exit ticket for today's lesson", Intent.GENERATE_ASSESSMENT),
        ("generate a rubric for the essay", Intent.GENERATE_ASSESSMENT),
        # Bellringer / Do Now
        ("bell ringer idea for US history", Intent.GENERATE_BELLRINGER),
        ("give me a warm-up for my math class", Intent.GENERATE_BELLRINGER),
        ("do now on vocabulary review", Intent.GENERATE_BELLRINGER),
        # Standards
        ("what standards for grade 8 math", Intent.SEARCH_STANDARDS),
        # Materials
        ("make a worksheet on the American Revolution", Intent.GENERATE_MATERIALS),
        ("create a handout for my science class", Intent.GENERATE_MATERIALS),
        # Year planning
        ("plan my year for 9th grade Global History", Intent.GENERATE_YEAR_MAP),
        ("create a scope and sequence for AP US History", Intent.GENERATE_YEAR_MAP),
        # Search
        ("find an article about climate change for my class", Intent.WEB_SEARCH),
        ("search for current events about elections", Intent.WEB_SEARCH),
        # Help
        ("help", Intent.HELP),
        ("what can you do", Intent.HELP),
        # Setup
        ("I teach 9th grade math at Lincoln High", Intent.SETUP),
        # Differentiation edge cases
        ("differentiate this lesson for my IEP students", Intent.GENERATE_DIFFERENTIATION),
        ("how do I accommodate ELL students", Intent.GENERATE_DIFFERENTIATION),
    ]

    @pytest.mark.parametrize(
        "message,expected",
        CASES,
        ids=[c[0][:40] for c in CASES],
    )
    def test_intent_classification(self, message: str, expected: Intent):
        result = parse_intent(message)
        assert result.intent == expected, f"Message: {message!r}\nExpected: {expected}\nGot: {result.intent}"

    def test_router_accuracy_at_least_90_percent(self):
        """Overall accuracy must be >= 90%."""
        correct = 0
        for message, expected in self.CASES:
            result = parse_intent(message)
            if result.intent == expected:
                correct += 1
        accuracy = correct / len(self.CASES)
        assert accuracy >= 0.90, f"Router accuracy {accuracy:.0%} < 90%"

    def test_topic_extraction(self):
        """parse_intent extracts topics from natural language."""
        result = parse_intent("plan a unit on the Civil War")
        assert result.topic is not None
        assert "civil war" in result.topic.lower()

    def test_grade_extraction(self):
        """parse_intent extracts grade level."""
        result = parse_intent("create a lesson on fractions for grade 7")
        assert result.grade == "7"

    def test_weeks_extraction(self):
        """parse_intent extracts duration in weeks."""
        result = parse_intent("plan a unit on ecology for 3 weeks")
        assert result.weeks == 3

    def test_unknown_intent_for_gibberish(self):
        """Unrecognizable input maps to UNKNOWN."""
        result = parse_intent("asdf qwerty zxcv")
        assert result.intent == Intent.UNKNOWN

    def test_raw_preserved(self):
        """The raw message text is preserved in the result."""
        msg = "make a lesson on photosynthesis"
        result = parse_intent(msg)
        assert result.raw == msg


# ═══════════════════════════════════════════════════════════════════════════
# 4. State Persistence
# ═══════════════════════════════════════════════════════════════════════════


class TestStatePersistence:
    """Verify TeacherSession survives save → load round-trips."""

    def test_session_round_trip(
        self,
        temp_db,
        persona,
        sample_unit,
        sample_lesson,
    ):
        """Session with persona, unit, and lesson survives save/load."""
        session = TeacherSession(
            teacher_id="teacher-integration-001",
            name="Ms. Rivera",
            persona=persona,
        )
        session.add_context("user", "plan a unit on WWI")
        session.add_context("assistant", "Here is your unit plan.")

        unit_id = session.save_unit(sample_unit)
        session.save_lesson(sample_lesson, unit_id=unit_id)
        session.save()

        loaded = TeacherSession.load("teacher-integration-001")

        assert loaded.name == "Ms. Rivera"
        assert loaded.persona is not None
        assert loaded.persona.name == "Ms. Rivera"
        assert loaded.persona.teaching_style == TeachingStyle.DIRECT_INSTRUCTION

        assert loaded.current_unit is not None
        assert loaded.current_unit.title == sample_unit.title
        assert loaded.current_unit.topic == "Causes of WWI"
        assert len(loaded.current_unit.daily_lessons) == 10

        assert loaded.current_lesson is not None
        assert loaded.current_lesson.title == sample_lesson.title
        assert loaded.current_lesson.lesson_number == 1

        assert len(loaded.context) == 2
        assert loaded.context[0]["role"] == "user"
        assert "WWI" in loaded.context[0]["content"]

    def test_session_unit_saved_to_generated_units_table(
        self,
        temp_db,
        persona,
        sample_unit,
    ):
        """save_unit() writes to the generated_units table."""
        session = TeacherSession(
            teacher_id="teacher-integration-002",
            persona=persona,
        )
        unit_id = session.save_unit(sample_unit)

        recent = session.get_recent_units(limit=5)
        assert len(recent) >= 1
        assert any(u["id"] == unit_id for u in recent)

    def test_session_lesson_saved_with_share_token(
        self,
        temp_db,
        persona,
        sample_unit,
        sample_lesson,
    ):
        """save_lesson() creates a unique share token."""
        session = TeacherSession(
            teacher_id="teacher-integration-003",
            persona=persona,
        )
        unit_id = session.save_unit(sample_unit)
        session.save_lesson(sample_lesson, unit_id=unit_id)

        from clawed.state import _get_conn

        with _get_conn() as conn:
            row = conn.execute(
                "SELECT share_token FROM generated_lessons WHERE teacher_id = ?",
                ("teacher-integration-003",),
            ).fetchone()
        assert row is not None
        assert row["share_token"]

    def test_new_session_is_new(self, temp_db):
        """A fresh session with no persona is marked as new."""
        session = TeacherSession.load("nonexistent-teacher-999")
        assert session.is_new

    def test_context_capped_at_20_turns(self, temp_db, persona):
        """Session context is capped at 20 turns on save."""
        session = TeacherSession(
            teacher_id="teacher-cap-test",
            persona=persona,
        )
        for i in range(30):
            session.add_context("user", f"Message {i}")
        session.save()

        loaded = TeacherSession.load("teacher-cap-test")
        assert len(loaded.context) <= 20

    def test_multiple_units_tracked(self, temp_db, persona, sample_unit):
        """Multiple units can be saved for the same teacher."""
        session = TeacherSession(
            teacher_id="teacher-multi-unit",
            persona=persona,
        )
        for i in range(3):
            unit = sample_unit.model_copy(
                update={"title": f"Unit {i}", "topic": f"Topic {i}"},
            )
            session.save_unit(unit)

        recent = session.get_recent_units(limit=10)
        assert len(recent) == 3


# ═══════════════════════════════════════════════════════════════════════════
# 5. Corpus Contribution and Retrieval
# ═══════════════════════════════════════════════════════════════════════════


class TestCorpusContributionAndRetrieval:
    """Verify the corpus stores examples and retrieves relevant ones."""

    def test_contribute_and_retrieve(self, temp_db):
        """Add 3 lessons, retrieve them by subject and grade."""
        init_corpus_db()

        ids = []
        for i in range(1, 4):
            entry_id = contribute_example(
                content_type="lesson_plan",
                subject="social studies",
                grade_level="10",
                content={
                    "title": f"Lesson {i}: Topic {i}",
                    "objective": f"SWBAT explain topic {i}",
                    "do_now": f"Review warm-up for topic {i}",
                },
                topic=f"Topic {i}",
                quality_score=4.5,
                teacher_id="test-teacher-corpus",
            )
            ids.append(entry_id)

        assert len(ids) == 3

        results = get_examples(
            content_type="lesson_plan",
            subject="social studies",
            grade_level="10",
            limit=5,
            min_quality=3.0,
        )

        assert len(results) == 3
        titles = [r.get("title", "") for r in results]
        assert any("Lesson 1" in t for t in titles)

    def test_retrieve_filters_by_subject(self, temp_db):
        """Retrieval only returns matching subject."""
        init_corpus_db()

        contribute_example(
            content_type="lesson_plan",
            subject="math",
            grade_level="8",
            content={"title": "Math Lesson"},
            quality_score=5.0,
        )
        contribute_example(
            content_type="lesson_plan",
            subject="science",
            grade_level="8",
            content={"title": "Science Lesson"},
            quality_score=5.0,
        )

        math_results = get_examples("lesson_plan", "math", limit=10)
        assert all("Math" in r.get("title", "") for r in math_results)

        sci_results = get_examples("lesson_plan", "science", limit=10)
        assert all("Science" in r.get("title", "") for r in sci_results)

    def test_quality_filter(self, temp_db):
        """Low-quality examples are filtered out."""
        init_corpus_db()

        contribute_example(
            content_type="lesson_plan",
            subject="social studies",
            grade_level="10",
            content={"title": "Good Lesson"},
            quality_score=4.5,
        )
        contribute_example(
            content_type="lesson_plan",
            subject="social studies",
            grade_level="10",
            content={"title": "Bad Lesson"},
            quality_score=1.0,
        )

        results = get_examples(
            "lesson_plan",
            "social studies",
            min_quality=3.0,
            limit=10,
        )
        titles = [r.get("title", "") for r in results]
        assert "Good Lesson" in titles
        assert "Bad Lesson" not in titles

    def test_pii_sanitization(self, temp_db):
        """Email and phone numbers are scrubbed from corpus entries."""
        init_corpus_db()

        contribute_example(
            content_type="lesson_plan",
            subject="math",
            grade_level="7",
            content={
                "title": "Lesson with PII",
                "contact": "teacher@school.edu",
                "phone": "555-123-4567",
            },
            quality_score=4.0,
        )

        results = get_examples(
            "lesson_plan",
            "math",
            limit=1,
            min_quality=0.0,
        )
        assert len(results) == 1
        content_str = json.dumps(results[0])
        assert "teacher@school.edu" not in content_str
        assert "555-123-4567" not in content_str

    def test_contributor_hash_is_anonymous(self, temp_db):
        """Teacher ID is hashed, not stored in plaintext."""
        init_corpus_db()

        contribute_example(
            content_type="lesson_plan",
            subject="ela",
            grade_level="9",
            content={"title": "ELA Lesson"},
            quality_score=4.0,
            teacher_id="real-teacher-id-12345",
        )

        from clawed.corpus import _get_conn

        with _get_conn() as conn:
            row = conn.execute(
                "SELECT contributor_hash FROM corpus_examples",
            ).fetchone()
        assert row["contributor_hash"] is not None
        assert "real-teacher-id-12345" not in row["contributor_hash"]
        # sha256 truncated to 16 hex chars
        assert len(row["contributor_hash"]) == 16
