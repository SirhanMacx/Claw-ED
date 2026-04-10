"""Tests for clawed/validation.py — post-generation output validators."""

from __future__ import annotations

from clawed.master_content import (
    DoNow,
    GuidedNote,
    InstructionSection,
    MasterContent,
    PrimarySource,
    StationDocument,
    StimulusQuestion,
)
from clawed.models import (
    AssessmentQuestion,
    DBQAssessment,
    DifferentiationNotes,
    FormativeAssessment,
    LessonMaterials,
    PacingGuide,
    Quiz,
    Rubric,
    RubricCriterion,
    SummativeAssessment,
    UnitPlan,
    YearMap,
    YearMapUnit,
)
from clawed.validation import (
    check_self_contained,
    validate_alignment,
    validate_dbq,
    validate_formative,
    validate_lesson_materials,
    validate_master_content,
    validate_pacing_guide,
    validate_quiz,
    validate_rubric,
    validate_summative,
    validate_unit_plan,
    validate_year_map,
)

# ── Helpers ────────────────────────────────────────────────────────────────


def _minimal_mc(topic: str = "Reconstruction") -> MasterContent:
    """Return a minimal but valid MasterContent that passes NLAH gates."""
    return MasterContent(
        title=f"Lesson on {topic}",
        subject="US History",
        grade_level="8",
        topic=topic,
        objective="Students will understand Reconstruction.",
        do_now=DoNow(
            stimulus="What do you know about the Civil War?",
            stimulus_type="text_excerpt",
            questions=["Question 1"],
            answers=["Answer 1"],
        ),
        direct_instruction=[
            InstructionSection(
                heading="Introduction",
                content="Reconstruction was the period after the Civil War from 1865 to 1877.",
                teacher_script="Begin here.",
                key_points=["key point one", "key point two"],
            )
        ],
        guided_notes=[
            GuidedNote(prompt=f"Blank {i} ___.", answer=f"answer {i}", section_ref="Introduction")
            for i in range(1, 7)  # NLAH: >= 6
        ],
        primary_sources=[
            PrimarySource(
                id="src1",
                title="Freedmen's Bureau Act",
                source_type="text_excerpt",
                content_text="An act to establish a Bureau...",
                attribution="Congress, 1865",
            ),
            PrimarySource(
                id="src2",
                title="14th Amendment",
                source_type="text_excerpt",
                content_text="All persons born or naturalized...",
                attribution="U.S. Constitution, 1868",
            ),
        ],
        exit_ticket=[
            StimulusQuestion(
                stimulus=f"Read excerpt {i}.",
                stimulus_type="text_excerpt",
                question=f"Question {i}?",
                answer=f"Answer {i}.",
            )
            for i in range(1, 4)  # NLAH: >= 3
        ],
        differentiation=DifferentiationNotes(
            struggling=["Provide graphic organizer"],
            advanced=["Extended essay"],
            ell=["Visual supports"],
        ),
    )


# ── check_self_contained ───────────────────────────────────────────────────


def test_check_self_contained_no_violations():
    text = "This lesson covers the causes of World War I in detail."
    assert check_self_contained(text) == []


def test_check_self_contained_detects_teacher_will_distribute():
    text = "Complete the worksheet. Teacher will distribute materials."
    violations = check_self_contained(text)
    assert len(violations) == 1
    assert "teacher will distribute" in violations[0].lower()


def test_check_self_contained_detects_see_page():
    text = "For more information, see page 47 of your textbook."
    violations = check_self_contained(text)
    assert any("see page" in v.lower() for v in violations)


def test_check_self_contained_detects_insert_placeholder():
    text = "Read the excerpt: [insert primary source here] and answer questions."
    violations = check_self_contained(text)
    assert any("[insert" in v.lower() or "insert" in v.lower() for v in violations)


def test_check_self_contained_case_insensitive():
    text = "TEACHER WILL PROVIDE handouts for this activity."
    violations = check_self_contained(text)
    assert len(violations) >= 1


def test_check_self_contained_multiple_violations():
    text = "Teacher will distribute the worksheet. See page 10 for details."
    violations = check_self_contained(text)
    assert len(violations) >= 2


def test_check_self_contained_refer_to_textbook():
    text = "Refer to the textbook for background reading."
    violations = check_self_contained(text)
    assert len(violations) >= 1


# ── validate_master_content ────────────────────────────────────────────────


def test_validate_master_content_clean():
    mc = _minimal_mc("Reconstruction")
    errors = validate_master_content(mc, "Reconstruction")
    assert errors == []


def test_validate_master_content_no_guided_notes():
    mc = _minimal_mc()
    mc.guided_notes = []
    errors = validate_master_content(mc, "Reconstruction")
    assert any("guided notes" in e.lower() for e in errors)


def test_validate_master_content_no_exit_ticket():
    mc = _minimal_mc()
    mc.exit_ticket = []
    errors = validate_master_content(mc, "Reconstruction")
    assert any("exit ticket" in e.lower() for e in errors)


def test_validate_master_content_no_primary_sources():
    mc = _minimal_mc()
    mc.primary_sources = []
    errors = validate_master_content(mc, "Reconstruction")
    assert any("primary source" in e.lower() for e in errors)


def test_validate_master_content_no_direct_instruction():
    mc = _minimal_mc()
    mc.direct_instruction = []
    errors = validate_master_content(mc, "Reconstruction")
    assert any("instruction" in e.lower() for e in errors)


def test_validate_master_content_topic_drift():
    mc = _minimal_mc("Reconstruction")
    errors = validate_master_content(mc, "French Revolution")
    assert any("topic drift" in e.lower() or "french revolution" in e.lower() for e in errors)


def test_validate_master_content_topic_match_in_topic_field():
    """Topic in mc.topic should satisfy validation even if not in title."""
    mc = MasterContent(
        title="A Great Lesson",  # topic not in title
        subject="US History",
        grade_level="8",
        topic="Reconstruction",  # topic IS here
        objective="Students will understand Reconstruction.",
        do_now=DoNow(
            stimulus="Prompt.",
            stimulus_type="text_excerpt",
            questions=["Q"],
            answers=["A"],
        ),
        direct_instruction=[InstructionSection(heading="H", content="C", teacher_script="S", key_points=["k"])],
        guided_notes=[GuidedNote(prompt="P", answer="A", section_ref="H")],
        primary_sources=[
            PrimarySource(
                id="s1",
                title="T",
                source_type="text_excerpt",
                content_text="text",
                attribution="Author",
            )
        ],
        exit_ticket=[
            StimulusQuestion(
                stimulus="Read this.",
                stimulus_type="text_excerpt",
                question="Q?",
                answer="A.",
            )
        ],
        differentiation=DifferentiationNotes(),
    )
    errors = validate_master_content(mc, "Reconstruction")
    # Should NOT have topic drift error
    assert not any("topic drift" in e.lower() for e in errors)


# ── validate_alignment ─────────────────────────────────────────────────────


def test_validate_alignment_clean():
    mc = _minimal_mc()
    # Put ALL guided note answers into instruction so alignment is 100%
    all_answers = " ".join(n.answer for n in mc.guided_notes)
    mc.direct_instruction[0].content = f"Reconstruction: {all_answers}."
    score, issues = validate_alignment(mc)
    assert score == 100.0
    note_issues = [i for i in issues if "guided note" in i.lower()]
    assert note_issues == []


def test_validate_alignment_mismatched_guided_note():
    mc = _minimal_mc()
    mc.guided_notes[0].answer = "completely unrelated answer xyz"
    score, issues = validate_alignment(mc)
    assert score < 100.0
    assert any("guided note" in i.lower() for i in issues)


def test_validate_alignment_score_percentage():
    mc = _minimal_mc()
    # Match exactly half the guided notes
    half = len(mc.guided_notes) // 2
    matched_answers = " ".join(n.answer for n in mc.guided_notes[:half])
    mc.direct_instruction[0].content = matched_answers
    mc.direct_instruction[0].key_points = []
    score, issues = validate_alignment(mc)
    expected = half / len(mc.guided_notes) * 100
    assert abs(score - expected) < 1.0


def test_validate_alignment_invalid_station_source_ref():
    mc = _minimal_mc()
    mc.stations = [
        StationDocument(
            title="Station 1",
            source_ref="nonexistent_source_id",
            task="Analyze the document.",
            student_directions="Read and answer.",
            teacher_answer_key="Key answers.",
        )
    ]
    _, issues = validate_alignment(mc)
    assert any("station" in i.lower() and "source" in i.lower() for i in issues)


def test_validate_alignment_valid_station_source_ref():
    mc = _minimal_mc()
    mc.stations = [
        StationDocument(
            title="Station 1",
            source_ref="src1",  # matches the PrimarySource id in _minimal_mc
            task="Analyze the document.",
            student_directions="Read and answer.",
            teacher_answer_key="Key answers.",
        )
    ]
    _, issues = validate_alignment(mc)
    station_issues = [i for i in issues if "station" in i.lower() and "source" in i.lower()]
    assert station_issues == []


def test_validate_alignment_empty_exit_ticket_stimulus():
    """Alignment validator catches empty stimulus on exit ticket questions."""
    # We can't construct StimulusQuestion with empty stimulus (validator blocks it)
    # so we build a valid one then patch the field directly.
    mc = _minimal_mc()
    mc.exit_ticket[0].model_fields_set  # access to confirm it's a real instance
    # Bypass pydantic validator to inject bad data for testing
    object.__setattr__(mc.exit_ticket[0], "stimulus", "   ")
    _, issues = validate_alignment(mc)
    assert any("exit ticket" in i.lower() for i in issues)


def test_validate_alignment_no_notes_returns_zero_score():
    mc = _minimal_mc()
    mc.guided_notes = []
    score, _ = validate_alignment(mc)
    assert score == 0.0


# ── validate_quiz ──────────────────────────────────────────────────────────


def _make_quiz(topic: str = "WWI", count: int = 3) -> Quiz:
    return Quiz(
        topic=topic,
        grade_level="8",
        questions=[AssessmentQuestion(question_number=i + 1, question=f"Q{i + 1}?") for i in range(count)],
        answer_key={i + 1: f"A{i + 1}" for i in range(count)},
        total_points=count,
    )


def test_validate_quiz_clean():
    quiz = _make_quiz("WWI", 5)
    errors = validate_quiz(quiz, "WWI", 5)
    assert errors == []


def test_validate_quiz_empty_questions():
    quiz = _make_quiz()
    quiz.questions = []
    errors = validate_quiz(quiz, "WWI", 3)
    assert any("question" in e.lower() for e in errors)


def test_validate_quiz_topic_drift():
    quiz = _make_quiz("WWI")
    errors = validate_quiz(quiz, "French Revolution", 3)
    assert any("topic" in e.lower() or "drift" in e.lower() for e in errors)


def test_validate_quiz_wrong_count():
    quiz = _make_quiz("WWI", 2)
    errors = validate_quiz(quiz, "WWI", 5)
    assert any("question" in e.lower() or "count" in e.lower() for e in errors)


# ── validate_rubric ────────────────────────────────────────────────────────


def _make_rubric(criteria_count: int = 4) -> Rubric:
    return Rubric(
        task_description="Evaluate the essay.",
        criteria=[RubricCriterion(criterion=f"Criterion {i + 1}") for i in range(criteria_count)],
        total_points=criteria_count * 4,
    )


def test_validate_rubric_clean():
    rubric = _make_rubric(4)
    errors = validate_rubric(rubric, 4)
    assert errors == []


def test_validate_rubric_empty_criteria():
    rubric = _make_rubric(0)
    errors = validate_rubric(rubric, 4)
    assert any("criteria" in e.lower() or "criterion" in e.lower() for e in errors)


def test_validate_rubric_wrong_criteria_count():
    rubric = _make_rubric(2)
    errors = validate_rubric(rubric, 4)
    assert len(errors) > 0


# ── validate_year_map ──────────────────────────────────────────────────────


def _make_year_map(subject: str = "US History", unit_count: int = 4) -> YearMap:
    return YearMap(
        subject=subject,
        grade_level="8",
        units=[YearMapUnit(unit_number=i + 1, title=f"Unit {i + 1}", duration_weeks=4) for i in range(unit_count)],
    )


def test_validate_year_map_clean():
    ym = _make_year_map("US History", 4)
    errors = validate_year_map(ym, "US History")
    assert errors == []


def test_validate_year_map_empty_units():
    ym = _make_year_map()
    ym.units = []
    errors = validate_year_map(ym, "US History")
    assert any("unit" in e.lower() for e in errors)


def test_validate_year_map_subject_drift():
    ym = _make_year_map("US History")
    errors = validate_year_map(ym, "Biology")
    assert any("subject" in e.lower() or "drift" in e.lower() for e in errors)


# ── validate_unit_plan ─────────────────────────────────────────────────────


def _make_unit_plan(topic: str = "Reconstruction") -> UnitPlan:
    from clawed.models import LessonBrief

    return UnitPlan(
        title=f"Unit on {topic}",
        subject="US History",
        grade_level="8",
        topic=topic,
        duration_weeks=3,
        overview="Overview text.",
        essential_questions=["Why did Reconstruction fail?"],
        daily_lessons=[LessonBrief(lesson_number=1, topic="Day 1 Topic", description="Day 1 desc")],
    )


def test_validate_unit_plan_clean():
    up = _make_unit_plan("Reconstruction")
    errors = validate_unit_plan(up, "Reconstruction")
    assert errors == []


def test_validate_unit_plan_no_lessons():
    up = _make_unit_plan()
    up.daily_lessons = []
    errors = validate_unit_plan(up, "Reconstruction")
    assert any("lesson" in e.lower() for e in errors)


def test_validate_unit_plan_topic_drift():
    up = _make_unit_plan("Reconstruction")
    errors = validate_unit_plan(up, "World War II")
    assert any("topic" in e.lower() or "drift" in e.lower() for e in errors)


# ── validate_formative ─────────────────────────────────────────────────────


def _make_formative() -> FormativeAssessment:
    return FormativeAssessment(
        lesson_title="Reconstruction Lesson 1",
        objective="Students can identify Reconstruction goals.",
        questions=[AssessmentQuestion(question_number=1, question="What was Reconstruction?")],
        answer_key={1: "The period of rebuilding after the Civil War."},
    )


def test_validate_formative_clean():
    fa = _make_formative()
    errors = validate_formative(fa)
    assert errors == []


def test_validate_formative_empty_questions():
    fa = _make_formative()
    fa.questions = []
    errors = validate_formative(fa)
    assert any("question" in e.lower() for e in errors)


def test_validate_formative_missing_objective():
    fa = _make_formative()
    fa.objective = ""
    errors = validate_formative(fa)
    assert any("objective" in e.lower() for e in errors)


# ── validate_summative ─────────────────────────────────────────────────────


def _make_summative() -> SummativeAssessment:
    from clawed.models import SummativeQuestion

    return SummativeAssessment(
        unit_title="Reconstruction Unit",
        subject="US History",
        grade_level="8",
        objectives=["Understand Reconstruction goals"],
        questions=[SummativeQuestion(question_number=1, question="What was the 13th Amendment?")],
        total_points=10,
    )


def test_validate_summative_clean():
    sa = _make_summative()
    errors = validate_summative(sa)
    assert errors == []


def test_validate_summative_empty_questions():
    sa = _make_summative()
    sa.questions = []
    errors = validate_summative(sa)
    assert any("question" in e.lower() for e in errors)


def test_validate_summative_empty_objectives():
    sa = _make_summative()
    sa.objectives = []
    errors = validate_summative(sa)
    assert any("objective" in e.lower() for e in errors)


# ── validate_dbq ───────────────────────────────────────────────────────────


def _make_dbq() -> DBQAssessment:
    from clawed.models import DBQDocument

    return DBQAssessment(
        topic="Reconstruction",
        grade_level="8",
        background="After the Civil War...",
        documents=[
            DBQDocument(
                document_number=1,
                title="Freedmen's Bureau Report",
                content="Congress established the Bureau...",
            )
        ],
        essay_prompt="Using the documents, analyze Reconstruction.",
        model_answer="Reconstruction aimed to...",
    )


def test_validate_dbq_clean():
    dbq = _make_dbq()
    errors = validate_dbq(dbq)
    assert errors == []


def test_validate_dbq_empty_documents():
    dbq = _make_dbq()
    dbq.documents = []
    errors = validate_dbq(dbq)
    assert any("document" in e.lower() for e in errors)


def test_validate_dbq_missing_essay_prompt():
    dbq = _make_dbq()
    dbq.essay_prompt = ""
    errors = validate_dbq(dbq)
    assert any("essay" in e.lower() or "prompt" in e.lower() for e in errors)


# ── validate_lesson_materials ──────────────────────────────────────────────


def _make_lesson_materials() -> LessonMaterials:
    from clawed.models import WorksheetItem

    return LessonMaterials(
        lesson_title="Reconstruction Day 1",
        worksheet_items=[WorksheetItem(item_number=1, item_type="short_answer", prompt="Describe Reconstruction.")],
        assessment_questions=[AssessmentQuestion(question_number=1, question="What happened in 1865?")],
    )


def test_validate_lesson_materials_clean():
    mats = _make_lesson_materials()
    errors = validate_lesson_materials(mats)
    assert errors == []


def test_validate_lesson_materials_empty_worksheet():
    mats = _make_lesson_materials()
    mats.worksheet_items = []
    errors = validate_lesson_materials(mats)
    assert any("worksheet" in e.lower() for e in errors)


def test_validate_lesson_materials_empty_assessment_questions():
    mats = _make_lesson_materials()
    mats.assessment_questions = []
    errors = validate_lesson_materials(mats)
    assert any("assessment" in e.lower() or "question" in e.lower() for e in errors)


# ── validate_pacing_guide ──────────────────────────────────────────────────


def _make_pacing_guide() -> PacingGuide:
    from clawed.models import PacingWeek

    return PacingGuide(
        subject="US History",
        grade_level="8",
        school_year="2025-2026",
        start_date="2025-09-02",
        weeks=[
            PacingWeek(
                week_number=1,
                start_date="2025-09-02",
                end_date="2025-09-06",
                unit_title="Reconstruction",
                unit_number=1,
                topics=["Introduction to Reconstruction"],
            )
        ],
    )


def test_validate_pacing_guide_clean():
    pg = _make_pacing_guide()
    errors = validate_pacing_guide(pg)
    assert errors == []


def test_validate_pacing_guide_empty_weeks():
    pg = _make_pacing_guide()
    pg.weeks = []
    errors = validate_pacing_guide(pg)
    assert any("week" in e.lower() for e in errors)


def test_validate_pacing_guide_missing_start_date():
    pg = _make_pacing_guide()
    pg.start_date = ""
    errors = validate_pacing_guide(pg)
    assert any("start" in e.lower() or "date" in e.lower() for e in errors)
