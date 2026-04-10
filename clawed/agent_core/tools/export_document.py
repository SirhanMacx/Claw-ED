"""Tool: export_document — wraps PDF/DOCX/PPTX export functions."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from clawed.agent_core.context import AgentContext, ToolResult


class ExportDocumentTool:
    """Export a lesson plan to PDF, DOCX, or PPTX format."""

    risk_level = "write_local"

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "export_document",
                "description": (
                    "Export a lesson plan to a document format (PDF, DOCX, or PPTX). "
                    "Requires a topic to generate the lesson first, then exports it."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "topic": {
                            "type": "string",
                            "description": "Lesson topic to export",
                        },
                        "format": {
                            "type": "string",
                            "description": "Export format: 'pdf', 'docx', or 'pptx'",
                            "enum": ["pdf", "docx", "pptx"],
                            "default": "pdf",
                        },
                        "output_dir": {
                            "type": "string",
                            "description": "Output directory path (optional)",
                            "default": "",
                        },
                    },
                    "required": ["topic"],
                },
            },
        }

    async def execute(self, params: dict[str, Any], context: AgentContext) -> ToolResult:
        topic = params["topic"]
        fmt = params.get("format", "pdf")
        output_dir_str = params.get("output_dir", "")

        output_dir = Path(output_dir_str).expanduser().resolve() if output_dir_str else Path("clawed_output").resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        try:
            # First generate a lesson to export
            from clawed.lesson import generate_lesson
            from clawed.models import LessonBrief, TeacherPersona, UnitPlan

            persona = TeacherPersona()
            if context.persona:
                try:
                    persona = TeacherPersona(**context.persona)
                except Exception:
                    pass

            unit = UnitPlan(
                title=f"{topic} Unit",
                subject="General",
                grade_level="8",
                topic=topic,
                duration_weeks=1,
                overview=f"A lesson on {topic}.",
                daily_lessons=[
                    LessonBrief(
                        lesson_number=1,
                        topic=topic,
                        description=f"Introduction to {topic}",
                    )
                ],
            )
            lesson = await generate_lesson(
                lesson_number=1,
                unit=unit,
                persona=persona,
                config=context.config,
            )

            # Now export in the requested format
            if fmt == "pdf":
                from clawed.export_pdf import export_lesson_pdf

                path = export_lesson_pdf(lesson, persona, output_dir)
            elif fmt == "docx":
                from clawed.export_docx import export_lesson_docx

                path = export_lesson_docx(lesson, persona, output_dir)
            elif fmt == "pptx":
                from clawed.export_pptx import export_lesson_pptx

                path = export_lesson_pptx(lesson, persona, output_dir, teacher_id=context.teacher_id)
            else:
                return ToolResult(text=f"Unsupported format: {fmt}")

            return ToolResult(
                text=f"Exported lesson to {fmt.upper()}: {path}",
                files=[path],
                side_effects=[f"Exported {topic} as {fmt.upper()} to {path}"],
            )
        except Exception as e:
            return ToolResult(text=f"Failed to export document: {e}")
