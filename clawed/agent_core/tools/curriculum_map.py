"""Tool: curriculum_map — wraps CurriculumMapper.generate_year_map."""

from __future__ import annotations

import json
from typing import Any

from clawed.agent_core.context import AgentContext, ToolResult


class CurriculumMapTool:
    """Generate a full-year curriculum map for a subject and grade."""

    risk_level = "read_only"

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "curriculum_map",
                "description": (
                    "Generate a full-year curriculum map with units, big ideas, "
                    "and an assessment calendar for a subject and grade level."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "subject": {
                            "type": "string",
                            "description": "Academic subject (e.g. 'Math', 'Science')",
                        },
                        "grade": {
                            "type": "string",
                            "description": "Grade level (e.g. '8', 'K', '11-12')",
                        },
                        "school_year": {
                            "type": "string",
                            "description": "School year label (e.g. '2025-26')",
                            "default": "",
                        },
                        "total_weeks": {
                            "type": "integer",
                            "description": "Total instructional weeks in the year",
                            "default": 36,
                        },
                    },
                    "required": ["subject", "grade"],
                },
            },
        }

    async def execute(self, params: dict[str, Any], context: AgentContext) -> ToolResult:
        from clawed.curriculum_map import CurriculumMapper
        from clawed.models import TeacherPersona

        subject = params["subject"]
        grade = params["grade"]
        school_year = params.get("school_year", "")
        total_weeks = params.get("total_weeks", 36)

        persona = TeacherPersona()
        if context.persona:
            try:
                persona = TeacherPersona(**context.persona)
            except Exception:
                pass

        try:
            mapper = CurriculumMapper(context.config)
            year_map = await mapper.generate_year_map(
                subject=subject,
                grade_level=grade,
                persona=persona,
                school_year=school_year,
                total_weeks=total_weeks,
            )
            map_data = year_map.model_dump()
            title = map_data.get("title", f"{subject} Grade {grade}")
            num_units = len(year_map.units) if hasattr(year_map, "units") else 0
            return ToolResult(
                text=f"Generated curriculum map: {title} "
                f"({num_units} units, {total_weeks} weeks)\n\n"
                f"{json.dumps(map_data, indent=2)[:2000]}",
                data=map_data,
                side_effects=[f"Generated year map for {subject} grade {grade}"],
            )
        except Exception as e:
            return ToolResult(text=f"Failed to generate curriculum map: {e}")
