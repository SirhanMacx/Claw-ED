"""Tool: gap_analysis — wraps CurriculumMapper.identify_curriculum_gaps."""
from __future__ import annotations

import contextlib
import json
from typing import Any

from clawed.agent_core.context import AgentContext, ToolResult


class GapAnalysisTool:
    """Identify curriculum gaps by comparing materials against standards."""

    risk_level = "read_only"

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "gap_analysis",
                "description": (
                    "Analyze existing teaching materials against curriculum "
                    "standards to identify gaps and missing coverage."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "existing_materials": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": (
                                "Summaries or titles of existing curriculum materials"
                            ),
                        },
                        "standards": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": (
                                "Standards codes/descriptions to check coverage against"
                            ),
                        },
                    },
                    "required": ["existing_materials", "standards"],
                },
            },
        }

    async def execute(
        self, params: dict[str, Any], context: AgentContext
    ) -> ToolResult:
        from clawed.curriculum_map import CurriculumMapper
        from clawed.models import TeacherPersona

        existing_materials = params["existing_materials"]
        standards = params["standards"]

        persona = TeacherPersona()
        if context.persona:
            with contextlib.suppress(Exception):
                persona = TeacherPersona(**context.persona)

        try:
            mapper = CurriculumMapper(context.config)
            gaps = await mapper.identify_curriculum_gaps(
                existing_materials=existing_materials,
                standards=standards,
                persona=persona,
            )
            gaps_data = [g.model_dump() for g in gaps]
            if not gaps:
                return ToolResult(
                    text="No curriculum gaps identified. All standards appear covered.",
                    data={"gaps": []},
                )
            lines = [f"Found {len(gaps)} curriculum gap(s):"]
            for gap in gaps[:5]:
                lines.append(f"  - {gap.standard}: {gap.description}")
            if len(gaps) > 5:
                lines.append(f"  ... and {len(gaps) - 5} more")
            return ToolResult(
                text="\n".join(lines) + "\n\n"
                f"{json.dumps(gaps_data, indent=2)[:2000]}",
                data={"gaps": gaps_data},
                side_effects=["Performed curriculum gap analysis"],
            )
        except Exception as e:
            return ToolResult(text=f"Failed to perform gap analysis: {e}")
