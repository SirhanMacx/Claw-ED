"""Tests for the chatbot engine and feedback/improver modules."""

import json

import pytest

from clawed.database import Database
from clawed.feedback import analyze_feedback, collect_feedback


@pytest.fixture
def db(tmp_path):
    """Create a temporary database for testing."""
    database = Database(tmp_path / "test_chat.db")
    yield database
    database.close()


# ── Chat engine ───────────────────────────────────────────────────────


class TestChatEngine:
    def test_student_chat_import(self):
        from clawed.chat import student_chat

        assert callable(student_chat)

    def test_chat_function_signature(self):
        import inspect

        from clawed.chat import student_chat

        sig = inspect.signature(student_chat)
        params = list(sig.parameters.keys())
        assert "question" in params
        assert "lesson_json" in params
        assert "persona" in params
        assert "chat_history" in params


# ── Feedback module ───────────────────────────────────────────────────


class TestFeedback:
    def test_collect_feedback(self, db):
        tid = db.upsert_teacher("T", "{}")
        uid = db.insert_unit(tid, "U", "S", "8", "T", "{}")
        lid = db.insert_lesson(uid, 1, "L1", "{}")
        fid = collect_feedback(db, lid, 4, "Nice lesson", ["objective", "do_now"])
        assert len(fid) == 12
        feedback = db.get_feedback_for_lesson(lid)
        assert len(feedback) == 1
        assert feedback[0]["rating"] == 4
        sections = json.loads(feedback[0]["sections_edited"])
        assert "objective" in sections

    def test_collect_feedback_clamps_rating(self, db):
        tid = db.upsert_teacher("T", "{}")
        uid = db.insert_unit(tid, "U", "S", "8", "T", "{}")
        lid = db.insert_lesson(uid, 1, "L1", "{}")
        collect_feedback(db, lid, 10)  # Should clamp to 5
        feedback = db.get_feedback_for_lesson(lid)
        assert feedback[0]["rating"] == 5

    def test_collect_feedback_clamps_low(self, db):
        tid = db.upsert_teacher("T", "{}")
        uid = db.insert_unit(tid, "U", "S", "8", "T", "{}")
        lid = db.insert_lesson(uid, 1, "L1", "{}")
        collect_feedback(db, lid, -5)  # Should clamp to 1
        feedback = db.get_feedback_for_lesson(lid)
        assert feedback[0]["rating"] == 1

    def test_analyze_feedback_empty(self, db):
        result = analyze_feedback(db, days=7)
        assert result["total_feedback"] == 0
        assert result["avg_rating"] == 0.0

    def test_analyze_feedback_with_data(self, db):
        tid = db.upsert_teacher("T", "{}")
        uid = db.insert_unit(tid, "U", "S", "8", "T", "{}")
        lid = db.insert_lesson(uid, 1, "L1", "{}")
        collect_feedback(db, lid, 5, "Great!")
        collect_feedback(db, lid, 3, "Okay")
        collect_feedback(db, lid, 1, "Bad", ["objective"])
        result = analyze_feedback(db, days=7)
        assert result["total_feedback"] == 3
        assert result["avg_rating"] == 3.0
        assert result["low_rated_count"] == 1
        assert "objective" in result["most_edited_sections"]


# ── Improver module ───────────────────────────────────────────────────


class TestImprover:
    def test_improver_import(self):
        from clawed.improver import improve_prompts

        assert callable(improve_prompts)

    def test_prompt_files_mapping(self):
        from clawed.improver import PROMPT_FILES

        assert "lesson_plan" in PROMPT_FILES
        assert "unit_plan" in PROMPT_FILES
        assert "persona_extract" in PROMPT_FILES

    def test_check_and_promote_no_candidates(self, db):
        from clawed.improver import _check_and_promote

        # Should not raise with no data
        _check_and_promote(db, "lesson_plan")

    def test_check_and_promote_with_data(self, db):
        from clawed.improver import _check_and_promote

        p1 = db.insert_prompt_version("lesson_plan", 1, "v1")
        p2 = db.insert_prompt_version("lesson_plan", 2, "v2")
        # Simulate usage: p2 has better rating and enough usage
        db.update_prompt_stats(p1, 3.0, 15)
        db.update_prompt_stats(p2, 4.5, 15)
        _check_and_promote(db, "lesson_plan")
        active = db.get_active_prompt("lesson_plan")
        assert active["id"] == p2


# ── Database chat methods ─────────────────────────────────────────────


class TestDatabaseChat:
    def test_insert_and_get_chat_history(self, db):
        tid = db.upsert_teacher("T", "{}")
        uid = db.insert_unit(tid, "U", "S", "8", "T", "{}")
        lid = db.insert_lesson(uid, 1, "L1", "{}")

        db.insert_chat_message(lid, "user", "What is photosynthesis?")
        db.insert_chat_message(lid, "assistant", "Photosynthesis is a process...")
        db.insert_chat_message(lid, "user", "Can you explain more?")

        history = db.get_chat_history(lid, limit=10)
        assert len(history) == 3

    def test_count_chat_sessions(self, db):
        tid = db.upsert_teacher("T", "{}")
        uid = db.insert_unit(tid, "U", "S", "8", "T", "{}")
        lid1 = db.insert_lesson(uid, 1, "L1", "{}")
        lid2 = db.insert_lesson(uid, 2, "L2", "{}")

        db.insert_chat_message(lid1, "user", "Q1")
        db.insert_chat_message(lid2, "user", "Q2")
        assert db.count_chat_sessions() == 2

    def test_empty_chat_history(self, db):
        history = db.get_chat_history("nonexistent")
        assert history == []
