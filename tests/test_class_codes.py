"""Tests for the enhanced class code system, weekly reports, and web database tables."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from clawed.models import TeacherPersona
from clawed.state import init_db


def _run(coro):
    """Run an async coroutine synchronously."""
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _use_tmp_db(tmp_path, monkeypatch):
    """Route all state.py DB operations to a temp directory."""
    monkeypatch.setattr("clawed.state.DEFAULT_DATA_DIR", tmp_path)
    init_db()


# ── Teacher-controlled class code creation ────────────────────────────────


class TestTeacherClassCodes:
    def test_create_class_with_name_and_topic(self):
        from clawed.student_bot import StudentBot

        bot = StudentBot()
        code = bot.create_class(
            "teacher-mac",
            name="Period 3 Global Studies",
            topic="Unit 4: WWI",
        )
        info = bot.get_class(code)
        assert info is not None
        assert info.name == "Period 3 Global Studies"
        assert info.topic == "Unit 4: WWI"

    def test_create_class_with_allowed_lessons(self):
        from clawed.student_bot import StudentBot

        bot = StudentBot()
        code = bot.create_class(
            "teacher-mac",
            allowed_lesson_ids=["lesson-1", "lesson-2"],
        )
        info = bot.get_class(code)
        assert info.allowed_lesson_ids == ["lesson-1", "lesson-2"]

    def test_create_class_with_expiration(self):
        from clawed.student_bot import StudentBot

        bot = StudentBot()
        code = bot.create_class(
            "teacher-mac",
            expires_at="2026-06-15",
        )
        info = bot.get_class(code)
        assert info.expires_at == "2026-06-15"

    def test_class_code_format(self):
        from clawed.student_bot import StudentBot

        bot = StudentBot()
        code = bot.create_class("teacher-mac")
        parts = code.split("-")
        assert len(parts) == 3
        assert parts[0].isalpha() and parts[0].isupper()
        assert parts[1].isalpha() and parts[1].isupper()
        assert parts[2].isdigit()

    def test_expired_class_detected(self):
        from clawed.student_bot import StudentBot

        bot = StudentBot()
        code = bot.create_class("teacher-mac", expires_at="2020-01-01")
        assert bot.is_expired(code) is True

    def test_non_expired_class(self):
        from clawed.student_bot import StudentBot

        bot = StudentBot()
        code = bot.create_class("teacher-mac", expires_at="2099-12-31")
        assert bot.is_expired(code) is False

    def test_no_expiry_not_expired(self):
        from clawed.student_bot import StudentBot

        bot = StudentBot()
        code = bot.create_class("teacher-mac")
        assert bot.is_expired(code) is False


# ── Student revocation ────────────────────────────────────────────────────


class TestStudentRevocation:
    def test_revoke_registered_student(self):
        from clawed.student_bot import StudentBot

        bot = StudentBot()
        code = bot.create_class("teacher-mac")
        bot.register_student("stu-001", code, "Alice")
        assert bot.is_registered("stu-001", code)

        result = bot.revoke_student(code, "stu-001")
        assert result is True
        assert not bot.is_registered("stu-001", code)

    def test_revoke_nonexistent_student(self):
        from clawed.student_bot import StudentBot

        bot = StudentBot()
        code = bot.create_class("teacher-mac")
        result = bot.revoke_student(code, "nobody")
        assert result is False


# ── Class stats ───────────────────────────────────────────────────────────


class TestClassStats:
    def test_empty_class_stats(self):
        from clawed.student_bot import StudentBot

        bot = StudentBot()
        code = bot.create_class("teacher-mac")
        stats = bot.get_class_stats(code)
        assert stats["class_code"] == code
        assert stats["registered_students"] == 0
        assert stats["total_questions"] == 0
        assert stats["active_students"] == 0

    @patch("clawed.chat.student_chat", new_callable=AsyncMock)
    def test_stats_after_activity(self, mock_chat):
        from clawed.state import TeacherSession
        from clawed.student_bot import StudentBot

        session = TeacherSession(
            teacher_id="teacher-stats",
            persona=TeacherPersona(name="Mr. Stats"),
        )
        session.save()

        bot = StudentBot()
        code = bot.create_class("teacher-stats")
        lesson = json.dumps({"title": "Test", "objective": "Test"})
        _run(bot.set_active_lesson(code, "lesson-1", "teacher-stats", lesson))

        bot.register_student("stu-A", code, "Alice")
        bot.register_student("stu-B", code, "Bob")

        mock_chat.return_value = "Answer."
        _run(bot.handle_message("Question 1?", "stu-A", code))
        _run(bot.handle_message("Question 2?", "stu-B", code))

        stats = bot.get_class_stats(code)
        assert stats["registered_students"] == 2
        assert stats["total_questions"] == 2
        assert stats["active_students"] == 2


# ── Weekly report ─────────────────────────────────────────────────────────


class TestWeeklyReport:
    def test_empty_report(self):
        from clawed.student_bot import StudentBot

        bot = StudentBot()
        code = bot.create_class("teacher-rpt")
        report = _run(bot.get_weekly_report(code))
        assert report["class_code"] == code
        assert report["student_count"] == 0
        assert report["total_questions"] == 0

    @patch("clawed.chat.student_chat", new_callable=AsyncMock)
    def test_report_with_data(self, mock_chat):
        from clawed.state import TeacherSession
        from clawed.student_bot import StudentBot

        session = TeacherSession(
            teacher_id="teacher-wrpt",
            persona=TeacherPersona(name="Mr. Weekly"),
        )
        session.save()

        bot = StudentBot()
        code = bot.create_class("teacher-wrpt")
        lesson = json.dumps({"title": "WWI Causes", "objective": "Learn"})
        _run(bot.set_active_lesson(code, "lesson-1", "teacher-wrpt", lesson))

        mock_chat.return_value = "Answer."
        _run(bot.handle_message("What caused WWI?", "stu-A", code))
        _run(bot.handle_message("Who was involved?", "stu-B", code))
        _run(bot.handle_message("When did it start?", "stu-A", code))

        report = _run(bot.get_weekly_report(code))
        assert report["student_count"] == 2
        assert report["total_questions"] == 3
        assert len(report["student_activity"]) == 2
        # Student A asked 2 questions, student B asked 1
        counts = {s["question_count"] for s in report["student_activity"]}
        assert 2 in counts
        assert 1 in counts

    def test_report_with_specific_week(self):
        from clawed.student_bot import StudentBot

        bot = StudentBot()
        code = bot.create_class("teacher-wk")
        report = _run(bot.get_weekly_report(code, "2026-W12"))
        assert report["week"] == "2026-W12"


# ── Web database class code tables ────────────────────────────────────────


class TestWebDatabaseClassCodes:
    def test_create_and_get_class_code(self, tmp_path):
        from clawed.database import Database

        db = Database(tmp_path / "test.db")
        db.create_class_code(
            code="AB-CDE-1",
            teacher_id="teacher-mac",
            name="Period 3",
            topic="WWI",
        )
        row = db.get_class_code("AB-CDE-1")
        assert row is not None
        assert row["name"] == "Period 3"
        assert row["topic"] == "WWI"
        db.close()

    def test_list_class_codes(self, tmp_path):
        from clawed.database import Database

        db = Database(tmp_path / "test.db")
        db.create_class_code(code="AA-BBB-1", teacher_id="t1", name="Class 1")
        db.create_class_code(code="CC-DDD-2", teacher_id="t1", name="Class 2")
        db.create_class_code(code="EE-FFF-3", teacher_id="t2", name="Other")

        codes = db.list_class_codes("t1")
        assert len(codes) == 2
        db.close()

    def test_enroll_and_revoke_student(self, tmp_path):
        from clawed.database import Database

        db = Database(tmp_path / "test.db")
        db.create_class_code(code="XY-ZAB-1", teacher_id="t1")
        db.enroll_student("stu-001", "XY-ZAB-1")
        assert db.count_enrollments("XY-ZAB-1") == 1

        db.revoke_student("XY-ZAB-1", "stu-001")
        assert db.count_enrollments("XY-ZAB-1") == 0
        db.close()

    def test_student_questions(self, tmp_path):
        from clawed.database import Database

        db = Database(tmp_path / "test.db")
        db.insert_student_question("stu-001", "AB-CDE-1", "What is photosynthesis?", "Plants use sunlight.")
        db.insert_student_question("stu-002", "AB-CDE-1", "How do plants grow?", "With water and sun.")

        questions = db.get_student_questions("AB-CDE-1")
        assert len(questions) == 2
        assert db.count_student_questions("AB-CDE-1") == 2
        db.close()


# ── CLI commands ──────────────────────────────────────────────────────────


class TestClassCLI:
    def test_class_app_importable(self):
        from clawed.commands.config import class_app

        assert class_app is not None

    def test_class_commands_registered(self):
        from clawed.commands.config import class_app

        cmd_names = [cmd.name for cmd in class_app.registered_commands]
        assert "create" in cmd_names
        assert "revoke" in cmd_names
        assert "stats" in cmd_names
        assert "report" in cmd_names
        assert "qr" in cmd_names

    def test_class_app_in_main_cli(self):
        from clawed.cli import app

        group_names = [cmd.name for cmd in app.registered_groups]
        assert "class" in group_names


# ── Onboarding enhancements ──────────────────────────────────────────────


class TestOnboardingDetection:
    def test_detect_no_models(self):
        from clawed.onboarding import _detect_available_models

        with (
            patch.dict("os.environ", {}, clear=True),
            patch("httpx.get", side_effect=Exception("no ollama")),
        ):
            provider, msg = _detect_available_models()
            assert provider is None
            assert "No LLM backend" in msg

    def test_detect_anthropic_key(self):
        from clawed.onboarding import _detect_available_models

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-ant-test"}, clear=True):
            provider, msg = _detect_available_models()
            from clawed.models import LLMProvider

            assert provider == LLMProvider.ANTHROPIC
            assert "Anthropic" in msg

    def test_detect_openai_key(self):
        from clawed.onboarding import _detect_available_models

        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}, clear=True):
            provider, msg = _detect_available_models()
            from clawed.models import LLMProvider

            assert provider == LLMProvider.OPENAI
            assert "OpenAI" in msg

    def test_detect_ollama_running(self):
        from clawed.onboarding import _detect_available_models

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"models": [{"name": "llama3.2:latest"}]}

        with (
            patch.dict("os.environ", {}, clear=True),
            patch("httpx.get", return_value=mock_resp),
        ):
            provider, msg = _detect_available_models()
            from clawed.models import LLMProvider

            assert provider == LLMProvider.OLLAMA
            assert "llama3.2" in msg


class TestPersonaPreview:
    def test_preview_confirmed(self):
        from clawed.onboarding import _show_persona_preview

        with patch("clawed.onboarding.Prompt.ask", return_value="y"):
            result = _show_persona_preview(["History"], ["8"], "NY")
            assert result is True

    def test_preview_rejected(self):
        from clawed.onboarding import _show_persona_preview

        with patch("clawed.onboarding.Prompt.ask", return_value="n"):
            result = _show_persona_preview(["Math"], ["6"], "CA")
            assert result is False
