"""Shared noise words for curriculum content filtering.

Used by kg_extractor.py (entity extraction) and curriculum_visualizer.py
(graph filtering) to consistently identify non-curriculum terms. One
canonical set — no duplication.
"""
from __future__ import annotations

# Generic English stop words
STOP_WORDS: frozenset[str] = frozenset({
    "the", "a", "an", "and", "or", "for", "in", "on", "of", "to", "is",
    "it", "by", "at", "be", "as", "do", "if", "so", "no", "up", "but",
    "not", "was", "are", "has", "had", "its", "this", "that", "with",
    "from", "will", "can", "all", "may", "new", "one", "two", "use",
})

# Education structure terms — NOT curriculum concepts
EDUCATION_NOISE: frozenset[str] = frozenset({
    # Lesson structure
    "lesson", "plan", "lesson plan", "unit", "chapter", "section", "part",
    "do now", "exit ticket", "warm up", "objective", "aim", "goals",
    "directions", "instructions", "rubric", "overview", "activity",
    # Document types
    "handout", "worksheet", "packet", "notes", "review", "test", "quiz",
    "exam", "homework", "assignment", "project", "presentation",
    # Generic terms
    "name", "date", "period", "class", "grade", "grading", "student",
    "teacher", "answer", "question", "questions", "page", "slide",
    "copy", "blank", "version", "final", "draft", "new", "old", "group",
    "materials", "resources", "learning experience",
    # File artifacts
    "[slide", "slide]", "slide 1", "slide 2", "slide 3",
    # Document format terms
    "pdf", "doc", "docx", "pptx", "ppt", "txt",
})

# Combined set for quick membership tests
ALL_NOISE: frozenset[str] = STOP_WORDS | EDUCATION_NOISE
