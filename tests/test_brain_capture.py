"""Tests for clawed.brain.capture — originals detection and persistence."""
from pathlib import Path

import pytest

from clawed.brain.capture import (
    capture_original,
    extract_slug_from_message,
    looks_like_original_thinking,
)
from clawed.brain.store import BrainStore


@pytest.fixture
def tmp_store(tmp_path: Path) -> BrainStore:
    return BrainStore(root=tmp_path / "brain")


# ── looks_like_original_thinking ─────────────────────────────────────────


def test_detects_insight_with_i_think():
    msg = (
        "I think the key to getting 8th graders to care about CRQs is "
        "making them argue something they actually believe."
    )
    assert looks_like_original_thinking(msg)


def test_detects_insight_with_in_my_experience():
    msg = (
        "In my experience, stations always outperform jigsaws when "
        "the reading level is too high for some students."
    )
    assert looks_like_original_thinking(msg)


def test_detects_insight_with_students_always():
    msg = (
        "Students always shut down when I hand them a dense primary "
        "source without pre-teaching the vocabulary first."
    )
    assert looks_like_original_thinking(msg)


def test_rejects_operational_command():
    assert not looks_like_original_thinking("generate a lesson on Douglass")
    assert not looks_like_original_thinking("ok")
    assert not looks_like_original_thinking("please create a worksheet")


def test_rejects_short_messages():
    # Too short even if it has an insight marker
    assert not looks_like_original_thinking("I think yes")


def test_rejects_messages_without_insight_markers():
    # No insight markers at all
    msg = "The lesson was on Frederick Douglass and we used stations."
    assert not looks_like_original_thinking(msg)


# ── extract_slug_from_message ────────────────────────────────────────────


def test_extract_slug_from_i_think():
    msg = "I think stations always outperform jigsaws for dense text."
    slug = extract_slug_from_message(msg)
    assert "stations" in slug
    assert slug.startswith("stations") or "outperform" in slug
    assert "-" in slug  # proper slugification


def test_extract_slug_truncates_long_messages():
    msg = "I think " + "word " * 50
    slug = extract_slug_from_message(msg, max_len=30)
    assert len(slug) <= 30


def test_extract_slug_handles_punctuation():
    msg = "I believe students! need, sentence: starters?"
    slug = extract_slug_from_message(msg)
    assert "!" not in slug
    assert "," not in slug
    assert ":" not in slug
    assert "?" not in slug


# ── capture_original ─────────────────────────────────────────────────────


def test_capture_saves_insight(tmp_store: BrainStore):
    msg = (
        "I've noticed that when I define cognitive verbs explicitly "
        "before assessments, students score noticeably better on CRQs."
    )
    page = capture_original(msg, store=tmp_store)
    assert page is not None
    assert page.page_type == "original"
    assert "define cognitive verbs" in page.compiled_truth


def test_capture_preserves_exact_phrasing(tmp_store: BrainStore):
    """The language IS the insight — exact phrasing must be preserved."""
    msg = (
        "I find that my weakest readers become my best writers when "
        "I give them sentence starters they can OWN — not just use."
    )
    page = capture_original(msg, store=tmp_store)
    assert page is not None
    # The exact distinctive phrasing should be present
    assert "OWN — not just use" in page.compiled_truth


def test_capture_rejects_non_insights(tmp_store: BrainStore):
    page = capture_original("generate a lesson", store=tmp_store)
    assert page is None


def test_capture_force_saves_anything(tmp_store: BrainStore):
    page = capture_original(
        "generate a lesson on Douglass",
        store=tmp_store,
        force=True,
    )
    assert page is not None


def test_capture_deduplicates_exact_matches(tmp_store: BrainStore):
    msg = (
        "I've noticed that defining explain explicitly helps student "
        "performance on constructed response questions."
    )
    page1 = capture_original(msg, store=tmp_store)
    assert page1 is not None
    initial_timeline = len(page1.timeline)

    # Capturing again should not create a new page — just append timeline
    page2 = capture_original(msg, store=tmp_store)
    assert page2 is not None
    assert page2.slug == page1.slug
    assert len(page2.timeline) == initial_timeline + 1


def test_capture_sets_tier_1(tmp_store: BrainStore):
    """Originals are always Tier 1 — highest value content."""
    msg = (
        "I think the secret to good history lessons is making the "
        "past feel like it matters to today."
    )
    page = capture_original(msg, store=tmp_store)
    assert page is not None
    assert page.metadata.get("tier") == "1"
