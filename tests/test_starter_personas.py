"""Tests for starter persona selection."""

from clawed.starter_personas import (
    STARTER_PERSONAS,
    get_starter_persona,
    list_starter_subjects,
)


def test_starter_personas_has_four_subjects():
    """Four built-in subjects: social_studies, science, math, ela."""
    assert len(STARTER_PERSONAS) == 4
    assert "social_studies" in STARTER_PERSONAS
    assert "science" in STARTER_PERSONAS
    assert "math" in STARTER_PERSONAS
    assert "ela" in STARTER_PERSONAS


def test_get_starter_persona_direct_key():
    """Direct key lookup returns the correct persona."""
    persona = get_starter_persona("science")
    assert persona is not None
    assert persona.subject_area == "Science"


def test_get_starter_persona_alias():
    """Subject alias resolves correctly."""
    persona = get_starter_persona("biology")
    assert persona is not None
    assert persona.subject_area == "Science"

    persona = get_starter_persona("us history")
    assert persona is not None
    assert persona.subject_area == "Social Studies"


def test_get_starter_persona_case_insensitive():
    """Lookup is case-insensitive."""
    persona = get_starter_persona("MATH")
    assert persona is not None
    assert persona.subject_area == "Math"


def test_get_starter_persona_unknown_falls_back():
    """Unknown subject falls back to social_studies."""
    persona = get_starter_persona("underwater basket weaving")
    assert persona is not None
    assert persona.subject_area == "Social Studies"


def test_list_starter_subjects():
    """Lists all available starter persona subjects."""
    subjects = list_starter_subjects()
    assert len(subjects) == 4
    assert "Science" in subjects
    assert "Math" in subjects
