"""Tool: student_insights — query student question patterns for reteaching."""

from __future__ import annotations

import logging
from typing import Any

from clawed.agent_core.context import AgentContext, ToolResult

logger = logging.getLogger(__name__)


class StudentInsightsTool:
    risk_level = "read_only"

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "student_insights",
                "description": "Analyze student question patterns to find confusion topics. "
                "Shows what students are struggling with so you can plan reteach activities.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "class_code": {
                            "type": "string",
                            "description": "Filter by class code (optional)",
                        },
                        "days": {
                            "type": "integer",
                            "description": "Look back this many days (default 7)",
                            "default": 7,
                        },
                    },
                },
            },
        }

    async def execute(self, params: dict[str, Any], context: AgentContext) -> ToolResult:
        days = params.get("days", 7)
        class_code = params.get("class_code", "")

        try:
            from clawed.state import _get_conn, init_db

            init_db()
            with _get_conn() as conn:
                if class_code:
                    rows = conn.execute(
                        "SELECT lesson_topic, COUNT(*) as count FROM student_questions "
                        "WHERE class_code = ? AND created_at >= datetime('now', ?) "
                        "GROUP BY lesson_topic ORDER BY count DESC LIMIT 10",
                        (class_code, f"-{days} days"),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT lesson_topic, COUNT(*) as count FROM student_questions "
                        "WHERE created_at >= datetime('now', ?) "
                        "GROUP BY lesson_topic ORDER BY count DESC LIMIT 10",
                        (f"-{days} days",),
                    ).fetchall()

            if not rows:
                return ToolResult(text=f"No student questions in the last {days} days.")

            total = sum(r["count"] for r in rows)
            lines = [f"Student confusion topics (last {days} days, {total} total questions):"]
            for r in rows:
                topic = r["lesson_topic"] or "General"
                lines.append(f"  - {topic}: {r['count']} questions")

            return ToolResult(
                text="\n".join(lines),
                data={"topics": [{"topic": r["lesson_topic"], "count": r["count"]} for r in rows]},
            )
        except Exception as e:
            return ToolResult(text=f"Could not query student insights: {e}")
