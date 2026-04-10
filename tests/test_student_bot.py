"""Tests for the student bot, class management, and MCP server."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

from clawed.models import TeacherPersona
from clawed.state import init_db


def _run(coro):
    """Run an async coroutine synchronously."""
    return asyncio.run(coro)


# ── Fixtures ────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _use_tmp_db(tmp_path, monkeypatch):
    """Route all state.py DB operations to a temp directory."""
    monkeypatch.setattr("clawed.state.DEFAULT_DATA_DIR", tmp_path)
    init_db()


# ── Student session creation ────────────────────────────────────────


class TestStudentSessionCreation:
    def test_student_session_dataclass(self):
        from clawed.student_bot import StudentSession

        session = StudentSession(
            student_id="stu-001",
            teacher_id="teacher-mac",
            class_code="MR-MAC-P3",
        )
        assert session.student_id == "stu-001"
        assert session.teacher_id == "teacher-mac"
        assert session.class_code == "MR-MAC-P3"
        assert session.message_count == 0

    def test_student_session_defaults(self):
        from clawed.student_bot import StudentSession

        session = StudentSession(student_id="stu-002")
        assert session.teacher_id == ""
        assert session.current_lesson_id == ""
        assert session.class_code == ""


# ── Class creation and management ───────────────────────────────────


class TestClassCreation:
    def test_create_class_returns_code(self):
        from clawed.student_bot import StudentBot

        bot = StudentBot()
        code = bot.create_class("teacher-001")
        # Code format: AB-CDE-N (2 uppercase + 3 uppercase + 1 digit)
        assert len(code.split("-")) == 3
        assert len(code) >= 8

    def test_create_class_is_unique(self):
        from clawed.student_bot import StudentBot

        bot = StudentBot()
        code1 = bot.create_class("teacher-001")
        code2 = bot.create_class("teacher-001")
        assert code1 != code2

    def test_get_class_returns_none_for_unknown(self):
        from clawed.student_bot import StudentBot

        bot = StudentBot()
        assert bot.get_class("NONEXISTENT") is None

    def test_get_class_returns_info(self):
        from clawed.student_bot import StudentBot

        bot = StudentBot()
        code = bot.create_class("teacher-mac")
        info = bot.get_class(code)
        assert info is not None
        assert info.class_code == code
        assert info.teacher_id == "teacher-mac"
        assert info.hint_mode is False


# ── Set active lesson ───────────────────────────────────────────────


class TestSetActiveLesson:
    def test_set_active_lesson(self):
        from clawed.student_bot import StudentBot

        bot = StudentBot()
        code = bot.create_class("teacher-mac")

        lesson_data = json.dumps({"title": "Photosynthesis", "objective": "Learn about plants"})
        _run(bot.set_active_lesson(code, "lesson-1", "teacher-mac", lesson_data))

        info = bot.get_class(code)
        assert info.active_lesson_id == "lesson-1"
        assert info.active_lesson_json == lesson_data

    def test_set_active_lesson_creates_class_if_needed(self):
        from clawed.student_bot import StudentBot

        bot = StudentBot()
        _run(bot.set_active_lesson("NEW-CLASS-01", "lesson-1", "teacher-new", '{"title": "Test"}'))

        info = bot.get_class("NEW-CLASS-01")
        assert info is not None
        assert info.teacher_id == "teacher-new"


# ── Handle question ─────────────────────────────────────────────────


class TestHandleQuestion:
    def test_unknown_class_code(self):
        from clawed.student_bot import StudentBot

        bot = StudentBot()
        result = _run(bot.handle_message("What is photosynthesis?", "stu-001", "BAD-CODE"))
        assert "don't recognize" in result.lower()

    def test_no_active_lesson(self):
        from clawed.student_bot import StudentBot

        bot = StudentBot()
        code = bot.create_class("teacher-001")
        result = _run(bot.handle_message("Help!", "stu-001", code))
        assert "hasn't activated" in result.lower()

    @patch("clawed.chat.student_chat", new_callable=AsyncMock)
    def test_handle_question_returns_string(self, mock_chat):
        from clawed.state import TeacherSession
        from clawed.student_bot import StudentBot

        # Set up teacher session with persona
        session = TeacherSession(
            teacher_id="teacher-mac",
            persona=TeacherPersona(name="Mr. Mac", subject_area="Science"),
        )
        session.save()

        bot = StudentBot()
        code = bot.create_class("teacher-mac")
        lesson = json.dumps(
            {
                "title": "Photosynthesis",
                "objective": "Explain photosynthesis",
                "do_now": "What do plants need?",
                "direct_instruction": "Plants use sunlight...",
                "guided_practice": "Label the diagram",
                "independent_work": "Answer questions 1-5",
            }
        )
        _run(bot.set_active_lesson(code, "lesson-1", "teacher-mac", lesson))

        mock_chat.return_value = "Great question! Plants use sunlight to make food."

        result = _run(bot.handle_message("What is photosynthesis?", "stu-001", code))
        assert isinstance(result, str)
        assert len(result) > 0
        mock_chat.assert_called_once()


# ── Hint mode ───────────────────────────────────────────────────────


class TestHintMode:
    @patch("clawed.chat.student_chat", new_callable=AsyncMock)
    def test_hint_mode_does_not_give_direct_answer(self, mock_chat):
        from clawed.state import TeacherSession
        from clawed.student_bot import StudentBot

        # Set up teacher with persona
        session = TeacherSession(
            teacher_id="teacher-hint",
            persona=TeacherPersona(name="Ms. Hint"),
        )
        session.save()

        bot = StudentBot()
        code = bot.create_class("teacher-hint")
        lesson = json.dumps({"title": "Test Lesson", "objective": "Test"})
        _run(bot.set_active_lesson(code, "lesson-1", "teacher-hint", lesson))

        # Enable hint mode
        bot.set_hint_mode(code, True)

        info = bot.get_class(code)
        assert info.hint_mode is True

        mock_chat.return_value = "Think about what plants need from the sun..."

        result = _run(bot.handle_message("What's the answer to #3?", "stu-002", code))
        assert isinstance(result, str)

        # Verify the hint mode instruction was passed to the chat function
        call_args = mock_chat.call_args
        question_arg = call_args.kwargs.get("question", "")
        assert "HINT MODE" in question_arg

    def test_set_hint_mode_toggle(self):
        from clawed.student_bot import StudentBot

        bot = StudentBot()
        code = bot.create_class("teacher-toggle")

        bot.set_hint_mode(code, True)
        assert bot.get_class(code).hint_mode is True

        bot.set_hint_mode(code, False)
        assert bot.get_class(code).hint_mode is False


# ── Student report ──────────────────────────────────────────────────


class TestStudentReport:
    def test_empty_report(self):
        from clawed.student_bot import StudentBot

        bot = StudentBot()
        code = bot.create_class("teacher-report")
        report = _run(bot.get_student_report(code))

        assert report["class_code"] == code
        assert report["student_count"] == 0
        assert report["total_messages"] == 0
        assert report["recent_questions"] == []

    @patch("clawed.chat.student_chat", new_callable=AsyncMock)
    def test_report_after_questions(self, mock_chat):
        from clawed.state import TeacherSession
        from clawed.student_bot import StudentBot

        session = TeacherSession(
            teacher_id="teacher-rpt",
            persona=TeacherPersona(name="Mr. Report"),
        )
        session.save()

        bot = StudentBot()
        code = bot.create_class("teacher-rpt")
        lesson = json.dumps({"title": "History 101", "objective": "Learn history"})
        _run(bot.set_active_lesson(code, "lesson-1", "teacher-rpt", lesson))

        mock_chat.return_value = "The Civil War began in 1861."

        _run(bot.handle_message("When did the Civil War start?", "stu-A", code))
        _run(bot.handle_message("Who was president?", "stu-B", code))

        report = _run(bot.get_student_report(code))
        assert report["student_count"] == 2
        assert report["total_messages"] == 2
        assert len(report["recent_questions"]) == 2


# ── Student registration ───────────────────────────────────────────


class TestStudentRegistration:
    def test_register_student_bad_class(self):
        from clawed.student_bot import StudentBot

        bot = StudentBot()
        result = bot.register_student("stu-001", "BAD-CODE", "Alice")
        assert "don't recognize" in result.lower()

    def test_register_student_success(self):
        from clawed.student_bot import StudentBot

        bot = StudentBot()
        code = bot.create_class("teacher-mac")
        result = bot.register_student("stu-001", code, "Alice")
        assert "welcome" in result.lower()
        assert bot.is_registered("stu-001", code)

    def test_register_student_already_registered(self):
        from clawed.student_bot import StudentBot

        bot = StudentBot()
        code = bot.create_class("teacher-mac")
        bot.register_student("stu-001", code, "Alice")
        result = bot.register_student("stu-001", code, "Alice")
        assert "already registered" in result.lower()

    def test_is_registered_false_before_registration(self):
        from clawed.student_bot import StudentBot

        bot = StudentBot()
        code = bot.create_class("teacher-mac")
        assert not bot.is_registered("stu-new", code)

    def test_get_registered_students(self):
        from clawed.student_bot import StudentBot

        bot = StudentBot()
        code = bot.create_class("teacher-mac")
        bot.register_student("stu-001", code, "Alice")
        bot.register_student("stu-002", code, "Bob")

        students = bot.get_registered_students(code)
        assert len(students) == 2
        names = {s["display_name"] for s in students}
        assert "Alice" in names
        assert "Bob" in names

    def test_register_student_no_name_uses_id(self):
        from clawed.student_bot import StudentBot

        bot = StudentBot()
        code = bot.create_class("teacher-mac")
        bot.register_student("stu-anon", code)

        students = bot.get_registered_students(code)
        assert len(students) == 1
        assert students[0]["display_name"] == "stu-anon"


# ── Confusion detection ────────────────────────────────────────────


class TestConfusionDetection:
    def test_detect_confused_about(self):
        from clawed.student_bot import StudentBot

        topic = StudentBot.detect_confusion_topic("I'm confused about the powder keg analogy")
        assert topic == "the powder keg analogy"

    def test_detect_dont_understand(self):
        from clawed.student_bot import StudentBot

        topic = StudentBot.detect_confusion_topic("I don't understand alliances")
        assert topic == "alliances"

    def test_detect_explain(self):
        from clawed.student_bot import StudentBot

        topic = StudentBot.detect_confusion_topic("can you explain the MANIA acronym?")
        assert topic is not None
        assert "mania" in topic.lower()

    def test_detect_help_me_understand(self):
        from clawed.student_bot import StudentBot

        topic = StudentBot.detect_confusion_topic("help me understand nationalism")
        assert topic == "nationalism"

    def test_no_confusion_in_normal_question(self):
        from clawed.student_bot import StudentBot

        topic = StudentBot.detect_confusion_topic("What year did WWI start?")
        assert topic is None

    def test_find_lesson_section_match(self):
        from clawed.student_bot import StudentBot

        lesson = {
            "direct_instruction": "The powder keg analogy refers to the Balkans in 1914.",
            "guided_practice": "Students label a map.",
        }
        section = StudentBot._find_lesson_section_for_topic("powder keg", lesson)
        assert "powder keg" in section.lower()

    def test_find_lesson_section_no_match(self):
        from clawed.student_bot import StudentBot

        lesson = {
            "direct_instruction": "Plants use sunlight.",
            "guided_practice": "Label diagram.",
        }
        section = StudentBot._find_lesson_section_for_topic("quantum physics", lesson)
        assert section == ""

    @patch("clawed.chat.student_chat", new_callable=AsyncMock)
    def test_confusion_injects_lesson_context(self, mock_chat):
        from clawed.state import TeacherSession
        from clawed.student_bot import StudentBot

        session = TeacherSession(
            teacher_id="teacher-conf",
            persona=TeacherPersona(name="Mr. Mac"),
        )
        session.save()

        bot = StudentBot()
        code = bot.create_class("teacher-conf")
        lesson = json.dumps(
            {
                "title": "WWI Causes",
                "objective": "Understand causes of WWI",
                "direct_instruction": (
                    "The powder keg analogy refers to the Balkans region before 1914. "
                    "Nationalism, militarism, and imperial rivalry had packed the region with tension."
                ),
                "guided_practice": "Map activity",
            }
        )
        _run(bot.set_active_lesson(code, "lesson-3", "teacher-conf", lesson))

        mock_chat.return_value = "Great question about the powder keg!"

        _run(bot.handle_message("I'm confused about the powder keg analogy", "stu-001", code))

        call_args = mock_chat.call_args
        question_arg = call_args.kwargs.get("question", "")
        assert "powder keg" in question_arg.lower()
        assert "confused about" in question_arg.lower()


# ── Mode toggle ────────────────────────────────────────────────────


class TestModeToggle:
    def test_get_mode_default_is_answer(self):
        from clawed.student_bot import StudentBot

        bot = StudentBot()
        code = bot.create_class("teacher-mode")
        assert bot.get_mode(code) == "answer"

    def test_get_mode_hint_when_enabled(self):
        from clawed.student_bot import StudentBot

        bot = StudentBot()
        code = bot.create_class("teacher-mode")
        bot.set_hint_mode(code, True)
        assert bot.get_mode(code) == "hint"

    def test_get_mode_answer_when_disabled(self):
        from clawed.student_bot import StudentBot

        bot = StudentBot()
        code = bot.create_class("teacher-mode")
        bot.set_hint_mode(code, True)
        bot.set_hint_mode(code, False)
        assert bot.get_mode(code) == "answer"

    @patch("clawed.chat.student_chat", new_callable=AsyncMock)
    def test_answer_mode_no_hint_instruction(self, mock_chat):
        from clawed.state import TeacherSession
        from clawed.student_bot import StudentBot

        session = TeacherSession(
            teacher_id="teacher-ans",
            persona=TeacherPersona(name="Mr. Answer"),
        )
        session.save()

        bot = StudentBot()
        code = bot.create_class("teacher-ans")
        lesson = json.dumps({"title": "Test", "objective": "Test"})
        _run(bot.set_active_lesson(code, "lesson-1", "teacher-ans", lesson))

        # hint mode is OFF (answer mode)
        mock_chat.return_value = "The answer is 42."

        _run(bot.handle_message("What's the answer to #3?", "stu-001", code))

        call_args = mock_chat.call_args
        question_arg = call_args.kwargs.get("question", "")
        assert "HINT MODE" not in question_arg

    @patch("clawed.chat.student_chat", new_callable=AsyncMock)
    def test_hint_mode_includes_socratic_instruction(self, mock_chat):
        from clawed.state import TeacherSession
        from clawed.student_bot import StudentBot

        session = TeacherSession(
            teacher_id="teacher-soc",
            persona=TeacherPersona(name="Mr. Socrates"),
        )
        session.save()

        bot = StudentBot()
        code = bot.create_class("teacher-soc")
        lesson = json.dumps({"title": "Test", "objective": "Test"})
        _run(bot.set_active_lesson(code, "lesson-1", "teacher-soc", lesson))

        bot.set_hint_mode(code, True)
        mock_chat.return_value = "What do you think?"

        _run(bot.handle_message("Give me the answer", "stu-001", code))

        call_args = mock_chat.call_args
        question_arg = call_args.kwargs.get("question", "")
        assert "Socratic" in question_arg
        assert "NEVER give direct answers" in question_arg


# ── Conversation memory ────────────────────────────────────────────


class TestConversationMemory:
    @patch("clawed.chat.student_chat", new_callable=AsyncMock)
    def test_history_passed_to_chat(self, mock_chat):
        from clawed.state import TeacherSession
        from clawed.student_bot import StudentBot

        session = TeacherSession(
            teacher_id="teacher-mem",
            persona=TeacherPersona(name="Mr. Memory"),
        )
        session.save()

        bot = StudentBot()
        code = bot.create_class("teacher-mem")
        lesson = json.dumps({"title": "Memory Test", "objective": "Remember things"})
        _run(bot.set_active_lesson(code, "lesson-1", "teacher-mem", lesson))

        mock_chat.return_value = "First answer."
        _run(bot.handle_message("First question", "stu-001", code))

        mock_chat.return_value = "Second answer referencing first."
        _run(bot.handle_message("Follow-up question", "stu-001", code))

        # On the second call, chat_history should contain the first exchange
        second_call = mock_chat.call_args_list[1]
        history = second_call.kwargs.get("chat_history", [])
        assert len(history) >= 2
        assert history[0]["content"] == "First question"
        assert history[1]["content"] == "First answer."

    @patch("clawed.chat.student_chat", new_callable=AsyncMock)
    def test_different_students_have_separate_memory(self, mock_chat):
        from clawed.state import TeacherSession
        from clawed.student_bot import StudentBot

        session = TeacherSession(
            teacher_id="teacher-sep",
            persona=TeacherPersona(name="Mr. Sep"),
        )
        session.save()

        bot = StudentBot()
        code = bot.create_class("teacher-sep")
        lesson = json.dumps({"title": "Test", "objective": "Test"})
        _run(bot.set_active_lesson(code, "lesson-1", "teacher-sep", lesson))

        mock_chat.return_value = "Answer for Alice."
        _run(bot.handle_message("Alice's question", "stu-alice", code))

        mock_chat.return_value = "Answer for Bob."
        _run(bot.handle_message("Bob's question", "stu-bob", code))

        # Bob's call should NOT contain Alice's history
        bob_call = mock_chat.call_args_list[1]
        history = bob_call.kwargs.get("chat_history", [])
        for msg in history:
            assert "Alice" not in msg["content"]


# ── Student CLI module ─────────────────────────────────────────────


class TestStudentCLI:
    def test_student_cli_importable(self):
        from clawed.student_cli import cli_entry, main

        assert callable(main)
        assert callable(cli_entry)


# ── Router patterns ─────────────────────────────────────────────────


class TestRouterStudentBotPatterns:
    def test_start_student_bot_intent(self):
        from clawed.router import Intent, parse_intent

        result = parse_intent("start student bot for lesson 1")
        assert result.intent == Intent.START_STUDENT_BOT

    def test_show_student_report_intent(self):
        from clawed.router import Intent, parse_intent

        result = parse_intent("show me what students are asking")
        assert result.intent == Intent.SHOW_STUDENT_REPORT

    def test_set_hint_mode_intent(self):
        from clawed.router import Intent, parse_intent

        result = parse_intent("set homework hint mode")
        assert result.intent == Intent.SET_HINT_MODE

    def test_activate_student_chat(self):
        from clawed.router import Intent, parse_intent

        result = parse_intent("activate student chat")
        assert result.intent == Intent.START_STUDENT_BOT

    def test_student_activity_report(self):
        from clawed.router import Intent, parse_intent

        result = parse_intent("student activity report")
        assert result.intent == Intent.SHOW_STUDENT_REPORT

    def test_disable_hint_mode(self):
        from clawed.router import Intent, parse_intent

        result = parse_intent("disable hint mode")
        assert result.intent == Intent.SET_HINT_MODE


# ── MCP server ──────────────────────────────────────────────────────


_has_mcp = True
try:
    import mcp  # noqa: F401
except ImportError:
    _has_mcp = False


@pytest.mark.skipif(not _has_mcp, reason="mcp package not installed")
class TestMCPServer:
    def test_mcp_server_import(self):
        from clawed.mcp_server import mcp

        assert mcp is not None

    def test_mcp_tools_registered(self):
        from clawed.mcp_server import mcp

        # FastMCP registers tools internally; verify our module loaded
        assert hasattr(mcp, "run")

    def test_mcp_tool_functions_exist(self):
        from clawed.mcp_server import (
            generate_lesson,
            generate_unit,
            get_teacher_standards,
            ingest_materials,
            student_question,
        )

        assert callable(generate_lesson)
        assert callable(generate_unit)
        assert callable(ingest_materials)
        assert callable(student_question)
        assert callable(get_teacher_standards)
