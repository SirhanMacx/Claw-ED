"""Tests for auto-chain features in generate_lesson_bundle.

Verifies that differentiation, games, standards, and quality gate
auto-chain correctly after lesson generation.
"""

from clawed.models import AppConfig


class TestAutoChainConfig:
    """Test that auto-chain config fields exist and default correctly."""

    def test_auto_differentiate_defaults_true(self):
        config = AppConfig()
        assert config.auto_differentiate is True

    def test_auto_game_defaults_true(self):
        config = AppConfig()
        assert config.auto_game is True

    def test_auto_standards_defaults_true(self):
        config = AppConfig()
        assert config.auto_standards is True

    def test_quality_threshold_defaults_3_5(self):
        config = AppConfig()
        assert config.quality_threshold == 3.5

    def test_can_disable_auto_differentiate(self):
        config = AppConfig(auto_differentiate=False)
        assert config.auto_differentiate is False

    def test_can_disable_auto_game(self):
        config = AppConfig(auto_game=False)
        assert config.auto_game is False

    def test_can_set_quality_threshold(self):
        config = AppConfig(quality_threshold=4.0)
        assert config.quality_threshold == 4.0


class TestLessonFormatField:
    """Test the lesson_format field on MasterContent."""

    def test_default_format(self):
        from clawed.master_content import (
            DifferentiationNotes,
            DoNow,
            GuidedNote,
            InstructionSection,
            MasterContent,
            StimulusQuestion,
        )

        master = MasterContent(
            title="Test",
            subject="History",
            grade_level="8",
            topic="Test",
            objective="Test objective",
            do_now=DoNow(stimulus="q", stimulus_type="question", questions=["a"], answers=["b"]),
            direct_instruction=[
                InstructionSection(heading="h", content="c", teacher_script="t"),
            ],
            guided_notes=[
                GuidedNote(prompt="p", answer="a", section_ref="s"),
            ],
            exit_ticket=[
                StimulusQuestion(stimulus="s", stimulus_type="text", question="q", answer="a"),
            ],
            differentiation=DifferentiationNotes(),
        )
        assert master.lesson_format == "document_analysis"

    def test_custom_format(self):
        from clawed.master_content import (
            DifferentiationNotes,
            DoNow,
            GuidedNote,
            InstructionSection,
            MasterContent,
            StimulusQuestion,
        )

        master = MasterContent(
            title="Test",
            subject="History",
            grade_level="8",
            topic="Test",
            objective="Test objective",
            lesson_format="station_rotation",
            do_now=DoNow(stimulus="q", stimulus_type="question", questions=["a"], answers=["b"]),
            direct_instruction=[
                InstructionSection(heading="h", content="c", teacher_script="t"),
            ],
            guided_notes=[
                GuidedNote(prompt="p", answer="a", section_ref="s"),
            ],
            exit_ticket=[
                StimulusQuestion(stimulus="s", stimulus_type="text", question="q", answer="a"),
            ],
            differentiation=DifferentiationNotes(),
        )
        assert master.lesson_format == "station_rotation"


class TestEnrichmentFields:
    """Test new enrichment fields on MasterContent."""

    def test_misconceptions_default_empty(self):
        from clawed.master_content import (
            DifferentiationNotes,
            DoNow,
            GuidedNote,
            InstructionSection,
            MasterContent,
            StimulusQuestion,
        )

        master = MasterContent(
            title="T",
            subject="S",
            grade_level="8",
            topic="T",
            objective="O",
            do_now=DoNow(stimulus="q", stimulus_type="q", questions=["a"], answers=["b"]),
            direct_instruction=[InstructionSection(heading="h", content="c", teacher_script="t")],
            guided_notes=[GuidedNote(prompt="p", answer="a", section_ref="s")],
            exit_ticket=[StimulusQuestion(stimulus="s", stimulus_type="t", question="q", answer="a")],
            differentiation=DifferentiationNotes(),
        )
        assert master.misconceptions == []
        assert master.formative_checks == []
        assert master.prerequisite_skills == []

    def test_misconceptions_can_be_set(self):
        from clawed.master_content import (
            DifferentiationNotes,
            DoNow,
            GuidedNote,
            InstructionSection,
            MasterContent,
            StimulusQuestion,
        )

        master = MasterContent(
            title="T",
            subject="S",
            grade_level="8",
            topic="T",
            objective="O",
            misconceptions=["Students think X but actually Y"],
            formative_checks=["Quick check: thumbs up if..."],
            prerequisite_skills=["Can read a timeline"],
            do_now=DoNow(stimulus="q", stimulus_type="q", questions=["a"], answers=["b"]),
            direct_instruction=[InstructionSection(heading="h", content="c", teacher_script="t")],
            guided_notes=[GuidedNote(prompt="p", answer="a", section_ref="s")],
            exit_ticket=[StimulusQuestion(stimulus="s", stimulus_type="t", question="q", answer="a")],
            differentiation=DifferentiationNotes(),
        )
        assert len(master.misconceptions) == 1
        assert len(master.formative_checks) == 1
        assert len(master.prerequisite_skills) == 1
