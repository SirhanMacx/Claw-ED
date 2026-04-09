"""Tool: search_lessons — queries Database for lesson history."""
from __future__ import annotations

from typing import Any

from clawed.agent_core.context import AgentContext, ToolResult


class SearchLessonsTool:
    """Search previously generated lessons by unit ID."""

    risk_level = "read_only"

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "search_lessons",
                "description": (
                    "Search previously generated lessons stored in the database. "
                    "Returns a list of lessons for a given unit."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "unit_id": {
                            "type": "string",
                            "description": "The unit ID to search lessons for",
                        },
                    },
                    "required": ["unit_id"],
                },
            },
        }

    async def execute(
        self, params: dict[str, Any], context: AgentContext
    ) -> ToolResult:
        from clawed.database import Database

        unit_id = params["unit_id"]

        try:
            db = Database()
            lessons = db.list_lessons(unit_id)
            if not lessons:
                return ToolResult(
                    text=f"No lessons found for unit {unit_id}.",
                    data={"lessons": []},
                )
            # Convert Row objects to dicts
            lesson_list = [dict(row) for row in lessons]
            lines = [f"Found {len(lesson_list)} lesson(s) for unit {unit_id}:"]
            for row in lesson_list[:10]:
                title = row.get("title", "Untitled")
                num = row.get("lesson_number", "?")
                lines.append(f"  Lesson {num}: {title}")
            if len(lesson_list) > 10:
                lines.append(f"  ... and {len(lesson_list) - 10} more")
            return ToolResult(
                text="\n".join(lines),
                data={"lessons": lesson_list},
            )
        except Exception as e:
            return ToolResult(text=f"Failed to search lessons: {e}")
