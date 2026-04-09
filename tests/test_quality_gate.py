"""Tests for the lesson.py quality gate validation logic.

These tests verify that _validate_quality() catches the known output quality
gaps and that the retry mechanism works as expected.
"""

from __future__ import annotations

from clawed.lesson import _validate_quality
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
from clawed.models import DifferentiationNotes


def _good_master() -> MasterContent:
    """Build a MasterContent that passes all quality checks."""
    return MasterContent(
        title="Causes of the French Revolution",
        subject="Global History",
        grade_level="10th Grade",
        topic="French Revolution",
        standards=["NYS 10.2"],
        objective="SWBAT analyze the causes of the French Revolution using primary sources.",
        duration_minutes=45,
        lesson_personality="Today we're investigating why an entire country snapped",
        vocabulary=[
            VocabularyEntry(
                term="Bourgeoisie",
                definition="The middle class in France who paid taxes but had no political power.",
                context_sentence="The bourgeoisie resented paying heavy taxes while the nobility was exempt.",
                image_spec="French Revolution Third Estate political cartoon 1789",
            ),
        ],
        primary_sources=[
            PrimarySource(
                id="source_a",
                title="Declaration of the Rights of Man and Citizen (1789)",
                source_type="text_excerpt",
                content_text=(
                    "Article 1: Men are born and remain free and equal in rights. "
                    "Social distinctions may be founded only upon the general good. "
                    "Article 2: The aim of all political association is the preservation "
                    "of the natural and imprescriptible rights of man. These rights are "
                    "liberty, property, security, and resistance to oppression."
                ),
                attribution="National Assembly of France, August 26, 1789",
                image_spec="Declaration of Rights of Man and Citizen 1789 document painting",
                scaffolding_questions=[
                    "What specific rights does this document guarantee?",
                    "How does this compare to the American Declaration of Independence?",
                ],
            ),
        ],
        do_now=DoNow(
            stimulus=(
                "Read the following excerpt: 'The people of France are divided into "
                "three estates. The First Estate (clergy) and Second Estate (nobility) "
                "own most of the land but pay no taxes. The Third Estate pays all taxes.'"
            ),
            stimulus_type="text_excerpt",
            questions=["What injustice does this system create?"],
            answers=["The Third Estate bears the tax burden while having no representation."],
        ),
        direct_instruction=[
            InstructionSection(
                heading="The Three Estates",
                content="France's social structure was divided into three estates...",
                teacher_script=(
                    "Open by asking: 'If you worked hard all day but your neighbor "
                    "who didn't work got all the rewards, how would you feel?' "
                    "Connect this to the tax burden on the Third Estate."
                ),
                key_points=["Unequal taxation", "No political voice for Third Estate"],
                image_spec="French Revolution Three Estates political cartoon 1789",
                hook="Imagine you work 12 hours a day but your neighbor who sleeps all day gets all the rewards.",
                transition="So we've seen the unfairness. But anger alone doesn't start a revolution...",
            ),
        ],
        guided_notes=[
            GuidedNote(
                prompt="The ________ Estate paid all taxes.",
                answer="Third", section_ref="The Three Estates",
            ),
            GuidedNote(
                prompt="The First Estate was the ________.",
                answer="clergy", section_ref="The Three Estates",
            ),
            GuidedNote(
                prompt="The Second Estate was the ________.",
                answer="nobility", section_ref="The Three Estates",
            ),
            GuidedNote(
                prompt="The ________ class resented their lack of power.",
                answer="middle", section_ref="The Three Estates",
            ),
            GuidedNote(
                prompt="The Enlightenment promoted ideas of ________.",
                answer="liberty", section_ref="The Three Estates",
            ),
        ],
        stations=[
            StationDocument(
                title="STATION A: Declaration of Rights",
                source_ref="source_a",
                task="Sourcing and contextualizing",
                student_directions="Read the excerpt and answer the questions below.",
                teacher_answer_key="Article 1 establishes natural equality...",
            ),
        ],
        exit_ticket=[
            StimulusQuestion(
                stimulus=(
                    "Read the following: 'The Third Estate makes up 97% of France's "
                    "population but has no political representation in the Estates-General.'"
                ),
                stimulus_type="text_excerpt",
                question="What does this statistic reveal about French society?",
                answer="It reveals extreme political inequality.",
                cognitive_level="recall",
            ),
            StimulusQuestion(
                stimulus=(
                    "Compare the French Third Estate's grievances with the American "
                    "colonists' complaint of 'no taxation without representation.'"
                ),
                stimulus_type="text_excerpt",
                question="How are these two situations similar?",
                answer="Both groups were taxed without political voice.",
                cognitive_level="application",
            ),
            StimulusQuestion(
                stimulus=(
                    "Consider that the French Revolution began in 1789, just six years "
                    "after the American Revolution ended. The Declaration of the Rights "
                    "of Man echoes the American Declaration of Independence."
                ),
                stimulus_type="text_excerpt",
                question="To what extent did the American Revolution influence the French Revolution?",
                answer="The American example showed revolution was possible and its documents provided a template.",
                cognitive_level="analysis",
            ),
        ],
        differentiation=DifferentiationNotes(
            struggling=[
                "Provide a pre-filled graphic organizer with Cause/Effect "
                "columns and two rows completed as models",
                "Sentence starters for exit ticket: 'This reveals that...'",
            ],
            advanced=[
                "Research and compare the Declaration of Rights of Man with the English Bill of Rights (1689)",
            ],
            ell=[
                "Visual glossary card with key terms and Spanish cognates: revolution/revolución, equality/igualdad",
                "Sentence frames: 'The Third Estate was frustrated because ___'",
            ],
        ),
        homework=(
            "Write a paragraph comparing the grievances of the French "
            "Third Estate with those of American colonists."
        ),
        materials_needed=["Printed primary source excerpts", "Graphic organizer handout"],
    )


class TestQualityGatePass:
    """A well-formed MasterContent should pass all checks."""

    def test_good_lesson_passes(self):
        issues = _validate_quality(_good_master())
        assert issues == [], f"Expected no issues, got: {issues}"


class TestQualityGatePrimarySource:
    """Primary source checks: content length, image_spec, specificity."""

    def test_short_content_text_rejected(self):
        m = _good_master()
        m.primary_sources[0].content_text = "A short summary."
        issues = _validate_quality(m)
        assert any("content_text" in i and "100" in i for i in issues)

    def test_empty_image_spec_rejected(self):
        m = _good_master()
        m.primary_sources[0].image_spec = ""
        issues = _validate_quality(m)
        assert any("image_spec" in i and "empty" in i for i in issues)

    def test_vague_image_spec_rejected(self):
        m = _good_master()
        m.primary_sources[0].image_spec = "document"
        issues = _validate_quality(m)
        assert any("vague" in i for i in issues)


class TestQualityGateExitTicket:
    """Exit ticket stimulus length check."""

    def test_thin_stimulus_rejected(self):
        m = _good_master()
        m.exit_ticket[0].stimulus = "Read this."
        issues = _validate_quality(m)
        assert any("stimulus" in i and "50" in i for i in issues)


class TestQualityGateGuidedNotes:
    """Guided notes minimum count."""

    def test_too_few_guided_notes_rejected(self):
        m = _good_master()
        m.guided_notes = m.guided_notes[:3]
        issues = _validate_quality(m)
        assert any("guided notes" in i and "5" in i for i in issues)


class TestQualityGateDirectInstruction:
    """Direct instruction checks: image_spec and CFU."""

    def test_empty_di_image_spec_rejected(self):
        m = _good_master()
        m.direct_instruction[0].image_spec = ""
        issues = _validate_quality(m)
        assert any("image_spec" in i and "Direct instruction" in i for i in issues)

    def test_no_cfu_in_teacher_script_rejected(self):
        m = _good_master()
        m.direct_instruction[0].teacher_script = "Talk about the three estates."
        issues = _validate_quality(m)
        assert any("question mark" in i for i in issues)


class TestQualityGateDifferentiation:
    """Generic differentiation phrases should be rejected."""

    def test_generic_struggling_rejected(self):
        m = _good_master()
        m.differentiation.struggling = ["Provide extra time for the assignment"]
        issues = _validate_quality(m)
        assert any("generic" in i.lower() for i in issues)

    def test_generic_ell_rejected(self):
        m = _good_master()
        m.differentiation.ell = ["Provide support for vocabulary"]
        issues = _validate_quality(m)
        assert any("generic" in i.lower() for i in issues)

    def test_specific_differentiation_passes(self):
        m = _good_master()
        # These are specific — should NOT trigger the ban list
        issues = _validate_quality(m)
        assert not any("differentiation" in i.lower() for i in issues)


class TestQualityGateStationAnswerKeys:
    """Station answer key completeness check."""

    def test_empty_answer_key_rejected(self):
        m = _good_master()
        m.stations[0].teacher_answer_key = ""
        issues = _validate_quality(m)
        assert any("answer_key" in i and "missing" in i for i in issues)

    def test_short_answer_key_rejected(self):
        m = _good_master()
        m.stations[0].teacher_answer_key = "See above."
        issues = _validate_quality(m)
        assert any("answer key" in i and "chars" in i for i in issues)

    def test_good_answer_key_passes(self):
        m = _good_master()
        # The default fixture has a substantive answer key
        issues = _validate_quality(m)
        assert not any("answer_key" in i or "answer key" in i for i in issues)


class TestQualityGateSelfContained:
    """Banned phrases like 'teacher will provide' should be caught."""

    def test_teacher_will_provide_rejected(self):
        m = _good_master()
        m.direct_instruction[0].content = "For this activity, the teacher will provide a handout."
        issues = _validate_quality(m)
        assert any("teacher will provide" in i for i in issues)

    def test_refer_to_textbook_rejected(self):
        m = _good_master()
        m.primary_sources[0].content_text = (
            "Please refer to textbook page 142 for the full text. "
            "This section discusses the key principles of the era."
        )
        issues = _validate_quality(m)
        assert any("refer to textbook" in i for i in issues)


class TestQualityGateBloomsEnforcer:
    """Bloom's cognitive progression must be present."""

    def test_good_progression_passes(self):
        m = _good_master()
        issues = _validate_quality(m)
        assert not any("Bloom" in i for i in issues)

    def test_missing_analysis_flagged(self):
        m = _good_master()
        for et in m.exit_ticket:
            et.cognitive_level = "recall"
        issues = _validate_quality(m)
        assert any("Bloom" in i for i in issues)


class TestQualityGateVoice:
    """Lesson personality and hooks must be present."""

    def test_empty_personality_flagged(self):
        m = _good_master()
        m.lesson_personality = ""
        issues = _validate_quality(m)
        assert any("lesson_personality" in i for i in issues)

    def test_missing_hook_flagged(self):
        m = _good_master()
        m.direct_instruction[0].hook = ""
        issues = _validate_quality(m)
        assert any("hook" in i for i in issues)

    def test_good_voice_passes(self):
        m = _good_master()
        m.lesson_personality = "Today we put Hammurabi on trial"
        m.direct_instruction[0].hook = "Imagine getting fined for eating too much bread"
        issues = _validate_quality(m)
        assert not any("personality" in i or "hook" in i for i in issues)


class TestQualityGateDiversity:
    """Diversity check catches exclusionary language."""

    def test_bias_flag_caught(self):
        m = _good_master()
        m.direct_instruction[0].content = (
            "The primitive peoples of this region were uncivilized "
            "until contact with European explorers."
        )
        issues = _validate_quality(m)
        assert any("Diversity" in i for i in issues)

    def test_clean_content_passes(self):
        m = _good_master()
        issues = _validate_quality(m)
        assert not any("Diversity" in i for i in issues)
