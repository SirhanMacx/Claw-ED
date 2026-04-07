"""Multi-format lesson export handler.

Supports: slides (PPTX), handout, doc (DOCX), pdf.
Extracted from tg.py lines 1623-1693.
"""
from __future__ import annotations

import logging
from pathlib import Path

from clawed.gateway_response import GatewayResponse
from clawed.models import DailyLesson, TeacherPersona

logger = logging.getLogger(__name__)


def _load_lesson(lesson_id: str, teacher_id: str) -> DailyLesson | None:
    """Load a lesson from the database by ID."""
    try:
        from clawed.state import _get_conn
        with _get_conn() as conn:
            row = conn.execute(
                "SELECT lesson_json FROM generated_lessons WHERE id = ? AND teacher_id = ?",
                (lesson_id, teacher_id),
            ).fetchone()
            if row:
                return DailyLesson.model_validate_json(row["lesson_json"])
    except Exception as e:
        logger.debug("Could not load lesson %s: %s", lesson_id, e)
    return None


def _load_persona(teacher_id: str) -> TeacherPersona | None:
    """Load teacher persona from session state."""
    try:
        from clawed.state import TeacherSession
        session = TeacherSession.load(teacher_id)
        return session.persona
    except Exception:
        return None


class ExportHandler:
    """Handles lesson export to various formats."""

    SUPPORTED_FORMATS = {"slides", "handout", "doc", "pdf"}

    async def export(self, lesson_id: str, teacher_id: str, fmt: str) -> GatewayResponse:
        """Export a lesson in the requested format."""
        if fmt not in self.SUPPORTED_FORMATS:
            return GatewayResponse(
                text=f"Format '{fmt}' is not supported. Try: slides, handout, doc, or pdf."
            )

        lesson = _load_lesson(lesson_id, teacher_id)
        if not lesson:
            return GatewayResponse(text="I couldn't find that lesson. Generate one first!")

        persona = _load_persona(teacher_id)
        output_dir = Path.home() / ".eduagent" / "exports"
        output_dir.mkdir(parents=True, exist_ok=True)

        try:
            file_path = await self._do_export(lesson, persona, output_dir, fmt, teacher_id=teacher_id)
            caption = {
                "slides": "Here are your slides!",
                "handout": "Here's the student handout!",
                "doc": "Here's the full lesson plan document!",
                "pdf": "Here's your lesson as a PDF!",
            }.get(fmt, "Here's your export!")
            return GatewayResponse(text=caption, files=[file_path])
        except Exception as e:
            logger.error("Export failed: %s", e)
            return GatewayResponse(text=f"Export failed: {e}")

    async def _do_export(self, lesson, persona, output_dir, fmt, teacher_id: str = "") -> Path:
        from clawed.doc_export import (
            export_lesson_docx,
            export_lesson_pdf,
            export_lesson_pptx,
            export_student_handout,
        )
        if fmt == "slides":
            return export_lesson_pptx(lesson, persona, output_dir, teacher_id=teacher_id)
        elif fmt == "handout":
            return export_student_handout(lesson, persona, output_dir)
        elif fmt == "doc":
            return export_lesson_docx(lesson, persona, output_dir)
        elif fmt == "pdf":
            return export_lesson_pdf(lesson, persona, output_dir)
        raise ValueError(f"Unknown export format: {fmt}")
