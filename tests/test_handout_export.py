"""Tests for LLM-generated handout export."""

from __future__ import annotations

import tempfile
from pathlib import Path

from clawed.export_handout import export_handout_docx


def test_basic_handout_export():
    handout_data = {
        "title": "Women's Suffrage",
        "do_now": "What does equality mean to you?",
        "vocabulary": [
            {"term": "Suffrage", "definition": "The right to vote"},
            {"term": "Amendment", "definition": "A change to the Constitution"},
        ],
        "source_excerpts": [
            {
                "text": "We hold these truths to be self-evident: that all men and women are created equal.",
                "attribution": "Elizabeth Cady Stanton, Declaration of Sentiments, 1848",
            }
        ],
        "organizer": {
            "title": "Source Analysis",
            "columns": ["Author", "Date", "Main Argument", "Evidence"],
            "instructions": "Analyze each primary source using the columns below.",
            "num_rows": 3,
        },
        "activity_instructions": "Work with your group to complete the graphic organizer.",
        "exit_ticket_questions": [
            "Why was the Seneca Falls Convention significant?",
            "How did suffragists use the Declaration of Independence in their argument?",
        ],
    }
    with tempfile.TemporaryDirectory() as tmp:
        path = export_handout_docx(handout_data, subject="history", output_dir=Path(tmp))
        assert path.exists()
        assert path.suffix == ".docx"
        assert "handout" in path.name.lower() or "packet" in path.name.lower()


def test_minimal_handout():
    handout_data = {"title": "Quick Lesson", "do_now": "Think about it."}
    with tempfile.TemporaryDirectory() as tmp:
        path = export_handout_docx(handout_data, output_dir=Path(tmp))
        assert path.exists()


def test_empty_handout():
    handout_data = {}
    with tempfile.TemporaryDirectory() as tmp:
        path = export_handout_docx(handout_data, output_dir=Path(tmp))
        assert path.exists()
