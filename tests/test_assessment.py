"""Tests for assessment intelligence layer — models, generator, and CLI."""

from pathlib import Path

import pytest

from clawed.models import (
    AppConfig,
    AssessmentQuestion,
    DailyLesson,
    DBQAssessment,
    DBQDocument,
    FormativeAssessment,
    LLMProvider,
    Quiz,
    Rubric,
    RubricCriterion,
    SummativeAssessment,
    SummativeQuestion,
    TeacherPersona,
    TeachingStyle,
    UnitPlan,
)

# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def persona():
    return TeacherPersona(
        name="Mr. Rivera",
        teaching_style=TeachingStyle.SOCRATIC,
        subject_area="US History",
        grade_levels=["10", "11"],
        favorite_strategies=["Socratic seminar", "primary source analysis"],
    )


@pytest.fixture
def lesson():
    return DailyLesson(
        title="Causes of the American Revolution",
        lesson_number=3,
        objective="SWBAT identify and explain 3 key causes of the American Revolution",
        standards=["C3.D2.His.1.9-12"],
        do_now="List one thing you know about colonial grievances.",
        direct_instruction="Overview of taxation without representation...",
        guided_practice="Analyze excerpts from the Stamp Act...",
        independent_work="Write a paragraph explaining the most important cause.",
    )


@pytest.fixture
def unit():
    return UnitPlan(
        title="The American Revolution",
        subject="US History",
        grade_level="10",
        topic="American Revolution",
        duration_weeks=3,
        overview="Three-week unit on causes, events, and consequences of the Revolution.",
        essential_questions=["Why did the colonies declare independence?"],
        enduring_understandings=[
            "Colonial grievances about taxation and representation drove revolution.",
            "Enlightenment ideas shaped revolutionary ideology.",
            "The Revolution had lasting effects on American governance.",
        ],
        standards=["C3.D2.His.1.9-12", "C3.D2.His.2.9-12"],
    )


# ── FormativeAssessment model ─────────────────────────────────────────


class TestFormativeAssessmentModel:
    def test_create_formative(self):
        fa = FormativeAssessment(
            lesson_title="Causes of the American Revolution",
            objective="SWBAT identify 3 causes",
            questions=[
                AssessmentQuestion(
                    question_number=1,
                    question_type="multiple_choice",
                    question="Which act taxed paper goods?",
                    choices=["A) Sugar Act", "B) Stamp Act", "C) Tea Act", "D) Quartering Act"],
                    correct_answer="B) Stamp Act",
                    point_value=1,
                ),
                AssessmentQuestion(
                    question_number=2,
                    question_type="short_answer",
                    question="Explain taxation without representation.",
                    correct_answer="Colonists were taxed by Parliament without elected representatives.",
                    point_value=2,
                ),
            ],
            answer_key={1: "B) Stamp Act", 2: "Colonists were taxed..."},
            time_minutes=5,
        )
        assert fa.lesson_title == "Causes of the American Revolution"
        assert len(fa.questions) == 2
        assert fa.time_minutes == 5
        assert 1 in fa.answer_key

    def test_formative_defaults(self):
        fa = FormativeAssessment(
            lesson_title="Test",
            objective="Test objective",
        )
        assert fa.questions == []
        assert fa.answer_key == {}
        assert fa.time_minutes == 5


# ── SummativeAssessment model ─────────────────────────────────────────


class TestSummativeAssessmentModel:
    def test_create_summative(self):
        sa = SummativeAssessment(
            unit_title="The American Revolution",
            subject="US History",
            grade_level="10",
            objectives=["Identify causes", "Analyze key events"],
            questions=[
                SummativeQuestion(
                    question_number=1,
                    question_type="multiple_choice",
                    blooms_level="remember",
                    question="When was the Declaration signed?",
                    choices=["A) 1774", "B) 1775", "C) 1776", "D) 1777"],
                    correct_answer="C) 1776",
                    point_value=2,
                    standard_aligned="C3.D2.His.1.9-12",
                ),
                SummativeQuestion(
                    question_number=2,
                    question_type="essay",
                    blooms_level="evaluate",
                    question="Was the Revolution inevitable? Argue your position.",
                    correct_answer="Model answer...",
                    point_value=10,
                ),
            ],
            rubric=[
                RubricCriterion(
                    criterion="Thesis",
                    excellent="Clear, defensible thesis",
                    proficient="Adequate thesis",
                    developing="Vague thesis",
                    beginning="No thesis",
                ),
            ],
            total_points=50,
            time_minutes=45,
        )
        assert sa.unit_title == "The American Revolution"
        assert len(sa.questions) == 2
        assert sa.questions[0].blooms_level == "remember"
        assert sa.questions[1].blooms_level == "evaluate"
        assert sa.total_points == 50
        assert len(sa.rubric) == 1

    def test_summative_defaults(self):
        sa = SummativeAssessment(
            unit_title="Test",
            subject="Math",
            grade_level="8",
        )
        assert sa.questions == []
        assert sa.objectives == []
        assert sa.time_minutes == 45


# ── DBQAssessment model ──────────────────────────────────────────────


class TestDBQAssessmentModel:
    def test_create_dbq(self):
        dbq = DBQAssessment(
            topic="Industrialization in America",
            grade_level="10",
            background="During the late 19th century, America underwent rapid industrialization...",
            documents=[
                DBQDocument(
                    document_number=1,
                    title="Excerpt from Andrew Carnegie's 'Gospel of Wealth'",
                    source="Andrew Carnegie, 1889",
                    date="1889",
                    content="The problem of our age is the proper administration of wealth...",
                    scaffolding_questions=[
                        "What does Carnegie argue about the role of the wealthy?",
                        "How might a factory worker respond to this argument?",
                    ],
                ),
                DBQDocument(
                    document_number=2,
                    title="Photo: Child laborers in a textile mill",
                    source="Lewis Hine, 1908",
                    date="1908",
                    content="[Photograph description: Young children operating large machines...]",
                    scaffolding_questions=[
                        "What does this image reveal about working conditions?",
                        "Why might reformers have used photographs like this?",
                    ],
                ),
            ],
            essay_prompt=(
                "Using the documents and your knowledge of US history, "
                "write an essay discussing the effects of industrialization on American society."
            ),
            model_answer="Industrialization transformed American society in profound ways...",
            rubric=[
                RubricCriterion(
                    criterion="Document Analysis",
                    excellent="Analyzes 4-5 documents with specific evidence",
                    proficient="References 3-4 documents",
                    developing="References 1-2 documents",
                    beginning="No document use",
                ),
            ],
            time_minutes=60,
        )
        assert dbq.topic == "Industrialization in America"
        assert len(dbq.documents) == 2
        assert dbq.documents[0].document_number == 1
        assert len(dbq.documents[0].scaffolding_questions) == 2
        assert "essay" in dbq.essay_prompt.lower()
        assert len(dbq.model_answer) > 0
        assert len(dbq.rubric) == 1

    def test_dbq_document_model(self):
        doc = DBQDocument(
            document_number=1,
            title="Test Document",
            source="Test Source",
        )
        assert doc.content == ""
        assert doc.scaffolding_questions == []
        assert doc.date == ""

    def test_dbq_defaults(self):
        dbq = DBQAssessment(topic="Test", grade_level="8")
        assert dbq.documents == []
        assert dbq.background == ""
        assert dbq.essay_prompt == ""
        assert dbq.model_answer == ""
        assert dbq.time_minutes == 60


# ── Quiz model ───────────────────────────────────────────────────────


class TestQuizModel:
    def test_create_quiz(self):
        quiz = Quiz(
            topic="Causes of WWI",
            grade_level="10",
            questions=[
                AssessmentQuestion(
                    question_number=1,
                    question_type="multiple_choice",
                    question="What event triggered WWI?",
                    choices=[
                        "A) Sinking of the Lusitania",
                        "B) Assassination of Archduke Franz Ferdinand",
                        "C) Treaty of Versailles",
                        "D) Russian Revolution",
                    ],
                    correct_answer="B) Assassination of Archduke Franz Ferdinand",
                    point_value=1,
                ),
            ],
            answer_key={1: "B) Assassination of Archduke Franz Ferdinand"},
            total_points=10,
            time_minutes=10,
        )
        assert quiz.topic == "Causes of WWI"
        assert len(quiz.questions) == 1
        assert quiz.total_points == 10
        assert 1 in quiz.answer_key

    def test_quiz_defaults(self):
        quiz = Quiz(topic="Test", grade_level="8")
        assert quiz.questions == []
        assert quiz.answer_key == {}
        assert quiz.total_points == 0
        assert quiz.time_minutes == 15


# ── Rubric model ─────────────────────────────────────────────────────


class TestRubricModel:
    def test_create_rubric(self):
        r = Rubric(
            task_description="Write an argumentative essay on whether the Revolution was justified.",
            criteria=[
                RubricCriterion(
                    criterion="Thesis",
                    excellent="Sophisticated thesis with nuance",
                    proficient="Clear thesis",
                    developing="Vague thesis",
                    beginning="No thesis",
                ),
                RubricCriterion(
                    criterion="Evidence",
                    excellent="3+ pieces of specific evidence with analysis",
                    proficient="2-3 pieces of evidence",
                    developing="1 piece of evidence, mostly summary",
                    beginning="No evidence cited",
                ),
            ],
            total_points=8,
        )
        assert r.task_description.startswith("Write an argumentative")
        assert len(r.criteria) == 2
        assert r.total_points == 8

    def test_rubric_defaults(self):
        r = Rubric(task_description="Test task")
        assert r.criteria == []
        assert r.total_points == 0


# ── SummativeQuestion model ──────────────────────────────────────────


class TestSummativeQuestionModel:
    def test_summative_question_fields(self):
        sq = SummativeQuestion(
            question_number=1,
            question_type="essay",
            blooms_level="evaluate",
            question="Argue whether...",
            point_value=10,
            standard_aligned="C3.D2.His.1.9-12",
        )
        assert sq.blooms_level == "evaluate"
        assert sq.standard_aligned == "C3.D2.His.1.9-12"
        assert sq.point_value == 10

    def test_summative_question_defaults(self):
        sq = SummativeQuestion(question_number=1, question="Test?")
        assert sq.question_type == "multiple_choice"
        assert sq.blooms_level == "remember"
        assert sq.standard_aligned == ""
        assert sq.choices == []


# ── AssessmentGenerator class ────────────────────────────────────────


class TestAssessmentGeneratorClass:
    def test_import_and_construct(self):
        from clawed.assessment import AssessmentGenerator

        gen = AssessmentGenerator()
        assert gen.config is None

    def test_construct_with_config(self):
        from clawed.assessment import AssessmentGenerator

        config = AppConfig(provider=LLMProvider.OLLAMA)
        gen = AssessmentGenerator(config)
        assert gen.config.provider == LLMProvider.OLLAMA


# ── Prompt templates exist ───────────────────────────────────────────


class TestPromptTemplates:
    @pytest.mark.parametrize(
        "template",
        [
            "formative_assessment.txt",
            "summative_assessment.txt",
            "dbq_assessment.txt",
            "quiz.txt",
            "rubric.txt",
        ],
    )
    def test_prompt_template_exists(self, template):
        path = Path(__file__).parent.parent / "clawed" / "prompts" / template
        assert path.exists(), f"Missing prompt template: {template}"
        content = path.read_text()
        assert len(content) > 100, f"Template {template} seems too short"

    @pytest.mark.parametrize(
        "template,placeholders",
        [
            ("formative_assessment.txt", ["{persona}", "{lesson_title}", "{objective}"]),
            ("summative_assessment.txt", ["{persona}", "{unit_title}", "{objectives}"]),
            ("dbq_assessment.txt", ["{persona}", "{topic}", "{grade_level}"]),
            ("quiz.txt", ["{persona}", "{topic}", "{question_count}"]),
            ("rubric.txt", ["{persona}", "{task_description}", "{criteria_count}"]),
        ],
    )
    def test_prompt_template_has_placeholders(self, template, placeholders):
        path = Path(__file__).parent.parent / "clawed" / "prompts" / template
        content = path.read_text()
        for ph in placeholders:
            assert ph in content, f"Template {template} missing placeholder {ph}"


# ── Model router has assessment task ─────────────────────────────────


class TestModelRouterAssessment:
    def test_assessment_task_in_router(self):
        from clawed.model_router import DEFAULT_TIER_MODELS, TASK_TIERS, ModelTier

        assert "assessment" in TASK_TIERS
        assert TASK_TIERS["assessment"] == ModelTier.DEEP
        assert DEFAULT_TIER_MODELS["work"] == "gemma4:31b-cloud"

    def test_route_assessment_task(self):
        from clawed.model_router import route

        config = AppConfig(provider=LLMProvider.OLLAMA, ollama_model="llama3.2")
        routed = route("assessment", config)
        assert routed.ollama_model == "gemma4:31b-cloud"


# ── save_assessment helper ───────────────────────────────────────────


class TestSaveAssessment:
    def test_save_formative(self, tmp_path):
        from clawed.assessment import save_assessment

        fa = FormativeAssessment(
            lesson_title="Test Lesson",
            objective="Test objective",
        )
        path = save_assessment(fa, tmp_path, "formative")
        assert path.exists()
        assert "formative_" in path.name
        assert path.suffix == ".json"

    def test_save_dbq(self, tmp_path):
        from clawed.assessment import save_assessment

        dbq = DBQAssessment(topic="Industrialization", grade_level="10")
        path = save_assessment(dbq, tmp_path, "dbq")
        assert path.exists()
        assert "dbq_" in path.name

    def test_save_quiz(self, tmp_path):
        from clawed.assessment import save_assessment

        quiz = Quiz(topic="WWI Causes", grade_level="10")
        path = save_assessment(quiz, tmp_path, "quiz")
        assert path.exists()
        assert "quiz_" in path.name

    def test_save_rubric(self, tmp_path):
        from clawed.assessment import save_assessment

        r = Rubric(task_description="Write an essay")
        path = save_assessment(r, tmp_path, "rubric")
        assert path.exists()
        assert "rubric_" in path.name

    def test_save_creates_directory(self, tmp_path):
        from clawed.assessment import save_assessment

        nested = tmp_path / "deep" / "nested"
        fa = FormativeAssessment(lesson_title="Test", objective="Test")
        path = save_assessment(fa, nested, "formative")
        assert path.exists()

    def test_save_summative(self, tmp_path):
        from clawed.assessment import save_assessment

        sa = SummativeAssessment(
            unit_title="American Revolution",
            subject="US History",
            grade_level="10",
        )
        path = save_assessment(sa, tmp_path, "summative")
        assert path.exists()
        assert "summative_" in path.name


# ── Convenience wrappers exist ───────────────────────────────────────


class TestConvenienceWrappers:
    def test_convenience_functions_importable(self):
        from clawed.assessment import (
            generate_dbq,
            generate_formative,
            generate_quiz,
            generate_rubric,
            generate_summative,
        )

        # All are callable coroutines
        assert callable(generate_formative)
        assert callable(generate_summative)
        assert callable(generate_dbq)
        assert callable(generate_rubric)
        assert callable(generate_quiz)


# ── DBQ-specific tests (critical for Jon / NYS Regents) ──────────────


class TestDBQStructure:
    """DBQ format is critical for Jon (NYS Regents). These tests verify the
    structural integrity of the DBQ model for Regents-style assessments."""

    def test_dbq_has_background_documents_prompt_answer(self):
        """A complete DBQ must have all four components."""
        dbq = DBQAssessment(
            topic="Industrialization",
            grade_level="10",
            background="During the Gilded Age...",
            documents=[
                DBQDocument(
                    document_number=1,
                    title="Carnegie's Gospel of Wealth",
                    source="Andrew Carnegie, 1889",
                    date="1889",
                    content="The proper administration of wealth...",
                    scaffolding_questions=["What does Carnegie argue?"],
                ),
            ],
            essay_prompt="Using the documents and your knowledge...",
            model_answer="The Gilded Age transformed...",
        )
        assert len(dbq.background) > 0
        assert len(dbq.documents) > 0
        assert len(dbq.essay_prompt) > 0
        assert len(dbq.model_answer) > 0

    def test_dbq_documents_have_scaffolding(self):
        """Each DBQ document must support scaffolding questions."""
        doc = DBQDocument(
            document_number=1,
            title="Test Doc",
            source="Test Source, 1900",
            date="1900",
            content="Primary source text...",
            scaffolding_questions=[
                "What is the author's point of view?",
                "What evidence does the document provide?",
                "How does this relate to the topic?",
            ],
        )
        assert len(doc.scaffolding_questions) == 3
        assert all(q.endswith("?") for q in doc.scaffolding_questions)

    def test_dbq_rubric_covers_regents_criteria(self):
        """NYS Regents DBQ rubric should cover thesis, docs, outside knowledge, writing."""
        rubric = [
            RubricCriterion(criterion="Thesis/Claim", excellent="Clear analytical thesis"),
            RubricCriterion(criterion="Document Analysis", excellent="Analyzes 4-5 docs"),
            RubricCriterion(criterion="Outside Knowledge", excellent="Substantial outside knowledge"),
            RubricCriterion(criterion="Organization & Writing", excellent="Well-organized essay"),
        ]
        criteria_names = [c.criterion for c in rubric]
        assert "Thesis/Claim" in criteria_names
        assert "Document Analysis" in criteria_names
        assert "Outside Knowledge" in criteria_names
        assert "Organization & Writing" in criteria_names
