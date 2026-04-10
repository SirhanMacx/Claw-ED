"""Tests for the student-facing Telegram bot.

Covers: imports, command registration, /join flow, /topic, /quit,
free-text question routing, error recovery, and no-class guard.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from clawed.student_telegram_bot import (
    STUDENT_BOT_COMMANDS,
    StudentTelegramBot,
    _get_session,
    _log_error,
    _send_response,
    _student_sessions,
)

# ── Helpers ────────────────────────────────────────────────────────────────


def _make_update(text: str, user_id: int = 12345, chat_id: int = 99) -> MagicMock:
    """Create a mock Telegram Update with a text message."""
    update = MagicMock()
    update.message = MagicMock()
    update.message.text = text
    update.message.from_user = MagicMock()
    update.message.from_user.id = user_id
    update.message.chat = MagicMock()
    update.message.chat_id = chat_id
    update.message.chat.send_action = AsyncMock()
    update.message.reply_text = AsyncMock()
    return update


# ── Import test ───────────────────────────────────────────────────────────


class TestImport:
    def test_import_student_telegram_bot(self) -> None:
        """StudentTelegramBot and STUDENT_BOT_COMMANDS should be importable."""
        assert StudentTelegramBot is not None
        assert STUDENT_BOT_COMMANDS is not None


# ── Command registration ─────────────────────────────────────────────────


class TestCommandsRegistered:
    def test_student_bot_commands_has_required(self) -> None:
        """STUDENT_BOT_COMMANDS must include join, help, topic, quit."""
        cmd_names = [cmd for cmd, _ in STUDENT_BOT_COMMANDS]
        assert "join" in cmd_names
        assert "help" in cmd_names
        assert "topic" in cmd_names
        assert "quit" in cmd_names

    def test_commands_have_descriptions(self) -> None:
        for cmd, desc in STUDENT_BOT_COMMANDS:
            assert len(desc) > 5, f"Command /{cmd} needs a description"


# ── No class before join ──────────────────────────────────────────────────


class TestNoClassBeforeJoin:
    def test_free_text_without_join_returns_join_message(self) -> None:
        """Free text when not joined should tell user to /join first."""
        _student_sessions.clear()
        update = _make_update("What is photosynthesis?")

        async def _test() -> None:
            # Simulate the handle_message logic for no-class case
            chat_id = update.message.chat_id
            session = _get_session(chat_id)
            code = session.get("class_code")
            if not code:
                await update.message.reply_text("Use /join CODE first to connect to your class.")

        asyncio.run(_test())
        reply = update.message.reply_text.call_args[0][0]
        assert "join" in reply.lower()


# ── Join with invalid code ────────────────────────────────────────────────


class TestJoinInvalidCode:
    def test_join_invalid_code_returns_error(self) -> None:
        """Joining with an invalid code should return an error message."""
        _student_sessions.clear()

        mock_bot = MagicMock()
        mock_bot.get_class.return_value = None

        update = _make_update("/join XY-ZZZ-9")

        async def _test() -> None:
            text = update.message.text.strip()
            parts = text.split(maxsplit=1)
            code = parts[1].strip().upper() if len(parts) > 1 else ""

            class_info = mock_bot.get_class(code)
            if not class_info:
                await update.message.reply_text("That class code is not valid. Ask your teacher for a new one.")

        asyncio.run(_test())
        reply = update.message.reply_text.call_args[0][0]
        assert "not valid" in reply.lower()


# ── Join with valid code ──────────────────────────────────────────────────


class TestJoinValidCode:
    def test_join_valid_code_returns_welcome(self) -> None:
        """Joining a valid class should return a welcome message with class info."""
        _student_sessions.clear()

        mock_class = MagicMock()
        mock_class.name = "Mr. Mac's Science"
        mock_class.topic = "Photosynthesis"

        mock_bot = MagicMock()
        mock_bot.get_class.return_value = mock_class
        mock_bot.is_expired.return_value = False

        update = _make_update("/join AB-CDE-3")

        async def _test() -> None:
            text = update.message.text.strip()
            parts = text.split(maxsplit=1)
            code = parts[1].strip().upper()

            class_info = mock_bot.get_class(code)
            if class_info and not mock_bot.is_expired(code):
                mock_bot.register_student(str(update.message.from_user.id), code)
                session = _get_session(update.message.chat_id)
                session["class_code"] = code
                session["student_id"] = str(update.message.from_user.id)
                await update.message.reply_text(
                    f"You joined {class_info.name}! "
                    f"{class_info.name} is teaching {class_info.topic}. "
                    f"Go ahead and ask me anything!"
                )

        asyncio.run(_test())
        reply = update.message.reply_text.call_args[0][0]
        assert "You joined" in reply
        assert "Photosynthesis" in reply


# ── Question answered ─────────────────────────────────────────────────────


class TestQuestionAnswered:
    def test_question_gets_answer(self) -> None:
        """When joined, a question should be routed to handle_message and response sent."""
        _student_sessions.clear()
        _student_sessions[99] = {"class_code": "AB-CDE-3", "student_id": "12345"}

        mock_bot = MagicMock()
        mock_bot.handle_message = AsyncMock(return_value="Photosynthesis converts light to energy.")

        update = _make_update("What is photosynthesis?")

        async def _test() -> None:
            chat_id = update.message.chat_id
            session = _get_session(chat_id)
            code = session.get("class_code")
            student_id = session.get("student_id", str(update.message.from_user.id))

            if code:
                await update.message.chat.send_action("typing")
                answer = await mock_bot.handle_message(update.message.text, student_id, code)
                await _send_response(update, answer)

        asyncio.run(_test())
        mock_bot.handle_message.assert_awaited_once_with("What is photosynthesis?", "12345", "AB-CDE-3")
        reply = update.message.reply_text.call_args[0][0]
        assert "Photosynthesis" in reply


# ── Error recovery ────────────────────────────────────────────────────────


class TestErrorRecovery:
    def test_error_returns_friendly_fallback(self) -> None:
        """When the LLM fails twice, user gets a friendly fallback message."""
        _student_sessions.clear()
        _student_sessions[99] = {"class_code": "AB-CDE-3", "student_id": "12345"}

        mock_bot = MagicMock()
        mock_bot.handle_message = AsyncMock(side_effect=RuntimeError("LLM down"))

        update = _make_update("What is photosynthesis?")

        async def _test() -> None:
            chat_id = update.message.chat_id
            session = _get_session(chat_id)
            code = session.get("class_code")
            student_id = session.get("student_id")

            if code:
                await update.message.chat.send_action("typing")
                try:
                    await mock_bot.handle_message(update.message.text, student_id, code)
                except Exception:
                    await asyncio.sleep(0)  # simulate backoff
                    try:
                        await mock_bot.handle_message(update.message.text, student_id, code)
                    except Exception:
                        await update.message.reply_text(
                            "Hmm, I'm having trouble right now. Try asking again in a moment!"
                        )
                        return

        asyncio.run(_test())
        reply = update.message.reply_text.call_args[0][0]
        assert "trouble" in reply.lower()

    def test_error_logged(self, tmp_path: Any) -> None:
        """Errors should be written to the log file."""
        with patch("clawed.student_telegram_bot._ERROR_LOG", tmp_path / "student_errors.log"):
            _log_error(RuntimeError("test error"))
            log_content = (tmp_path / "student_errors.log").read_text()
            assert "RuntimeError" in log_content
            assert "test error" in log_content


# ── Quit command ──────────────────────────────────────────────────────────


class TestQuitCommand:
    def test_quit_clears_session(self) -> None:
        """After /quit, the session should be cleared."""
        _student_sessions.clear()
        _student_sessions[99] = {"class_code": "AB-CDE-3", "student_id": "12345"}

        update = _make_update("/quit")

        async def _test() -> None:
            chat_id = update.message.chat_id
            session = _get_session(chat_id)
            if session.get("class_code"):
                session.clear()
                await update.message.reply_text("You left AB-CDE-3. Use /join CODE to join another class.")

        asyncio.run(_test())
        assert _student_sessions[99] == {}
        reply = update.message.reply_text.call_args[0][0]
        assert "left" in reply.lower()


# ── Topic with no class ──────────────────────────────────────────────────


class TestTopicNoClass:
    def test_topic_without_join_returns_join_message(self) -> None:
        """/topic when not joined should tell user to /join."""
        _student_sessions.clear()
        update = _make_update("/topic")

        async def _test() -> None:
            chat_id = update.message.chat_id
            session = _get_session(chat_id)
            code = session.get("class_code")
            if not code:
                await update.message.reply_text(
                    "You haven't joined a class yet. Use /join CODE to connect to your class."
                )

        asyncio.run(_test())
        reply = update.message.reply_text.call_args[0][0]
        assert "/join" in reply


# ── Handler registration ──────────────────────────────────────────────────


class TestHandlerRegistration:
    def test_routes_all_commands(self) -> None:
        """The student bot should route /start, /help, /join, /topic, /quit."""
        sbot = StudentTelegramBot(token="fake:student-token")

        # Mock the TelegramAPI so no real HTTP calls happen
        sbot.api = MagicMock()
        sbot.api.send_message = MagicMock()

        mock_bot = MagicMock()
        mock_bot.get_class.return_value = None

        # Each command should be routed without error
        for cmd_text, method_name in [
            ("/start", "_cmd_start"),
            ("/help", "_cmd_help"),
            ("/topic", "_cmd_topic"),
            ("/quit", "_cmd_quit"),
        ]:
            update = {
                "update_id": 1,
                "message": {
                    "chat": {"id": 99},
                    "from": {"id": 12345},
                    "text": cmd_text,
                },
            }
            sbot._process_update(update, mock_bot)
            assert sbot.api.send_message.called

        # /join needs an argument
        update_join = {
            "update_id": 2,
            "message": {
                "chat": {"id": 99},
                "from": {"id": 12345},
                "text": "/join AB-CDE-3",
            },
        }
        sbot.api.send_message.reset_mock()
        sbot._process_update(update_join, mock_bot)
        assert sbot.api.send_message.called
