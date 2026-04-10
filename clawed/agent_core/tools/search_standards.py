"""Tool: search_standards — wraps clawed.standards.get_standards."""

from __future__ import annotations

from typing import Any

from clawed.agent_core.context import AgentContext, ToolResult


class SearchStandardsTool:
    """Look up curriculum standards by subject and grade."""

    risk_level = "read_only"

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "search_standards",
                "description": (
                    "Search curriculum standards (Common Core, NGSS, C3) by subject and optional grade level."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "subject": {
                            "type": "string",
                            "description": "Subject area (e.g. 'math', 'science', 'ela')",
                        },
                        "grade": {
                            "type": "string",
                            "description": "Grade level filter (e.g. '8', 'K', '9-12')",
                            "default": "",
                        },
                    },
                    "required": ["subject"],
                },
            },
        }

    async def execute(self, params: dict[str, Any], context: AgentContext) -> ToolResult:
        from clawed.standards import get_standards

        subject = params["subject"]
        grade = params.get("grade", "") or None

        try:
            results = get_standards(subject, grade)
            if not results:
                return ToolResult(text=f"No standards found for {subject}{' grade ' + (grade or '') if grade else ''}.")
            lines = [f"Standards for {subject.title()}{' Grade ' + grade if grade else ''}:"]
            for code, desc, _band in results[:10]:
                lines.append(f"  {code}: {desc}")
            if len(results) > 10:
                lines.append(f"  ... and {len(results) - 10} more")
            return ToolResult(
                text="\n".join(lines),
                data={"standards": [{"code": c, "description": d, "grade_band": b} for c, d, b in results]},
            )
        except Exception as e:
            return ToolResult(text=f"Failed to search standards: {e}")
