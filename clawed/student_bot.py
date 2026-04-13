"""Student chatbot engine — students ask questions, get answers in their teacher's voice.

The student bot is the other half of Claw-ED. Teachers set up their persona and
activate a lesson; students join with a class code and ask questions about today's
lesson. The bot answers in the teacher's voice, gives hints (not answers) for
homework, and tracks what students are asking so the teacher can see patterns.
"""

from __future__ import annotations

import contextlib
import json
import re
import secrets
import sqlite3
import string
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from clawed.models import AppConfig, TeacherPersona
from clawed.state import _get_conn, init_db


@dataclass
class StudentSession:
    """A student's active chat session."""

    student_id: str
    teacher_id: str = ""
    current_lesson_id: str = ""
    class_code: str = ""
    message_count: int = 0


@dataclass
class ClassInfo:
    """A teacher's class with an active lesson."""

    class_code: str
    teacher_id: str
    name: str = ""
    topic: str = ""
    allowed_lesson_ids: list[str] = field(default_factory=list)
    expires_at: str | None = None
    active_lesson_id: str | None = None
    active_lesson_json: str | None = None
    hint_mode: bool = False
    created_at: str = ""


# Pattern for detecting "I am confused about X" / "I don't understand X"
_CONFUSION_RE = re.compile(
    r"(?:i(?:'m| am) confused (?:about|by|on)|"
    r"i don(?:'t|t) (?:understand|get)|"
    r"(?:can you |could you )?(?:explain|help me (?:understand|with)))"
    r"\s+(.+)",
    re.IGNORECASE,
)


class StudentBot:
    """Student-facing chatbot that answers questions in the teacher's voice."""

    def __init__(self, config: AppConfig | None = None):
        self.config = config or AppConfig.load()
        init_db()

    # ── Class management ─────────────────────────────────────────────────

    @staticmethod
    def _generate_class_code() -> str:
        """Generate a readable but cryptographically-random class code.

        v4.11.2026.1 security fix (P2-5): previously used ``random.choices()``
        which is a non-CSPRNG. A 5-letter + 1-digit code space (~107M) with
        a predictable PRNG is both brute-forceable AND leaks future codes
        once any single code is observed. Now uses ``secrets.choice`` and
        widens the code to 3-4-4 (~7e10 codes) so enumeration is infeasible.
        """
        alphabet = string.ascii_uppercase
        part1 = "".join(secrets.choice(alphabet) for _ in range(3))
        part2 = "".join(secrets.choice(alphabet) for _ in range(4))
        part3 = "".join(secrets.choice(string.digits) for _ in range(4))
        return f"{part1}-{part2}-{part3}"

    def create_class(
        self,
        teacher_id: str,
        name: str = "",
        topic: str = "",
        allowed_lesson_ids: list[str] | None = None,
        expires_at: str | None = None,
    ) -> str:
        """Create a new class and return its class code."""
        code = self._generate_class_code()
        ids_json = json.dumps(allowed_lesson_ids or [])
        with _get_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO classes"
                " (class_code, teacher_id, name, topic, allowed_lesson_ids, expires_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (code, teacher_id, name, topic, ids_json, expires_at),
            )
        return code

    def get_class(self, class_code: str) -> ClassInfo | None:
        """Load class info by code."""
        with _get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM classes WHERE class_code = ?", (class_code,)
            ).fetchone()
        if not row:
            return None
        allowed: list[str] = []
        with contextlib.suppress(json.JSONDecodeError, TypeError, KeyError):
            allowed = json.loads(row["allowed_lesson_ids"] or "[]")
        name = ""
        topic = ""
        expires_at = None
        try:
            name = row["name"] or ""
            topic = row["topic"] or ""
            expires_at = row["expires_at"]
        except (KeyError, IndexError):
            pass
        return ClassInfo(
            class_code=row["class_code"],
            teacher_id=row["teacher_id"],
            name=name,
            topic=topic,
            allowed_lesson_ids=allowed,
            expires_at=expires_at,
            active_lesson_id=row["active_lesson_id"],
            active_lesson_json=row["active_lesson_json"],
            hint_mode=bool(row["hint_mode"]),
            created_at=row["created_at"],
        )

    def is_expired(self, class_code: str) -> bool:
        """Check if a class code has expired."""
        info = self.get_class(class_code)
        if not info or not info.expires_at:
            return False
        try:
            expires = datetime.fromisoformat(info.expires_at)
            # Make naive datetimes comparable by assuming UTC
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=UTC)
            return datetime.now(UTC) > expires
        except (ValueError, TypeError):
            return False

    def revoke_student(self, class_code: str, student_id: str) -> bool:
        """Revoke a student's access to a class."""
        with _get_conn() as conn:
            cur = conn.execute(
                "DELETE FROM registered_students WHERE class_code = ? AND student_id = ?",
                (class_code, student_id),
            )
        return cur.rowcount > 0

    def get_class_stats(self, class_code: str) -> dict[str, Any]:
        """Get stats for a class code."""
        with _get_conn() as conn:
            student_count = conn.execute(
                "SELECT COUNT(DISTINCT student_id) as cnt FROM registered_students WHERE class_code = ?",
                (class_code,),
            ).fetchone()
            question_count = conn.execute(
                "SELECT COUNT(*) as cnt FROM student_questions WHERE class_code = ?",
                (class_code,),
            ).fetchone()
            active_count = conn.execute(
                "SELECT COUNT(DISTINCT student_id) as cnt FROM student_sessions WHERE class_code = ?",
                (class_code,),
            ).fetchone()
        return {
            "class_code": class_code,
            "registered_students": student_count["cnt"] if student_count else 0,
            "total_questions": question_count["cnt"] if question_count else 0,
            "active_students": active_count["cnt"] if active_count else 0,
        }

    async def set_active_lesson(
        self, class_code: str, lesson_id: str, teacher_id: str, lesson_json: str = ""
    ) -> None:
        """Teacher sets which lesson is active for their class."""
        with _get_conn() as conn:
            # Ensure class exists
            row = conn.execute(
                "SELECT class_code FROM classes WHERE class_code = ?", (class_code,)
            ).fetchone()
            if not row:
                conn.execute(
                    """INSERT INTO classes
                    (class_code, teacher_id, active_lesson_id, active_lesson_json)
                    VALUES (?, ?, ?, ?)""",
                    (class_code, teacher_id, lesson_id, lesson_json),
                )
            else:
                conn.execute(
                    """UPDATE classes SET active_lesson_id = ?,
                    active_lesson_json = ?, teacher_id = ?
                    WHERE class_code = ?""",
                    (lesson_id, lesson_json, teacher_id, class_code),
                )

    def set_hint_mode(
        self, class_code: str, enabled: bool, student_name: str | None = None
    ) -> None:
        """Toggle hint mode for a class or a specific student.

        When hint mode is ON: Socratic questioning only, NEVER give direct
        answers to homework/assessment questions.
        When hint mode is OFF (answer mode): full explanations allowed.

        Args:
            class_code: The class code.
            enabled: True for hint mode, False for answer mode.
            student_name: If provided, only set hint mode for this student.
                When None, sets it for the entire class.
        """
        if student_name:
            # Per-student hint mode stored in student_hint_modes table
            with _get_conn() as conn:
                conn.execute(
                    """CREATE TABLE IF NOT EXISTS student_hint_modes (
                        id TEXT PRIMARY KEY,
                        class_code TEXT NOT NULL,
                        student_name TEXT NOT NULL,
                        hint_mode INTEGER NOT NULL DEFAULT 0
                    )"""
                )
                row_id = f"{class_code}:{student_name}"
                conn.execute(
                    """INSERT OR REPLACE INTO student_hint_modes (id, class_code, student_name, hint_mode)
                    VALUES (?, ?, ?, ?)""",
                    (row_id, class_code, student_name, 1 if enabled else 0),
                )
        else:
            with _get_conn() as conn:
                conn.execute(
                    "UPDATE classes SET hint_mode = ? WHERE class_code = ?",
                    (1 if enabled else 0, class_code),
                )

    def get_mode(self, class_code: str, student_id: str = "") -> str:
        """Return 'hint' or 'answer' based on current mode.

        Checks per-student override first, then falls back to class-level setting.
        """
        if student_id:
            with _get_conn() as conn:
                try:
                    row = conn.execute(
                        "SELECT hint_mode FROM student_hint_modes WHERE class_code = ? AND student_name = ?",
                        (class_code, student_id),
                    ).fetchone()
                    if row is not None:
                        return "hint" if row["hint_mode"] else "answer"
                except (sqlite3.OperationalError, OSError):
                    pass  # Table may not exist yet
        info = self.get_class(class_code)
        if info and info.hint_mode:
            return "hint"
        return "answer"

    # ── Student registration ─────────────────────────────────────────────

    def register_student(
        self, student_id: str, class_code: str, display_name: str = ""
    ) -> str:
        """Register a first-time student with a class code.

        Returns a status message. If the class doesn't exist, tells the
        student to check with their teacher.
        """
        class_info = self.get_class(class_code)
        if not class_info:
            return (
                "Hmm, I don't recognize that class code. "
                "Double-check with your teacher and try again!"
            )

        with _get_conn() as conn:
            existing = conn.execute(
                "SELECT id FROM registered_students WHERE student_id = ? AND class_code = ?",
                (student_id, class_code),
            ).fetchone()
            if existing:
                return f"You're already registered for {class_code}! Ask me anything."

            conn.execute(
                """INSERT INTO registered_students
                (id, student_id, class_code, display_name)
                VALUES (?, ?, ?, ?)""",
                (str(uuid.uuid4()), student_id, class_code, display_name),
            )

        return (
            f"Welcome to {class_code}! You're all set. "
            "Ask me anything about today's lesson."
        )

    def is_registered(self, student_id: str, class_code: str) -> bool:
        """Check if a student is registered for a class."""
        with _get_conn() as conn:
            row = conn.execute(
                "SELECT id FROM registered_students WHERE student_id = ? AND class_code = ?",
                (student_id, class_code),
            ).fetchone()
        return row is not None

    def get_registered_students(self, class_code: str) -> list[dict[str, str]]:
        """Return all registered students for a class."""
        with _get_conn() as conn:
            rows = conn.execute(
                "SELECT student_id, display_name, registered_at FROM registered_students WHERE class_code = ?",
                (class_code,),
            ).fetchall()
        return [
            {
                "student_id": r["student_id"],
                "display_name": r["display_name"] or r["student_id"],
                "registered_at": r["registered_at"],
            }
            for r in rows
        ]

    # ── Confusion detection ──────────────────────────────────────────────

    @staticmethod
    def detect_confusion_topic(message: str) -> str | None:
        """Extract the topic from an 'I'm confused about X' message.

        Returns the topic string if detected, otherwise None.
        """
        match = _CONFUSION_RE.search(message)
        if match:
            return match.group(1).strip().rstrip("?.!")
        return None

    @staticmethod
    def _find_lesson_section_for_topic(
        topic: str, lesson_json: dict[str, Any]
    ) -> str:
        """Search lesson content for the section most relevant to the topic.

        Returns the matching section text, or empty string if not found.
        """
        topic_lower = topic.lower()
        # Search these fields in priority order
        sections = [
            ("direct_instruction", lesson_json.get("direct_instruction", "")),
            ("guided_practice", lesson_json.get("guided_practice", "")),
            ("do_now", lesson_json.get("do_now", "")),
            ("independent_work", lesson_json.get("independent_work", "")),
            ("objective", lesson_json.get("objective", "")),
        ]
        for _name, content in sections:
            if topic_lower in content.lower():
                return content
        return ""

    # ── Student message handling ─────────────────────────────────────────

    async def handle_message(
        self, message: str, student_id: str, class_code: str
    ) -> str:
        """Handle a student message. Answers in teacher's voice using lesson context.

        Rules:
        - Give hints, not direct answers to homework questions (when hint mode on)
        - Use the teacher's vocabulary and tone
        - Reference specific parts of today's lesson
        - Track what the student asked (feeds back to teacher)
        - Encouraging, patient, uses teacher's actual phrases
        """
        # Load class info
        class_info = self.get_class(class_code)
        if not class_info:
            return "Hmm, I don't recognize that class code. Double-check with your teacher!"

        # Load teacher persona
        from clawed.state import TeacherSession

        teacher_session = TeacherSession.load(class_info.teacher_id)
        persona = teacher_session.persona or TeacherPersona()

        # Load lesson context
        lesson_json: dict[str, Any] = {}
        if class_info.active_lesson_json:
            with contextlib.suppress(json.JSONDecodeError, TypeError):
                lesson_json = json.loads(class_info.active_lesson_json)

        if not lesson_json:
            return (
                "Your teacher hasn't activated a lesson yet. "
                "Check back soon — they'll set one up for you!"
            )

        # Update student session
        self._touch_student_session(student_id, class_code)

        # Build the response using the existing chat engine
        from clawed.chat import student_chat

        # Build hint mode / answer mode instruction (per-student override)
        hint_instruction = ""
        effective_mode = self.get_mode(class_code, student_id=student_id)
        if effective_mode == "hint":
            hint_instruction = (
                "\n\nIMPORTANT — HINT MODE IS ON (Socratic questioning only):\n"
                "- NEVER give direct answers to homework, assessment, or exit ticket questions.\n"
                "- Use Socratic questioning: ask guiding questions that lead the student to discover the answer.\n"
                "- Break the problem into smaller steps and ask the student to work through each one.\n"
                "- It's okay to confirm correct thinking, give encouragement, or redirect wrong paths.\n"
                "- If the student asks 'what's the answer to #3?' respond with a question like "
                "'What do you think? Let's start with what we learned about...' \n"
                "- Be warm and patient — never make the student feel bad for asking.\n"
            )

        # Detect confusion pattern and inject relevant lesson section
        confusion_context = ""
        confusion_topic = self.detect_confusion_topic(message)
        if confusion_topic:
            section = self._find_lesson_section_for_topic(confusion_topic, lesson_json)
            if section:
                confusion_context = (
                    f"\n\nThe student is confused about '{confusion_topic}'. "
                    f"Here is the specific part of the lesson that covers this:\n"
                    f"---\n{section[:600]}\n---\n"
                    f"Use this content to explain the concept clearly and patiently."
                )

        # Get recent chat history for this student/class
        history = self._get_student_history(student_id, class_code, limit=6)

        answer = await student_chat(
            question=message + hint_instruction + confusion_context,
            lesson_json=lesson_json,
            persona=persona,
            chat_history=history,
            config=self.config,
        )

        # Log the question and answer
        lesson_topic = lesson_json.get("title", "")
        self._log_question(
            student_id=student_id,
            class_code=class_code,
            question=message,
            answer=answer,
            lesson_topic=lesson_topic,
        )

        # Update per-student progress tracking
        self._update_student_progress(student_id, class_code, lesson_topic)

        return answer

    # ── Reporting ────────────────────────────────────────────────────────

    async def get_student_report(self, class_code: str) -> dict:
        """Return what questions students asked (for teacher insight)."""
        with _get_conn() as conn:
            questions = conn.execute(
                """SELECT student_id, question, lesson_topic, created_at
                FROM student_questions WHERE class_code = ?
                ORDER BY created_at DESC LIMIT 50""",
                (class_code,),
            ).fetchall()

            student_count = conn.execute(
                "SELECT COUNT(DISTINCT student_id) as cnt FROM student_sessions WHERE class_code = ?",
                (class_code,),
            ).fetchone()

            total_messages = conn.execute(
                "SELECT SUM(message_count) as total FROM student_sessions WHERE class_code = ?",
                (class_code,),
            ).fetchone()

        return {
            "class_code": class_code,
            "student_count": student_count["cnt"] if student_count else 0,
            "total_messages": total_messages["total"] if total_messages and total_messages["total"] else 0,
            "recent_questions": [
                {
                    "student_id": q["student_id"],
                    "question": q["question"],
                    "topic": q["lesson_topic"],
                    "asked_at": q["created_at"],
                }
                for q in questions
            ],
        }

    async def get_weekly_report(self, class_code: str, week: str = "") -> dict[str, Any]:
        """Generate a weekly progress report for a class code.

        Args:
            class_code: The class code to report on.
            week: ISO week like '2026-W12'. If empty, uses current week.
        """
        if not week:
            now = datetime.now(UTC)
            week = f"{now.year}-W{now.isocalendar()[1]:02d}"

        with _get_conn() as conn:
            # Questions per student (anonymized count)
            per_student = conn.execute(
                "SELECT student_id, COUNT(*) as cnt FROM student_questions"
                " WHERE class_code = ? GROUP BY student_id ORDER BY cnt DESC",
                (class_code,),
            ).fetchall()

            # Most common topics
            topics = conn.execute(
                "SELECT lesson_topic, COUNT(*) as cnt FROM student_questions"
                " WHERE class_code = ? AND lesson_topic != ''"
                " GROUP BY lesson_topic ORDER BY cnt DESC LIMIT 10",
                (class_code,),
            ).fetchall()

            # All questions for struggle analysis
            all_questions = conn.execute(
                "SELECT question FROM student_questions WHERE class_code = ?",
                (class_code,),
            ).fetchall()

        # Build anonymized per-student stats
        student_activity = [
            {"student_number": i + 1, "question_count": r["cnt"]}
            for i, r in enumerate(per_student)
        ]

        common_topics = [
            {"topic": r["lesson_topic"], "count": r["cnt"]}
            for r in topics
        ]

        return {
            "class_code": class_code,
            "week": week,
            "student_count": len(per_student),
            "total_questions": sum(r["cnt"] for r in per_student),
            "student_activity": student_activity,
            "common_topics": common_topics,
            "question_samples": [r["question"] for r in all_questions[:20]],
        }

    def get_student_conversation(
        self, student_id: str, class_code: str, limit: int = 20
    ) -> list[dict[str, str]]:
        """Get a student's full conversation history for today (teacher view)."""
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        with _get_conn() as conn:
            rows = conn.execute(
                """SELECT question, answer, created_at FROM student_questions
                WHERE student_id = ? AND class_code = ? AND created_at LIKE ?
                ORDER BY created_at ASC LIMIT ?""",
                (student_id, class_code, f"{today}%", limit),
            ).fetchall()
        return [
            {
                "question": r["question"],
                "answer": r["answer"],
                "time": r["created_at"],
            }
            for r in rows
        ]

    # ── Internal helpers ─────────────────────────────────────────────────

    def _touch_student_session(self, student_id: str, class_code: str) -> None:
        """Create or update a student session, incrementing message count."""
        session_id = f"{student_id}:{class_code}"
        with _get_conn() as conn:
            existing = conn.execute(
                "SELECT id FROM student_sessions WHERE id = ?", (session_id,)
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE student_sessions SET message_count = message_count + 1, last_activity = ? WHERE id = ?",
                    (datetime.now(UTC).isoformat(), session_id),
                )
            else:
                conn.execute(
                    """INSERT INTO student_sessions
                    (id, student_id, class_code, message_count, last_activity)
                    VALUES (?, ?, ?, 1, ?)""",
                    (session_id, student_id, class_code, datetime.now(UTC).isoformat()),
                )

    def _log_question(
        self,
        student_id: str,
        class_code: str,
        question: str,
        answer: str,
        lesson_topic: str,
    ) -> None:
        """Log a student question for teacher reporting."""
        with _get_conn() as conn:
            conn.execute(
                """INSERT INTO student_questions
                (id, student_id, class_code, question, answer, lesson_topic)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (str(uuid.uuid4()), student_id, class_code, question, answer, lesson_topic),
            )

    def _get_student_history(
        self, student_id: str, class_code: str, limit: int = 6
    ) -> list[dict[str, str]]:
        """Get recent Q&A history for a student in a class."""
        with _get_conn() as conn:
            rows = conn.execute(
                """SELECT question, answer FROM student_questions
                WHERE student_id = ? AND class_code = ?
                ORDER BY created_at DESC LIMIT ?""",
                (student_id, class_code, limit),
            ).fetchall()
        # Reverse to chronological order and format as chat history
        history: list[dict[str, str]] = []
        for row in reversed(rows):
            history.append({"role": "user", "content": row["question"]})
            history.append({"role": "assistant", "content": row["answer"]})
        return history

    def _update_student_progress(
        self, student_id: str, class_code: str, topic: str
    ) -> None:
        """Update per-student progress tracking after a question."""
        try:
            from clawed.bot_state import StudentProgressStore
            from clawed.models import StudentProgress

            store = StudentProgressStore()
            existing = store.get(student_id, class_code)
            if existing:
                progress = StudentProgress(**existing)
            else:
                progress = StudentProgress(
                    student_id=student_id,
                    class_code=class_code,
                )
            progress.record_question(topic)
            store.save(
                student_id=student_id,
                class_code=class_code,
                student_name=progress.student_name,
                topics_asked=progress.topics_asked,
                total_questions=progress.total_questions,
                last_active=progress.last_active,
                struggle_topics=progress.struggle_topics,
            )
        except ImportError:
            pass  # Progress tracking is best-effort

    def get_student_progress(self, class_code: str) -> list[dict]:
        """Get progress data for all students in a class.

        Returns a list of dicts with student activity, topic counts,
        and struggle indicators — intended for the teacher /progress command.
        """
        try:
            from clawed.bot_state import StudentProgressStore

            store = StudentProgressStore()
            return store.get_class_progress(class_code)
        except ImportError:
            return []
