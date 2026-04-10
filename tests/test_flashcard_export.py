"""Tests for spaced repetition and quiz export (Anki TSV, Kahoot CSV, study guide)."""

from __future__ import annotations

from pathlib import Path

from clawed.compile_flashcards import (
    compile_anki_tsv,
    compile_kahoot_csv,
    compile_study_guide,
)
from clawed.master_content import (
    DoNow,
    GuidedNote,
    InstructionSection,
    MasterContent,
    PrimarySource,
    StimulusQuestion,
    VocabularyEntry,
)
from clawed.models import DifferentiationNotes


def _test_master() -> MasterContent:
    """Minimal MasterContent for export testing."""
    return MasterContent(
        title="Test Lesson",
        subject="History",
        grade_level="8",
        topic="Test Topic",
        standards=["NYS 8.1"],
        objective="SWBAT test things.",
        vocabulary=[
            VocabularyEntry(
                term="Democracy",
                definition="Government by the people.",
                context_sentence="Athens practiced democracy.",
            ),
            VocabularyEntry(
                term="Republic",
                definition="Government through elected representatives.",
                context_sentence="Rome was a republic.",
            ),
            VocabularyEntry(
                term="Oligarchy",
                definition="Government by a small group of powerful people.",
                context_sentence="Sparta was an oligarchy.",
            ),
        ],
        primary_sources=[
            PrimarySource(
                id="source_a",
                title="Test Source",
                source_type="text_excerpt",
                content_text="A" * 120,
                attribution="Test Author, 2026",
                image_spec="test source image spec query",
            ),
        ],
        do_now=DoNow(
            stimulus="Read the following passage.",
            stimulus_type="text_excerpt",
            questions=["What do you notice?"],
            answers=["Students should notice..."],
        ),
        direct_instruction=[
            InstructionSection(
                heading="Introduction",
                content="Content here.",
                teacher_script="Ask: What do you think? Wait 10 seconds.",
                key_points=["Point A", "Point B"],
                image_spec="test image spec for intro",
            ),
        ],
        guided_notes=[
            GuidedNote(prompt="The ________ was important.", answer="concept", section_ref="Introduction"),
            GuidedNote(prompt="A key idea is ________.", answer="equality", section_ref="Introduction"),
            GuidedNote(prompt="The leader was ________.", answer="Pericles", section_ref="Introduction"),
            GuidedNote(prompt="Democracy means ________.", answer="people rule", section_ref="Introduction"),
            GuidedNote(prompt="Athens was a ________.", answer="city-state", section_ref="Introduction"),
        ],
        stations=[],
        exit_ticket=[
            StimulusQuestion(
                stimulus="Read this excerpt about Athens...",
                stimulus_type="text_excerpt",
                question="What type of government did Athens have?",
                answer="Athens had a direct democracy.",
                cognitive_level="recall",
            ),
            StimulusQuestion(
                stimulus="Compare Athens and Sparta...",
                stimulus_type="text_excerpt",
                question="How did their governments differ?",
                answer="Athens was democratic, Sparta was oligarchic.",
                cognitive_level="application",
            ),
            StimulusQuestion(
                stimulus="Consider modern democracies...",
                stimulus_type="scenario",
                question="To what extent do modern democracies resemble Athens?",
                answer="Modern democracies are representative, not direct.",
                cognitive_level="analysis",
            ),
        ],
        differentiation=DifferentiationNotes(
            struggling=["Provide word bank with key terms"],
            advanced=["Research a third form of government"],
            ell=["Sentence frame: 'The government of ___ was ___'"],
        ),
    )


class TestAnkiExport:
    def test_generates_tsv(self, tmp_path: Path):
        m = _test_master()
        path = compile_anki_tsv(m, tmp_path)
        assert path.exists()
        assert path.suffix == ".tsv"

    def test_contains_vocabulary(self, tmp_path: Path):
        m = _test_master()
        path = compile_anki_tsv(m, tmp_path)
        content = path.read_text(encoding="utf-8")
        assert "Democracy" in content
        assert "Republic" in content
        assert "Oligarchy" in content

    def test_contains_guided_notes(self, tmp_path: Path):
        m = _test_master()
        path = compile_anki_tsv(m, tmp_path)
        content = path.read_text(encoding="utf-8")
        assert "concept" in content
        assert "equality" in content

    def test_card_count(self, tmp_path: Path):
        m = _test_master()
        path = compile_anki_tsv(m, tmp_path)
        content = path.read_text(encoding="utf-8").strip()
        # Count tab-separated records (each card has exactly 2 tabs)
        card_count = content.count("\t") // 2
        # 3 vocab + 5 guided notes + 2 key points = 10
        assert card_count == 10


class TestKahootExport:
    def test_generates_csv(self, tmp_path: Path):
        m = _test_master()
        path = compile_kahoot_csv(m, tmp_path)
        assert path.exists()
        assert path.suffix == ".csv"

    def test_has_header(self, tmp_path: Path):
        m = _test_master()
        path = compile_kahoot_csv(m, tmp_path)
        content = path.read_text(encoding="utf-8")
        assert "Question" in content
        assert "Answer 1" in content

    def test_vocab_questions(self, tmp_path: Path):
        m = _test_master()
        path = compile_kahoot_csv(m, tmp_path)
        content = path.read_text(encoding="utf-8")
        assert "Democracy" in content
        assert "Republic" in content

    def test_exit_ticket_questions(self, tmp_path: Path):
        m = _test_master()
        path = compile_kahoot_csv(m, tmp_path)
        content = path.read_text(encoding="utf-8")
        assert "Athens" in content


class TestStudyGuide:
    def test_generates_txt(self, tmp_path: Path):
        m = _test_master()
        path = compile_study_guide(m, tmp_path)
        assert path.exists()
        assert path.suffix == ".txt"

    def test_contains_all_sections(self, tmp_path: Path):
        m = _test_master()
        path = compile_study_guide(m, tmp_path)
        content = path.read_text(encoding="utf-8")
        assert "VOCABULARY" in content
        assert "KEY POINTS" in content
        assert "GUIDED NOTES" in content
        assert "REVIEW QUESTIONS" in content

    def test_vocabulary_present(self, tmp_path: Path):
        m = _test_master()
        path = compile_study_guide(m, tmp_path)
        content = path.read_text(encoding="utf-8")
        assert "Democracy" in content
        assert "Government by the people" in content
