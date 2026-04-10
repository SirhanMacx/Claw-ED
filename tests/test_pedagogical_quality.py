"""Pedagogical quality validation — stimulus, notes, sources, differentiation."""

import json
from pathlib import Path

import pytest

DEMO_DIR = Path(__file__).parent.parent / "clawed" / "demo"


class TestPedagogicalQuality:
    """Validate pedagogical quality of the demo MasterContent fixture."""

    @pytest.fixture
    def master_content(self):
        from clawed.master_content import MasterContent

        fixture_path = DEMO_DIR / "demo_master_content.json"
        data = json.loads(fixture_path.read_text(encoding="utf-8"))
        return MasterContent.model_validate(data)

    def test_exit_ticket_has_analysis_question(self, master_content):
        """At least one exit ticket question requires analysis or higher."""
        higher_order = {"analysis", "evaluation", "synthesis", "application", "create"}
        levels = [q.cognitive_level.lower() for q in master_content.exit_ticket]
        assert any(lv in higher_order for lv in levels), (
            f"No analysis-or-higher exit ticket questions. Levels: {levels}"
        )

    def test_exit_ticket_questions_have_stimulus(self, master_content):
        """Every exit ticket question has a non-empty stimulus."""
        for i, q in enumerate(master_content.exit_ticket):
            assert q.stimulus.strip(), f"Exit ticket question {i + 1} has empty stimulus"

    def test_guided_notes_minimum_count(self, master_content):
        """At least 5 guided notes per lesson (fill-in-the-blank)."""
        assert len(master_content.guided_notes) >= 5, f"Only {len(master_content.guided_notes)} guided notes, need >= 5"

    def test_primary_sources_minimum_count(self, master_content):
        """At least 1 primary source per lesson."""
        assert len(master_content.primary_sources) >= 1, "No primary sources"

    def test_do_now_is_stimulus_based(self, master_content):
        """Do Now has a non-empty stimulus."""
        assert master_content.do_now.stimulus.strip(), "Do Now has empty stimulus"

    def test_no_delegation_phrases(self, master_content):
        """No delegation phrases in any text field."""
        from clawed.validation import check_self_contained

        all_text = master_content.title + " " + master_content.objective
        for section in master_content.direct_instruction:
            all_text += " " + section.content + " " + " ".join(section.key_points)
        violations = check_self_contained(all_text)
        assert len(violations) == 0, f"Delegation phrases found: {violations}"

    def test_differentiation_is_specific(self, master_content):
        """Differentiation notes are specific (not just 'provide support')."""
        diff = master_content.differentiation
        for note in diff.struggling:
            assert len(note) > 20, f"Struggling note too generic: '{note}'"
        for note in diff.advanced:
            assert len(note) > 20, f"Advanced note too generic: '{note}'"
