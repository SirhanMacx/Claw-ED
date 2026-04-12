"""Claw-ED Hermes Plugin — thin shim delegating to the gateway.

External callers (Telegram bot, tests, CLI) import these names:
    handle_message   — routes through gateway.handle()
    get_last_lesson_id
    _show_status
    _transcribe_attachments
    _fmt_unit_summary, _fmt_lesson_summary, _fmt_persona  (re-exported from generation)

All generation logic lives in clawed.generation (the service layer).
All routing lives in clawed.gateway (the brain).
"""
from __future__ import annotations

from pathlib import Path

from clawed.generation import _fmt_lesson_summary, _fmt_persona, _fmt_unit_summary
from clawed.models import AppConfig
from clawed.state import TeacherSession

# Re-export formatters for backward compatibility
__all__ = [
    "_fmt_lesson_summary",
    "_fmt_persona",
    "_fmt_unit_summary",
    "_show_status",
    "_transcribe_attachments",
    "get_last_lesson_id",
    "handle_message",
]

# ── Rating helpers ────────────────────────────────────────────────────────────


def get_last_lesson_id(teacher_id: str) -> str | None:
    """Return the ID of the most recently generated lesson, then clear it.

    Used by Telegram bot and CLI chat to offer a rating prompt.
    """
    session = TeacherSession.load(teacher_id)
    lesson_id = session.config.pop("last_lesson_id", None)
    if lesson_id:
        session.save()
    return lesson_id


# ── Audio transcription ───────────────────────────────────────────────────────


async def _transcribe_attachments(attachments: list[str]) -> str:
    """Transcribe any audio files found in the attachment list."""
    from clawed.voice import is_audio_file, transcribe_audio

    parts: list[str] = []
    for att in attachments:
        if is_audio_file(att):
            try:
                text = await transcribe_audio(Path(att))
                if text:
                    parts.append(text)
            except (FileNotFoundError, OSError):
                pass  # Skip files that fail to transcribe
    return " ".join(parts)


# ── Status ────────────────────────────────────────────────────────────────────


def _show_status(session: TeacherSession) -> str:
    """Return a formatted status string for the given session."""
    lines = ["\u2699\ufe0f *Claw-ED Status*", ""]
    if session.persona:
        style = session.persona.teaching_style.value.replace("_", " ").title()
        lines.append(f"\U0001f469\u200d\U0001f3eb Persona: {style} teacher")
        if session.persona.subject_area:
            lines.append(f"\U0001f4da Subject: {session.persona.subject_area}")
        if session.persona.grade_levels:
            lines.append(f"\U0001f393 Grades: {', '.join(session.persona.grade_levels)}")
    else:
        lines.append("\U0001f469\u200d\U0001f3eb Persona: Not set up yet")

    if session.config.get("drive_url"):
        lines.append("\u2601\ufe0f Drive: Connected")
    elif session.config.get("materials_path"):
        lines.append(f"\U0001f4c1 Materials: {Path(session.config['materials_path']).name}")
    else:
        lines.append("\U0001f4c2 Materials: Not connected")

    config = AppConfig.load()
    lines.append(f"\U0001f916 LLM: {config.provider.value}")

    if session.current_unit:
        lines.append(f"\U0001f4d6 Current unit: {session.current_unit.title}")
    if session.current_lesson:
        lines.append(f"\U0001f4dd Current lesson: {session.current_lesson.title}")

    recent = session.get_recent_units(limit=3)
    if recent:
        lines.append("")
        lines.append("\U0001f4da Recent units:")
        for u in recent:
            lines.append(f"  \u2022 {u['title']} ({u['subject']}, Gr. {u['grade_level']})")

    return "\n".join(lines)


# ── Main handler (thin shim) ────────────────────────────────────────────────


async def handle_message(
    message: str,
    teacher_id: str,
    *,
    subject: str | None = None,
    grade: str | None = None,
    attachments: list[str] | None = None,
) -> str:
    """Handle a teacher message and return a response string.

    This is the backward-compatible entry point.  It delegates to the gateway
    for routing and intent dispatch.  The gateway calls into
    clawed.generation for the actual LLM work.
    """
    # Auto-transcribe audio attachments
    if attachments:
        transcribed = await _transcribe_attachments(attachments)
        if transcribed:
            message = transcribed if not message.strip() else message + "\n\n" + transcribed

    # Delegate to the gateway (the single brain)
    from clawed.gateway import Gateway
    gw = Gateway()
    response = await gw.handle(message, teacher_id)
    return response.text
