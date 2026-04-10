"""Tests for the shared noise words module."""

from clawed.noise_words import ALL_NOISE, EDUCATION_NOISE, STOP_WORDS

# ── Stop words ──────────────────────────────────────────────────────


def test_all_noise_contains_stop_words():
    """ALL_NOISE is a superset of STOP_WORDS."""
    assert STOP_WORDS.issubset(ALL_NOISE)
    # Spot-check a few canonical stop words
    for word in ("the", "a", "and", "or", "is", "for", "in", "on"):
        assert word in ALL_NOISE, f"Expected '{word}' in ALL_NOISE"


# ── Education noise ─────────────────────────────────────────────────


def test_all_noise_contains_education_noise():
    """ALL_NOISE is a superset of EDUCATION_NOISE."""
    assert EDUCATION_NOISE.issubset(ALL_NOISE)
    # Spot-check education structure terms that should be filtered
    for word in ("lesson", "handout", "worksheet", "exit ticket", "rubric"):
        assert word in ALL_NOISE, f"Expected '{word}' in ALL_NOISE"


# ── Slide markers ───────────────────────────────────────────────────


def test_slide_markers_in_noise():
    """Slide-related markers are in the noise set to filter document artifacts."""
    slide_markers = {"[slide", "slide]", "slide 1", "slide 2", "slide 3"}
    for marker in slide_markers:
        assert marker in EDUCATION_NOISE, f"Expected slide marker '{marker}' in EDUCATION_NOISE"
    # Also verify they propagate to ALL_NOISE
    for marker in slide_markers:
        assert marker in ALL_NOISE, f"Expected slide marker '{marker}' in ALL_NOISE"
