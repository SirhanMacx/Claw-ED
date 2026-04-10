"""Tests for the Teaching Memory Engine -- feedback loop and pattern learning."""

from __future__ import annotations

import pytest

from clawed.memory_engine import (
    DEFAULT_MEMORY_TEMPLATE,
    SECTION_GENERATION_STATS,
    SECTION_STRUCTURAL_PREFS,
    SECTION_WHAT_TO_AVOID,
    SECTION_WHAT_WORKS,
    _append_to_section,
    _compute_stats,
    _extract_section_entries,
    _is_duplicate_entry,
    _is_only_template,
    build_improvement_context,
    extract_lesson_patterns,
    get_improvement_stats,
    process_feedback,
    reset_memory,
)
from clawed.models import DailyLesson, DifferentiationNotes, ExitTicketQuestion

# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def sample_lesson():
    """A realistic DailyLesson for testing."""
    return DailyLesson(
        title="The Causes of World War I",
        lesson_number=3,
        objective="Students will be able to identify and explain the four main causes of WWI.",
        standards=["NYS-SS.9-12.2"],
        do_now=(
            "Look at the political cartoon on the board. "
            "What do you think the artist is trying to say about European alliances? "
            "Write a prediction about today's topic."
        ),
        direct_instruction="Teacher walks through MAIN causes with primary source excerpts.",
        guided_practice="Students analyze a set of primary source documents in groups.",
        independent_work="Write a paragraph explaining which cause was most significant.",
        exit_ticket=[
            ExitTicketQuestion(
                question="Name the four MAIN causes.",
                expected_response="Militarism, Alliances, Imperialism, Nationalism",
            ),
            ExitTicketQuestion(
                question="Which alliance system involved Germany?",
                expected_response="Triple Alliance",
            ),
            ExitTicketQuestion(
                question="How did imperialism contribute to tensions?",
                expected_response="Competition for colonies",
            ),
        ],
        homework="Read pages 245-250 and answer questions 1-3.",
        differentiation=DifferentiationNotes(
            struggling=["Provide a graphic organizer", "Pair with strong reader"],
            advanced=["Compare to modern geopolitical tensions"],
            ell=["Vocabulary list with translations"],
        ),
        materials_needed=["Political cartoon handout", "Primary source packet"],
    )


@pytest.fixture
def poor_lesson():
    """A lesson that received a low rating."""
    return DailyLesson(
        title="Vocabulary Review Day",
        lesson_number=7,
        objective="Students will review vocabulary.",
        do_now="Define these words.",
        direct_instruction="Go over definitions.",
        guided_practice="Discuss with your neighbor.",
        independent_work="Complete the worksheet.",
        exit_ticket=[
            ExitTicketQuestion(question="Did you learn the words?", expected_response="Yes"),
        ],
    )


@pytest.fixture
def tmp_memory(tmp_path, monkeypatch):
    """Redirect memory.md to a temp directory."""
    ws = tmp_path / "workspace"
    ws.mkdir(parents=True)
    monkeypatch.setattr("clawed.workspace.MEMORY_PATH", ws / "memory.md")
    # Write default template
    (ws / "memory.md").write_text(DEFAULT_MEMORY_TEMPLATE, encoding="utf-8")
    return ws / "memory.md"


# ── Pattern extraction ───────────────────────────────────────────────


class TestExtractLessonPatterns:
    def test_five_star_extracts_positive_patterns(self, sample_lesson):
        patterns = extract_lesson_patterns(sample_lesson, rating=5)
        assert len(patterns) > 0
        types = [p["type"] for p in patterns]
        assert "positive" in types
        # Should capture the lesson title
        titles = [p["pattern"] for p in patterns]
        assert any("Causes of World War I" in t for t in titles)

    def test_five_star_with_notes(self, sample_lesson):
        patterns = extract_lesson_patterns(sample_lesson, rating=5, notes="Loved the primary sources!")
        note_patterns = [p for p in patterns if "primary sources" in p["pattern"].lower()]
        assert len(note_patterns) > 0

    def test_five_star_extracts_do_now_pattern(self, sample_lesson):
        patterns = extract_lesson_patterns(sample_lesson, rating=5)
        # Should detect prediction question in Do-Now
        structural = [p for p in patterns if p["section"] == SECTION_STRUCTURAL_PREFS]
        assert len(structural) > 0

    def test_five_star_exit_ticket_pattern(self, sample_lesson):
        patterns = extract_lesson_patterns(sample_lesson, rating=5)
        et_patterns = [p for p in patterns if "exit ticket" in p["pattern"].lower()]
        assert len(et_patterns) > 0

    def test_low_rating_extracts_negative_patterns(self, poor_lesson):
        patterns = extract_lesson_patterns(poor_lesson, rating=1, notes="Too generic, no real content")
        assert len(patterns) > 0
        types = [p["type"] for p in patterns]
        assert "negative" in types
        # Should capture the teacher's complaint
        notes_patterns = [p for p in patterns if "generic" in p["pattern"].lower()]
        assert len(notes_patterns) > 0

    def test_low_rating_with_edited_sections(self, poor_lesson):
        patterns = extract_lesson_patterns(
            poor_lesson,
            rating=2,
            edited_sections=["guided_practice", "exit_ticket"],
        )
        structural = [p for p in patterns if p["section"] == SECTION_STRUCTURAL_PREFS]
        assert len(structural) >= 2  # One per edited section

    def test_rating_3_no_patterns(self, sample_lesson):
        """Rating 3 is neutral -- should not extract any patterns."""
        patterns = extract_lesson_patterns(sample_lesson, rating=3)
        assert patterns == []

    def test_rating_4_with_notes(self, sample_lesson):
        patterns = extract_lesson_patterns(sample_lesson, rating=4, notes="Good but needs more scaffolding")
        assert len(patterns) > 0
        assert any("scaffolding" in p["pattern"].lower() for p in patterns)

    def test_rating_4_with_edits(self, sample_lesson):
        patterns = extract_lesson_patterns(
            sample_lesson,
            rating=4,
            edited_sections=["do_now"],
        )
        structural = [p for p in patterns if p["section"] == SECTION_STRUCTURAL_PREFS]
        assert len(structural) >= 1


# ── Memory.md section operations ─────────────────────────────────────


class TestAppendToSection:
    def test_append_to_existing_section_with_placeholder(self):
        content = (
            "# Teaching Memory\n\n"
            f"## {SECTION_WHAT_WORKS}\n"
            "*(Patterns from your highest-rated lessons appear here automatically.)*\n\n"
            f"## {SECTION_WHAT_TO_AVOID}\n"
            "*(Patterns from your lowest-rated lessons appear here automatically.)*\n"
        )
        result = _append_to_section(content, SECTION_WHAT_WORKS, "Great lesson on photosynthesis")
        assert "- Great lesson on photosynthesis" in result
        # Placeholder should be replaced
        assert "*(Patterns from your highest-rated" not in result

    def test_append_to_existing_section_with_entries(self):
        content = (
            "# Teaching Memory\n\n"
            f"## {SECTION_WHAT_WORKS}\n"
            "- Existing pattern one\n\n"
            f"## {SECTION_WHAT_TO_AVOID}\n"
            "*(Patterns from your lowest-rated lessons appear here automatically.)*\n"
        )
        result = _append_to_section(content, SECTION_WHAT_WORKS, "New pattern two")
        assert "- Existing pattern one" in result
        assert "- New pattern two" in result

    def test_append_to_nonexistent_section(self):
        content = "# Teaching Memory\n\n## Existing Section\n- stuff\n"
        result = _append_to_section(content, "Brand New Section", "First entry")
        assert "## Brand New Section" in result
        assert "- First entry" in result

    def test_append_before_stats_section(self):
        content = f"# Teaching Memory\n\n## {SECTION_GENERATION_STATS}\n- Total lessons rated: 0\n"
        result = _append_to_section(content, "New Section", "An entry")
        # New section should appear before stats
        stats_pos = result.index(SECTION_GENERATION_STATS)
        new_pos = result.index("New Section")
        assert new_pos < stats_pos


class TestExtractSectionEntries:
    def test_extracts_bullet_entries(self):
        content = (
            f"## {SECTION_WHAT_WORKS}\n"
            "- Pattern one\n"
            "- Pattern two\n"
            "- Pattern three\n\n"
            f"## {SECTION_WHAT_TO_AVOID}\n"
            "- Bad thing\n"
        )
        entries = _extract_section_entries(content, SECTION_WHAT_WORKS)
        assert entries == ["Pattern one", "Pattern two", "Pattern three"]

    def test_skips_placeholders(self):
        content = f"## {SECTION_WHAT_WORKS}\n*(Patterns from your highest-rated lessons appear here automatically.)*\n"
        entries = _extract_section_entries(content, SECTION_WHAT_WORKS)
        assert entries == []

    def test_empty_for_missing_section(self):
        content = "## Some Other Section\n- stuff\n"
        entries = _extract_section_entries(content, SECTION_WHAT_WORKS)
        assert entries == []


class TestIsDuplicateEntry:
    def test_exact_duplicate(self):
        content = "- Lesson 'Photosynthesis' rated 5-star\n"
        assert _is_duplicate_entry(content, "Lesson 'Photosynthesis' rated 5-star") is True

    def test_title_duplicate(self):
        content = "- Lesson 'WWI Causes' rated 5-star (2026-03-20)\n"
        assert _is_duplicate_entry(content, "Lesson 'WWI Causes' rated 5-star (2026-03-24)") is True

    def test_no_duplicate(self):
        content = "- Lesson 'Photosynthesis' rated 5-star\n"
        assert _is_duplicate_entry(content, "Lesson 'Mitosis' rated 5-star") is False


class TestIsOnlyTemplate:
    def test_default_template_is_template(self):
        assert _is_only_template(DEFAULT_MEMORY_TEMPLATE) is True

    def test_template_with_entries_is_not(self):
        content = DEFAULT_MEMORY_TEMPLATE.replace(
            "*(Patterns from your highest-rated lessons appear here automatically.)*",
            "- Good lesson on fractions",
        )
        assert _is_only_template(content) is False


class TestComputeStats:
    def test_empty_memory(self):
        stats = _compute_stats(DEFAULT_MEMORY_TEMPLATE)
        assert stats["total_rated"] == 0
        assert stats["avg_rating"] == 0.0
        assert stats["trend"] == "--"

    def test_with_five_star_entries(self):
        content = "- Lesson 'A' rated 5-star\n- Lesson 'B' rated 5-star\n- Lesson 'C' rated 1-star\n"
        stats = _compute_stats(content)
        assert stats["total_rated"] == 3
        assert stats["trend"] == "improving"

    def test_declining_trend(self):
        content = "- Lesson 'A' rated 1-star\n- Lesson 'B' rated 2-star\n- Lesson 'C' rated 1-star\n"
        stats = _compute_stats(content)
        assert stats["trend"] == "needs attention"


# ── process_feedback (core API) ──────────────────────────────────────


class TestProcessFeedback:
    def test_five_star_adds_to_what_works(self, sample_lesson, tmp_memory):
        patterns = process_feedback(sample_lesson, rating=5)
        assert len(patterns) > 0
        content = tmp_memory.read_text()
        assert "Causes of World War I" in content
        assert SECTION_WHAT_WORKS in content

    def test_one_star_adds_to_what_to_avoid(self, poor_lesson, tmp_memory):
        patterns = process_feedback(poor_lesson, rating=1, notes="Terrible, no real content")
        assert len(patterns) > 0
        content = tmp_memory.read_text()
        assert "Vocabulary Review Day" in content
        assert "Terrible" in content

    def test_three_star_no_change(self, sample_lesson, tmp_memory):
        original = tmp_memory.read_text()
        patterns = process_feedback(sample_lesson, rating=3)
        assert patterns == []
        assert tmp_memory.read_text() == original

    def test_five_star_updates_stats(self, sample_lesson, tmp_memory):
        process_feedback(sample_lesson, rating=5)
        content = tmp_memory.read_text()
        assert "Total lessons rated: 1" in content

    def test_duplicate_not_added_twice(self, sample_lesson, tmp_memory):
        process_feedback(sample_lesson, rating=5)
        content_after_first = tmp_memory.read_text()
        process_feedback(sample_lesson, rating=5)
        content_after_second = tmp_memory.read_text()
        # The lesson title should appear only once in the patterns
        assert content_after_first.count("Causes of World War I") == content_after_second.count("Causes of World War I")

    def test_two_star_with_edited_sections(self, poor_lesson, tmp_memory):
        process_feedback(
            poor_lesson,
            rating=2,
            edited_sections=["guided_practice", "exit_ticket"],
        )
        content = tmp_memory.read_text()
        assert "guided_practice" in content
        assert "exit_ticket" in content

    def test_four_star_with_notes(self, sample_lesson, tmp_memory):
        patterns = process_feedback(
            sample_lesson,
            rating=4,
            notes="Good but needs more scaffolding for struggling readers",
        )
        assert len(patterns) > 0
        content = tmp_memory.read_text()
        assert "scaffolding" in content

    def test_rating_clamped(self, sample_lesson, tmp_memory):
        """Ratings outside 1-5 should be clamped."""
        patterns = process_feedback(sample_lesson, rating=10)
        # Clamped to 5, should produce positive patterns
        assert len(patterns) > 0
        assert any(p["type"] == "positive" for p in patterns)


# ── build_improvement_context ────────────────────────────────────────


class TestBuildImprovementContext:
    def test_empty_memory_returns_empty(self, tmp_memory):
        result = build_improvement_context()
        assert result == ""

    def test_with_patterns_returns_context(self, sample_lesson, tmp_memory):
        process_feedback(sample_lesson, rating=5)
        result = build_improvement_context()
        assert "Learning from Past Lessons" in result
        assert "What works well" in result

    def test_includes_what_to_avoid(self, poor_lesson, tmp_memory):
        process_feedback(poor_lesson, rating=1, notes="No real content")
        result = build_improvement_context()
        assert "What to avoid" in result

    def test_includes_structural_prefs(self, sample_lesson, tmp_memory):
        process_feedback(sample_lesson, rating=5)
        result = build_improvement_context()
        # Should include structural preferences (e.g., exit ticket pattern)
        assert "Structural preferences" in result or "What works well" in result

    def test_subject_filtering(self, sample_lesson, tmp_memory):
        process_feedback(
            sample_lesson,
            rating=4,
            notes="Great for social studies specifically",
        )
        result = build_improvement_context(subject="Social Studies")
        # Should return context even with subject filter
        assert isinstance(result, str)


# ── get_improvement_stats ────────────────────────────────────────────


class TestGetImprovementStats:
    def test_empty_stats(self, tmp_memory):
        stats = get_improvement_stats()
        assert stats["total_rated"] == 0
        assert stats["total_patterns"] == 0
        assert stats["avg_rating"] == 0.0

    def test_stats_after_feedback(self, sample_lesson, poor_lesson, tmp_memory):
        process_feedback(sample_lesson, rating=5)
        process_feedback(poor_lesson, rating=1, notes="Bad")
        stats = get_improvement_stats()
        assert stats["total_rated"] == 2
        assert stats["what_works_count"] > 0
        assert stats["what_to_avoid_count"] > 0
        assert stats["total_patterns"] > 0

    def test_stats_include_recent_patterns(self, sample_lesson, tmp_memory):
        process_feedback(sample_lesson, rating=5)
        stats = get_improvement_stats()
        assert len(stats["what_works"]) > 0


# ── Rating math correctness ──────────────────────────────────────────


class TestRatingMath:
    """Rating averages must use actual star values, not collapsed weights."""

    def test_single_two_star_averages_to_two(self, poor_lesson, tmp_memory):
        process_feedback(poor_lesson, rating=2)
        stats = get_improvement_stats()
        assert stats["avg_rating"] == 2.0, f"A single 2-star lesson should average 2.0, got {stats['avg_rating']}"

    def test_single_one_star_averages_to_one(self, poor_lesson, tmp_memory):
        process_feedback(poor_lesson, rating=1, notes="Awful")
        stats = get_improvement_stats()
        assert stats["avg_rating"] == 1.0, f"A single 1-star lesson should average 1.0, got {stats['avg_rating']}"

    def test_five_and_two_averages_to_three_point_five(
        self,
        sample_lesson,
        poor_lesson,
        tmp_memory,
    ):
        process_feedback(sample_lesson, rating=5)
        process_feedback(poor_lesson, rating=2)
        stats = get_improvement_stats()
        assert stats["avg_rating"] == 3.5, f"5★ + 2★ should average 3.5, got {stats['avg_rating']}"

    def test_five_and_one_averages_to_three(
        self,
        sample_lesson,
        poor_lesson,
        tmp_memory,
    ):
        process_feedback(sample_lesson, rating=5)
        process_feedback(poor_lesson, rating=1, notes="Bad")
        stats = get_improvement_stats()
        assert stats["avg_rating"] == 3.0, f"5★ + 1★ should average 3.0, got {stats['avg_rating']}"


# ── Cross-subject contamination ─────────────────────────────────────


class TestCrossSubjectFiltering:
    """Improvement context must not leak patterns across subjects."""

    def test_science_patterns_excluded_from_history(self, tmp_memory):
        science_lesson = DailyLesson(
            title="Photosynthesis Lab",
            lesson_number=1,
            objective="Understand photosynthesis",
        )
        history_lesson = DailyLesson(
            title="Causes of the Civil War",
            lesson_number=2,
            objective="Analyze Civil War causes",
        )
        process_feedback(science_lesson, rating=5, notes="Great lab structure", subject="Science")
        process_feedback(history_lesson, rating=1, notes="Too much lecture", subject="History")

        # Verify tags are in memory
        content = tmp_memory.read_text()
        assert "[Science]" in content, "Science patterns must be tagged"
        assert "[History]" in content, "History patterns must be tagged"

        # Science context must NOT contain history feedback
        science_ctx = build_improvement_context(subject="Science")
        assert "Photosynthesis" in science_ctx, "Science lesson should appear in Science context"
        assert "Civil War" not in science_ctx, "History lesson must NOT appear in Science context"
        assert "lecture" not in science_ctx, "History complaint must NOT appear in Science context"

        # History context must NOT contain science praise
        history_ctx = build_improvement_context(subject="History")
        assert "Civil War" in history_ctx, "History lesson should appear in History context"
        assert "Photosynthesis" not in history_ctx, "Science lesson must NOT appear in History context"
        assert "Great lab" not in history_ctx, "Science note must NOT appear in History context"

    def test_teacher_notes_are_subject_tagged(self, tmp_memory):
        """Teacher notes on rated lessons MUST carry the subject tag."""
        lesson = DailyLesson(title="Lab Safety", lesson_number=1, objective="x")
        process_feedback(lesson, rating=5, notes="Excellent hands-on activity", subject="Science")
        content = tmp_memory.read_text()
        # The note entry itself must have [Science] tag
        assert "[Science]: Excellent hands-on" in content or "[Science]" in content.split("Excellent")[0]

    def test_untagged_patterns_included_everywhere(self, sample_lesson, tmp_memory):
        # Structural preferences have no subject tag — should appear for all subjects
        process_feedback(sample_lesson, rating=5)
        ctx_science = build_improvement_context(subject="Science")
        ctx_history = build_improvement_context(subject="History")
        # Both should get structural preferences if any exist
        # (structural prefs are universal)
        assert isinstance(ctx_science, str)
        assert isinstance(ctx_history, str)


# ── reset_memory ─────────────────────────────────────────────────────


class TestResetMemory:
    def test_reset_without_confirm(self, sample_lesson, tmp_memory):
        process_feedback(sample_lesson, rating=5)
        result = reset_memory(confirm=False)
        assert result is False
        # Memory should still have patterns
        assert "Causes of World War I" in tmp_memory.read_text()

    def test_reset_with_confirm(self, sample_lesson, tmp_memory):
        process_feedback(sample_lesson, rating=5)
        result = reset_memory(confirm=True)
        assert result is True
        content = tmp_memory.read_text()
        assert "Causes of World War I" not in content
        assert "*(Patterns from your highest-rated" in content


# ── Integration: improvement context injected into prompts ───────────


class TestImprovementContextInjection:
    """Test that build_improvement_context output is suitable for prompt injection."""

    def test_context_has_delimiters(self, sample_lesson, tmp_memory):
        process_feedback(sample_lesson, rating=5)
        ctx = build_improvement_context()
        assert "=== Learning from Past Lessons ===" in ctx
        assert "=== End Learning Context ===" in ctx

    def test_context_is_reasonable_length(self, sample_lesson, poor_lesson, tmp_memory):
        # Add several patterns
        for i in range(5):
            lesson = DailyLesson(
                title=f"Lesson {i}",
                lesson_number=i,
                objective=f"Objective {i}",
                do_now="What do you think will happen? How does this connect to yesterday?",
                exit_ticket=[
                    ExitTicketQuestion(question="Q1?", expected_response="A1"),
                    ExitTicketQuestion(question="Q2?", expected_response="A2"),
                    ExitTicketQuestion(question="Q3?", expected_response="A3"),
                ],
            )
            process_feedback(lesson, rating=5, notes=f"Note for lesson {i}")

        process_feedback(poor_lesson, rating=1, notes="Awful lesson")

        ctx = build_improvement_context()
        # Should be non-empty but not enormous (under 3000 chars)
        assert len(ctx) > 50
        assert len(ctx) < 3000

    def test_graceful_with_deleted_memory(self, tmp_memory):
        """If memory.md is deleted, context should be empty (not crash)."""
        tmp_memory.unlink()
        ctx = build_improvement_context()
        # Should return empty or the default template with no patterns
        assert ctx == "" or "Learning from Past Lessons" not in ctx
