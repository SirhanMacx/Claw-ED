"""Thin student Telegram transport — httpx-based polling loop.

Students join a class with a code from their teacher, then ask questions
about the lesson. The bot answers in the teacher's voice.

Separate from the teacher bot (transports/telegram.py). Run with:
    clawed student-bot --token YOUR_STUDENT_BOT_TOKEN
"""

from __future__ import annotations

import asyncio
import logging
import signal
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from clawed.transports.telegram import TelegramAPI

if TYPE_CHECKING:
    from clawed.bot_state import StudentBotStateStore

logger = logging.getLogger(__name__)

# Error log path (separate from teacher bot)
def _student_error_log() -> Path:
    import os as _os
    base = Path(_os.environ.get("EDUAGENT_DATA_DIR", str(Path.home() / ".eduagent")))
    return base / "student_errors.log"

_ERROR_LOG = _student_error_log()

# Commands registered with BotFather
STUDENT_BOT_COMMANDS: list[tuple[str, str]] = [
    ("join", "Join a class with your class code"),
    ("topic", "See what your class is studying"),
    ("help", "Show all commands"),
    ("quit", "Leave your current class"),
]

# Module-level session store keyed by chat_id (in-memory cache)
_student_sessions: dict[int, dict[str, str]] = {}

# Persistent store — lazy-initialized
_student_state_store: StudentBotStateStore | None = None


def _get_student_store() -> StudentBotStateStore:
    global _student_state_store
    if _student_state_store is None:
        from clawed.bot_state import StudentBotStateStore

        _student_state_store = StudentBotStateStore()
    return _student_state_store


def _get_session(chat_id: int) -> dict[str, str]:
    """Get or create a student session for a chat."""
    if chat_id not in _student_sessions:
        # Try to restore from persistent storage
        store = _get_student_store()
        row = store.get(chat_id)
        if row is not None:
            _student_sessions[chat_id] = {
                "class_code": row.get("class_code", ""),
                "student_id": row.get("student_id", ""),
            }
        else:
            _student_sessions[chat_id] = {}
    return _student_sessions[chat_id]


def _persist_student_session(chat_id: int, session: dict[str, str]) -> None:
    """Write current in-memory session to the persistent store."""
    store = _get_student_store()
    store.save(
        chat_id,
        class_code=session.get("class_code", ""),
        student_id=session.get("student_id", ""),
    )


def _log_error(error: Exception) -> None:
    """Append error to the student_errors.log file."""
    try:
        _ERROR_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(_ERROR_LOG, "a") as f:
            import datetime

            f.write(f"[{datetime.datetime.now(datetime.UTC).isoformat()}] {type(error).__name__}: {error}\n")
    except (FileNotFoundError, OSError):
        pass


def _send_response(api: TelegramAPI, chat_id: int, text: str) -> None:
    """Send a response via TelegramAPI (handles splitting internally)."""
    api.send_message(chat_id, text)


class StudentTelegramBot:
    """Standalone httpx-based Telegram bot for students.

    Students join with /join CODE, then ask free-text questions.
    The bot routes questions through the StudentBot engine.
    """

    def __init__(self, token: str) -> None:
        self.token = token
        self.api = TelegramAPI(token)
        self._running = False

    def start(self) -> None:
        """Start the polling loop. Blocks until interrupted."""
        from clawed.student_bot import StudentBot

        bot = StudentBot()

        # Register commands with Telegram
        self.api.set_my_commands(
            [{"command": cmd, "description": desc} for cmd, desc in STUDENT_BOT_COMMANDS]
        )

        me = self.api.get_me()
        bot_name = me.get("username", "unknown")
        logger.info("Student bot @%s started, entering polling loop", bot_name)
        print(f"Claw-ED student bot @{bot_name} is running. Press Ctrl+C to stop.")

        self._running = True

        def _signal_handler(sig: Any, frame: Any) -> None:
            self._running = False

        signal.signal(signal.SIGINT, _signal_handler)
        signal.signal(signal.SIGTERM, _signal_handler)

        offset = 0
        while self._running:
            try:
                updates = self.api.get_updates(offset=offset, timeout=30)
                for update in updates:
                    offset = update["update_id"] + 1
                    self._process_update(update, bot)
            except Exception as e:
                logger.error("Error in student polling loop: %s", e)
                _log_error(e)
                time.sleep(2)

        print("\nStudent bot stopped.")
        self.api.close()

    def _process_update(self, update: dict, bot: Any) -> None:
        """Route an update to the appropriate handler."""
        msg = update.get("message")
        if not msg or not msg.get("text"):
            return

        chat_id = msg["chat"]["id"]
        user_id = msg["from"]["id"]
        text = msg["text"].strip()

        try:
            if text.startswith("/start"):
                self._cmd_start(chat_id)
            elif text.startswith("/help"):
                self._cmd_help(chat_id)
            elif text.startswith("/join"):
                self._cmd_join(chat_id, user_id, text, bot)
            elif text.startswith("/topic"):
                self._cmd_topic(chat_id, bot)
            elif text.startswith("/quit"):
                self._cmd_quit(chat_id)
            elif not text.startswith("/"):
                self._handle_message(chat_id, user_id, text, bot)
        except Exception as e:
            logger.error("Error processing student update: %s", e)
            _log_error(e)

    def _cmd_start(self, chat_id: int) -> None:
        self.api.send_message(
            chat_id,
            "Welcome to Claw-ED Student Bot!\n\n"
            "I answer your questions about today's lesson \u2014 in your teacher's voice.\n\n"
            "To get started, use:\n"
            "  /join CODE  \u2014 join your class (e.g. /join AB-CDE-3)\n\n"
            "Once you've joined, just type your question and I'll help you out!\n"
            "Type /help to see all commands.",
        )

    def _cmd_help(self, chat_id: int) -> None:
        self.api.send_message(
            chat_id,
            "Claw-ED Student Bot Commands\n\n"
            "/join CODE \u2014 Join a class with your class code\n"
            "/topic \u2014 See what your class is studying\n"
            "/help \u2014 Show this message\n"
            "/quit \u2014 Leave your current class\n\n"
            "After joining, just type your question!",
        )

    def _cmd_join(self, chat_id: int, user_id: int, text: str, bot: Any) -> None:
        student_id = str(user_id)
        parts = text.split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip():
            self.api.send_message(chat_id, "Usage: /join CODE\n\nExample: /join AB-CDE-3")
            return

        code = parts[1].strip().upper()
        class_info = bot.get_class(code)
        if not class_info or bot.is_expired(code):
            self.api.send_message(chat_id, "That class code is not valid. Ask your teacher for a new one.")
            return

        bot.register_student(student_id, code)

        session = _get_session(chat_id)
        session["class_code"] = code
        session["student_id"] = student_id
        _persist_student_session(chat_id, session)

        teacher_name = class_info.name or "your teacher"
        topic = class_info.topic or "today's lesson"
        self.api.send_message(
            chat_id,
            f"You joined {class_info.name or code}! "
            f"{teacher_name} is teaching {topic}. "
            f"Go ahead and ask me anything!",
        )

    def _cmd_topic(self, chat_id: int, bot: Any) -> None:
        session = _get_session(chat_id)
        code = session.get("class_code")

        if not code:
            self.api.send_message(
                chat_id, "You haven't joined a class yet. Use /join CODE to connect to your class."
            )
            return

        class_info = bot.get_class(code)
        if not class_info:
            self.api.send_message(chat_id, "Your class is no longer available. Use /join CODE to join a new one.")
            return

        topic = class_info.topic or "No topic set yet"
        name = class_info.name or code
        self.api.send_message(chat_id, f"Class: {name}\nTopic: {topic}")

    def _cmd_quit(self, chat_id: int) -> None:
        session = _get_session(chat_id)
        if not session.get("class_code"):
            self.api.send_message(chat_id, "You're not in a class right now.")
            return

        class_name = session.get("class_code", "")
        session.clear()
        _get_student_store().delete(chat_id)
        self.api.send_message(chat_id, f"You left {class_name}. Use /join CODE to join another class.")

    def _handle_message(self, chat_id: int, user_id: int, text: str, bot: Any) -> None:
        """Route free-text messages to the StudentBot engine."""
        session = _get_session(chat_id)
        code = session.get("class_code")
        student_id = session.get("student_id", str(user_id))

        if not code:
            self.api.send_message(chat_id, "Use /join CODE first to connect to your class.")
            return

        # Show typing indicator
        self.api.send_chat_action(chat_id, "typing")

        # Call StudentBot engine with retry
        try:
            answer = asyncio.run(bot.handle_message(text, student_id, code))
        except Exception as first_err:
            _log_error(first_err)
            logger.warning("First attempt failed: %s, retrying...", first_err)
            time.sleep(1)
            try:
                answer = asyncio.run(bot.handle_message(text, student_id, code))
            except Exception as retry_err:
                _log_error(retry_err)
                logger.error("Retry also failed: %s", retry_err)
                self.api.send_message(
                    chat_id, "Hmm, I'm having trouble right now. Try asking again in a moment!"
                )
                return

        self.api.send_message(chat_id, answer)

        # Log student interaction to workspace profile (best-effort)
        try:
            from clawed.workspace import update_student_profile

            student_name = f"student_{student_id}"
            topic = f"[{code}] Q: {text[:100]}"
            update_student_profile(student_name, topic)
        except ImportError:
            pass


def run_student_bot(token: str) -> None:
    """Entry point — create and run the student bot."""
    StudentTelegramBot(token).start()
