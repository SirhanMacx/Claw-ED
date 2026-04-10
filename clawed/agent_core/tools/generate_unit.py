"""Tool: generate_unit — wraps clawed.planner.plan_unit."""

from __future__ import annotations

import json
from typing import Any

from clawed.agent_core.context import AgentContext, ToolResult


class GenerateUnitTool:
    """Generate a multi-week unit plan on a topic."""

    risk_level = "read_only"

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "generate_unit",
                "description": (
                    "Generate a multi-week unit plan with daily lesson briefs. "
                    "Returns a structured unit with essential questions, "
                    "standards alignment, and a sequence of lessons."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "topic": {
                            "type": "string",
                            "description": "The unit topic",
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
                        "weeks": {
                            "type": "integer",
                            "description": "Duration in weeks",
                            "default": 2,
                        },
                    },
                    "required": ["topic"],
                },
            },
        }

    async def execute(self, params: dict[str, Any], context: AgentContext) -> ToolResult:
        from clawed.models import TeacherPersona
        from clawed.planner import plan_unit

        topic = params["topic"]
        grade = params.get("grade", "8")
        subject = params.get("subject", "General")
        weeks = params.get("weeks", 2)

        persona = TeacherPersona()
        if context.persona:
            try:
                persona = TeacherPersona(**context.persona)
            except Exception:
                pass

        try:
            unit = await plan_unit(
                subject=subject,
                grade_level=grade,
                topic=topic,
                duration_weeks=weeks,
                persona=persona,
                config=context.config,
            )
            unit_data = unit.model_dump()
            title = unit_data.get("title", topic)
            return ToolResult(
                text=f"Generated unit plan: {title} "
                f"({weeks} weeks, {len(unit.daily_lessons)} lessons)\n\n"
                f"{json.dumps(unit_data, indent=2)[:2000]}",
                data=unit_data,
                side_effects=[f"Generated unit plan on {topic}"],
            )
        except Exception as e:
            return ToolResult(text=f"Failed to generate unit plan: {e}")
