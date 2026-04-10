"""Tool: generate_materials — wraps clawed.materials worksheet/assessment generation."""

from __future__ import annotations

import json
from typing import Any

from clawed.agent_core.context import AgentContext, ToolResult


class GenerateMaterialsTool:
    """Generate supplementary materials (worksheet) for a lesson topic."""

    risk_level = "read_only"

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "generate_materials",
                "description": (
                    "Generate supplementary teaching materials such as worksheets for a given topic and grade level."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "topic": {
                            "type": "string",
                            "description": "The lesson/unit topic",
                        },
                        "grade": {
                            "type": "string",
                            "description": "Grade level (e.g. '8', 'K')",
                            "default": "8",
                        },
                        "subject": {
                            "type": "string",
                            "description": "Subject area",
                            "default": "General",
                        },
                    },
                    "required": ["topic"],
                },
            },
        }

    async def execute(self, params: dict[str, Any], context: AgentContext) -> ToolResult:
        from clawed.materials import generate_worksheet
        from clawed.models import DailyLesson, TeacherPersona

        topic = params["topic"]
        grade = params.get("grade", "8")

        persona = TeacherPersona()
        if context.persona:
            try:
                persona = TeacherPersona(**context.persona)
            except Exception:
                pass

        # Build a minimal DailyLesson to pass to generate_worksheet
        lesson = DailyLesson(
            lesson_number=1,
            title=topic,
            objective=f"Students will understand {topic}.",
            grade_level=grade,
        )

        try:
            items = await generate_worksheet(
                lesson=lesson,
                persona=persona,
                config=context.config,
            )
            items_data = [item.model_dump() for item in items]
            return ToolResult(
                text=f"Generated {len(items)} worksheet items for {topic}\n\n{json.dumps(items_data, indent=2)[:2000]}",
                data={"items": items_data},
                side_effects=[f"Generated worksheet for {topic}"],
            )
        except Exception as e:
            return ToolResult(text=f"Failed to generate materials: {e}")
