"""Tests for the Pedagogical Fingerprint Evolution module."""

from __future__ import annotations

import pytest

from clawed.models import TeacherPersona, TeachingStyle
from clawed.persona_evolution import (
    _analyze_rating_patterns,
    _build_candidate_changes,
    _compare_personas,
    apply_confirmed_changes,
    get_confirmed_changes,
    record_ingestion_changes,
)

# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def base_persona() -> TeacherPersona:
    return TeacherPersona(
        name="Test Teacher",
        teaching_style=TeachingStyle.DIRECT_INSTRUCTION,
        do_now_style="content recall question",
        exit_ticket_style="3 short-answer questions",
        source_types=["textbook excerpts"],
        activity_patterns=["lecture then worksheet"],
        scaffolding_moves=["sentence starters"],
        signature_moves=["always reads aloud"],
        handout_style="dense text packets",
    )


@pytest.fixture
def evolved_persona() -> TeacherPersona:
    return TeacherPersona(
        name="Test Teacher",
        teaching_style=TeachingStyle.INQUIRY_BASED,
        do_now_style="analogy scenario previewing the lesson concept",
        exit_ticket_style="3 short-answer questions",  # unchanged
        source_types=["primary source documents", "political speeches"],
        activity_patterns=["lecture then worksheet"],  # unchanged
        scaffolding_moves=["sentence starters"],  # unchanged
        signature_moves=["always reads aloud"],  # unchanged
        handout_style="graphic organizers with image hooks",
    )


# ── Tests ────────────────────────────────────────────────────────────


class TestComparePersonas:
    def test_compare_personas_detects_changes(self, base_persona: TeacherPersona, evolved_persona: TeacherPersona):
        changes = _compare_personas(base_persona, evolved_persona)
        changed_fields = {c["field"] for c in changes}

        # These fields differ between base and evolved
        assert "teaching_style" in changed_fields
        assert "do_now_style" in changed_fields
        assert "source_types" in changed_fields
        assert "handout_style" in changed_fields

        # These fields are the same
        assert "exit_ticket_style" not in changed_fields
        assert "activity_patterns" not in changed_fields
        assert "scaffolding_moves" not in changed_fields
        assert "signature_moves" not in changed_fields

    def test_compare_personas_no_changes(self, base_persona: TeacherPersona):
        changes = _compare_personas(base_persona, base_persona)
        assert changes == []


class TestAnalyzeRatingPatterns:
    def test_analyze_rating_patterns_needs_minimum_data(self):
        # 9 ratings — below the 10-rating minimum
        ratings = [(4, "good lesson")] * 9
        assert _analyze_rating_patterns(ratings) == []

    def test_analyze_rating_patterns_detects_trend(self):
        # 10 ratings: first half low, second half high
        ratings = [(2, "")] * 5 + [(5, "")] * 5
        signals = _analyze_rating_patterns(ratings)
        assert len(signals) >= 1
        assert any(s["type"] == "rating_trend" for s in signals)


class TestBuildCandidateChanges:
    def test_build_candidate_changes_from_ingestion(
        self, base_persona: TeacherPersona, evolved_persona: TeacherPersona
    ):
        candidates = _build_candidate_changes(base_persona, evolved_persona, source="ingestion")
        assert len(candidates) > 0
        for c in candidates:
            assert c["source"] == "ingestion"
            assert c["confirmations"] == 1
            assert "first_seen" in c
            assert "last_seen" in c
            assert "field" in c
            assert "new_value" in c


class TestRecordAndConfirmCycle:
    def test_record_and_confirm_cycle(self, base_persona: TeacherPersona, evolved_persona: TeacherPersona):
        # First ingestion — confirmations = 1
        record_ingestion_changes(base_persona, evolved_persona)
        confirmed = get_confirmed_changes()
        assert confirmed == [], "Should not confirm after only 1 signal"

        # Second ingestion with the same diff — confirmations = 2
        record_ingestion_changes(base_persona, evolved_persona)
        confirmed = get_confirmed_changes()
        assert len(confirmed) > 0, "Should confirm after 2 consistent signals"
        for c in confirmed:
            assert c["confirmations"] >= 2


class TestApplyConfirmedChanges:
    def test_apply_confirmed_changes_updates_persona(
        self, base_persona: TeacherPersona, evolved_persona: TeacherPersona
    ):
        # Build up 2 confirmations
        record_ingestion_changes(base_persona, evolved_persona)
        record_ingestion_changes(base_persona, evolved_persona)

        updated, descriptions = apply_confirmed_changes(base_persona)

        # teaching_style should have changed
        assert updated.teaching_style == TeachingStyle.INQUIRY_BASED
        assert updated.do_now_style == "analogy scenario previewing the lesson concept"
        assert updated.handout_style == "graphic organizers with image hooks"
        assert len(descriptions) > 0

        # After applying, no more confirmed candidates
        assert get_confirmed_changes() == []
