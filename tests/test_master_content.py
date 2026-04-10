"""Tests for clawed.master_content — MasterContent and sub-models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from clawed.master_content import (
    DoNow,
    GuidedNote,
    InstructionSection,
    MasterContent,
    PrimarySource,
    StationDocument,
    StimulusQuestion,
    VocabularyEntry,
)
from clawed.models import DailyLesson, DifferentiationNotes

# ── helpers ────────────────────────────────────────────────────────────────


def _make_master_content(**overrides) -> MasterContent:
    """Return a minimal but fully-valid MasterContent instance."""
    defaults = dict(
        title="The Industrial Revolution",
        subject="Social Studies",
        grade_level="8",
        topic="Industrial Revolution",
        standards=["SS.8.1", "SS.8.2"],
        objective="Students will analyze causes of the Industrial Revolution.",
        duration_minutes=45,
        vocabulary=[
            VocabularyEntry(
                term="industrialization",
                definition="Process of developing industry on a large scale.",
                context_sentence="Industrialization transformed daily life in 19th-century Britain.",
            )
        ],
        primary_sources=[
            PrimarySource(
                id="ps1",
                title="Factory Conditions Report, 1833",
                source_type="text_excerpt",
                content_text="Children as young as six worked 14-hour days...",
                attribution="Parliamentary Commission, 1833",
                scaffolding_questions=["What working conditions are described?"],
            )
        ],
        do_now=DoNow(
            stimulus="Look at the image of a 19th-century factory.",
            stimulus_type="image",
            questions=["What do you notice?", "What do you wonder?"],
            answers=["Students observe machinery and workers.", "Vary."],
        ),
        direct_instruction=[
            InstructionSection(
                heading="Background: Pre-Industrial Britain",
                content="Before 1750, most goods were made by hand in rural homes.",
                teacher_script="Say: 'Imagine a world without machines…'",
                key_points=["Cottage industry", "Agricultural economy"],
            )
        ],
        guided_notes=[
            GuidedNote(
                prompt="The Industrial Revolution began in ______.",
                answer="Britain",
                section_ref="Background: Pre-Industrial Britain",
            )
        ],
        stations=[
            StationDocument(
                title="Station A: Factory Life",
                source_ref="ps1",
                task="Read the excerpt and answer the questions.",
                student_directions="Read carefully, then respond in complete sentences.",
                teacher_answer_key="Children worked long hours in dangerous conditions.",
            )
        ],
        exit_ticket=[
            StimulusQuestion(
                stimulus="Textile workers earned less than 1 shilling per day.",
                stimulus_type="text_excerpt",
                question="How did factory wages affect working-class families?",
                answer="Low wages forced multiple family members to work.",
                cognitive_level="analysis",
            )
        ],
        differentiation=DifferentiationNotes(
            struggling=["Provide sentence starters"],
            advanced=["Compare to today's globalization"],
            ell=["Provide bilingual vocabulary sheet"],
        ),
        homework="Read pages 45–52 and answer questions 1–3.",
        materials_needed=["Chromebook", "Student packet"],
    )
    defaults.update(overrides)
    return MasterContent(**defaults)


# ── test 1: minimal valid MasterContent ───────────────────────────────────


def test_minimal_valid_master_content():
    mc = _make_master_content()
    assert mc.title == "The Industrial Revolution"
    assert mc.subject == "Social Studies"
    assert mc.grade_level == "8"
    assert mc.duration_minutes == 45
    assert len(mc.vocabulary) == 1
    assert len(mc.primary_sources) == 1
    assert len(mc.direct_instruction) == 1
    assert len(mc.guided_notes) == 1
    assert len(mc.exit_ticket) == 1
    assert mc.differentiation.struggling == ["Provide sentence starters"]


# ── test 2: empty stimulus raises ValidationError ─────────────────────────


def test_stimulus_question_requires_stimulus():
    with pytest.raises(ValidationError) as exc_info:
        StimulusQuestion(
            stimulus="",
            stimulus_type="text_excerpt",
            question="What happened?",
            answer="Something happened.",
        )
    assert "stimulus must not be empty" in str(exc_info.value)


def test_stimulus_question_whitespace_only_raises():
    with pytest.raises(ValidationError):
        StimulusQuestion(
            stimulus="   ",
            stimulus_type="text_excerpt",
            question="What happened?",
            answer="Something happened.",
        )


# ── test 3: to_daily_lesson backwards compat ──────────────────────────────


def test_to_daily_lesson_backwards_compat():
    mc = _make_master_content()
    dl = mc.to_daily_lesson()
    assert isinstance(dl, DailyLesson)
    assert dl.title == mc.title
    assert dl.objective == mc.objective
    assert dl.standards == mc.standards
    assert dl.homework == mc.homework
    assert dl.materials_needed == mc.materials_needed
    # do_now should contain the stimulus
    assert "factory" in dl.do_now.lower()
    # direct_instruction should contain heading
    assert "Pre-Industrial Britain" in dl.direct_instruction
    # guided_practice should contain the prompt
    assert "Industrial Revolution began" in dl.guided_practice
    # exit ticket list should have one item with combined stimulus + question
    assert len(dl.exit_ticket) == 1
    assert "shilling" in dl.exit_ticket[0].question
    assert "wages affect" in dl.exit_ticket[0].question


def test_to_daily_lesson_no_independent_work():
    mc = _make_master_content(independent_work=None)
    dl = mc.to_daily_lesson()
    assert dl.independent_work == ""


def test_to_daily_lesson_with_independent_work():
    from clawed.master_content import IndependentWork

    mc = _make_master_content(
        independent_work=IndependentWork(
            task="Write a paragraph comparing factory and farm work.",
            rubric_snippet="4 = strong evidence, 1 = no evidence",
        )
    )
    dl = mc.to_daily_lesson()
    assert "paragraph" in dl.independent_work


# ── test 4: vocabulary entry fields ───────────────────────────────────────


def test_vocabulary_entry_fields():
    entry = VocabularyEntry(
        term="capitalism",
        definition="An economic system based on private ownership.",
        context_sentence="Capitalism drove investment in new factories.",
        image_spec="illustration of coins and factory",
    )
    assert entry.term == "capitalism"
    assert entry.definition.startswith("An economic system")
    assert entry.context_sentence == "Capitalism drove investment in new factories."
    assert entry.image_spec == "illustration of coins and factory"


def test_vocabulary_entry_image_spec_defaults_empty():
    entry = VocabularyEntry(
        term="urbanization",
        definition="Growth of cities.",
        context_sentence="Urbanization accelerated after 1800.",
    )
    assert entry.image_spec == ""


# ── test 5: primary source fields ─────────────────────────────────────────


def test_primary_source_fields():
    ps = PrimarySource(
        id="ps2",
        title="Child Labour Report",
        source_type="text_excerpt",
        content_text="Children were employed in dangerous mines.",
        attribution="Ashley Commission, 1842",
        scaffolding_questions=["Who wrote this?", "What problem is described?"],
    )
    assert ps.id == "ps2"
    assert ps.source_type == "text_excerpt"
    assert len(ps.scaffolding_questions) == 2
    assert ps.image_spec == ""


# ── test 6: station document fields ───────────────────────────────────────


def test_station_document_fields():
    station = StationDocument(
        title="Station B: Transportation Revolution",
        source_ref="ps3",
        task="Annotate the map showing railroad expansion.",
        student_directions="Use your pencil to trace the railroad lines.",
        teacher_answer_key="Students should identify the Liverpool–Manchester line.",
    )
    assert station.title == "Station B: Transportation Revolution"
    assert station.source_ref == "ps3"
    assert "map" in station.task


# ── test 7: guided note count ─────────────────────────────────────────────


def test_guided_note_count():
    notes = [
        GuidedNote(
            prompt=f"Key fact number {i} is ______.",
            answer=f"Answer {i}",
            section_ref="Section 1",
        )
        for i in range(5)
    ]
    mc = _make_master_content(guided_notes=notes)
    assert len(mc.guided_notes) == 5
    assert mc.guided_notes[0].prompt == "Key fact number 0 is ______."
    assert mc.guided_notes[4].answer == "Answer 4"


def test_guided_note_section_ref():
    note = GuidedNote(
        prompt="The steam engine was invented by ______.",
        answer="James Watt",
        section_ref="Background: Pre-Industrial Britain",
    )
    assert note.section_ref == "Background: Pre-Industrial Britain"
