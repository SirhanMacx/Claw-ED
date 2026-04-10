"""Tests for clawed.voice_check — post-generation voice-match validation."""

from __future__ import annotations

from clawed.models import TeacherPersona
from clawed.voice_check import (
    _detect_do_now_type,
    _extract_address_terms,
    check_voice_match,
)

# ── Helper: build a persona with voice data ──────────────────────────────


def _persona(
    voice_sample: str = "",
    do_now_style: str = "",
    signature_moves: list[str] | None = None,
) -> TeacherPersona:
    return TeacherPersona(
        voice_sample=voice_sample,
        do_now_style=do_now_style,
        signature_moves=signature_moves or [],
    )


# ── Address term tests ───────────────────────────────────────────────────


class TestAddressTermPresent:
    """Persona says 'friends', output uses 'friends' -> ok."""

    def test_address_term_present(self):
        persona = _persona(voice_sample="Good morning, friends! Today we will...")
        result = check_voice_match(
            persona,
            do_now="Friends, take out your notebooks and answer the following.",
        )
        assert result.address_term_ok is True
        assert result.passed is True


class TestAddressTermMissing:
    """Persona says 'friends', output uses 'scholars' -> fail with specific issue."""

    def test_address_term_missing(self):
        persona = _persona(voice_sample="Good morning, friends! Today we will...")
        result = check_voice_match(
            persona,
            do_now="Scholars, take out your notebooks.",
            direct_instruction_opening="Scholars, let us begin.",
        )
        assert result.address_term_ok is False
        assert result.passed is False
        assert len(result.issues) >= 1
        # The issue message should mention both the expected and found terms.
        issue = result.issues[0]
        assert "friends" in issue.lower()
        assert "scholars" in issue.lower()


# ── Do Now style tests ───────────────────────────────────────────────────


class TestDoNowStyleMismatch:
    """Persona says 'scenario/analogy', Do Now is a recall question -> fail."""

    def test_do_now_style_mismatch(self):
        persona = _persona(
            voice_sample="Hey friends",
            do_now_style="analogy or scenario that previews the lesson concept",
        )
        result = check_voice_match(
            persona,
            do_now="What do you remember about the causes of the Civil War? List three facts.",
        )
        assert result.do_now_style_ok is False
        assert result.passed is False
        assert any("mismatch" in i.lower() for i in result.issues)


class TestDoNowStyleMatch:
    """Persona says 'scenario/analogy', Do Now uses 'imagine' -> ok."""

    def test_do_now_style_match(self):
        persona = _persona(
            voice_sample="Hey friends",
            do_now_style="scenario-based warm-ups",
        )
        result = check_voice_match(
            persona,
            do_now="Friends, imagine you just woke up in 1776 Philadelphia. What do you see?",
        )
        assert result.do_now_style_ok is True
        assert result.passed is True


# ── Overall pass ─────────────────────────────────────────────────────────


class TestOverallPass:
    """Everything matches -> passed=True, issues=[]."""

    def test_overall_pass(self):
        persona = _persona(
            voice_sample="Good morning, friends! Today we explore...",
            do_now_style="scenario that previews the concept",
            signature_moves=["Calls students 'friends'"],
        )
        result = check_voice_match(
            persona,
            do_now="Imagine you are a delegate arriving at the Constitutional Convention.",
            direct_instruction_opening="Friends, today we are going to explore...",
        )
        assert result.passed is True
        assert result.issues == []
        assert result.address_term_ok is True
        assert result.do_now_style_ok is True
        assert result.structure_ok is True


# ── No voice data — skip gracefully ──────────────────────────────────────


class TestNoVoiceSampleSkipsGracefully:
    """Empty persona -> passed=True (nothing to check)."""

    def test_no_voice_sample_skips_gracefully(self):
        persona = _persona()  # all defaults — empty strings / empty lists
        result = check_voice_match(persona)
        assert result.passed is True
        assert result.issues == []


# ── Unit tests for internal helpers ──────────────────────────────────────


class TestDetectDoNowType:
    def test_scenario(self):
        assert _detect_do_now_type("Imagine you are a Roman senator") == "scenario"

    def test_recall(self):
        assert _detect_do_now_type("What do you remember about gravity?") == "recall"

    def test_opinion(self):
        assert _detect_do_now_type("Do you think the decision was fair?") == "opinion"

    def test_other(self):
        assert _detect_do_now_type("Open your textbook to page 42.") == "other"

    def test_empty(self):
        assert _detect_do_now_type("") == "other"


class TestExtractAddressTerms:
    def test_single_term(self):
        assert _extract_address_terms("Good morning, friends!") == {"friends"}

    def test_multiple_terms(self):
        terms = _extract_address_terms("Hello scholars and friends, welcome.")
        assert terms == {"scholars", "friends"}

    def test_case_insensitive(self):
        assert _extract_address_terms("FRIENDS, let us begin") == {"friends"}

    def test_no_terms(self):
        assert _extract_address_terms("Open your books.") == set()

    def test_empty_string(self):
        assert _extract_address_terms("") == set()
