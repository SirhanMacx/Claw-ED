"""Simulation generation tool — Ed can create interactive scenario simulations."""

from __future__ import annotations

import logging
from typing import Any

from clawed.agent_core.context import AgentContext, ToolResult

logger = logging.getLogger(__name__)


class GenerateSimulationTool:
    """Create an interactive HTML simulation for classroom use."""

    risk_level = "read_only"

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "generate_simulation",
                "description": (
                    "Create an interactive simulation where students make decisions "
                    "and see consequences. Great for history (constitutional convention, "
                    "treaty negotiations), science (ecosystem management, lab experiments), "
                    "and economics (market scenarios, budgeting)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "scenario": {
                            "type": "string",
                            "description": "The scenario to simulate (e.g., 'Constitutional Convention debates')",
                        },
                        "subject": {
                            "type": "string",
                            "description": "School subject",
                        },
                        "grade": {
                            "type": "string",
                            "description": "Grade level",
                        },
                    },
                    "required": ["scenario"],
                },
            },
        }

    async def execute(self, params: dict[str, Any], context: AgentContext) -> ToolResult:
        scenario = params.get("scenario", "").strip()
        if not scenario:
            return ToolResult(text="ERROR: scenario is required")

        subject = params.get("subject", "")
        grade = params.get("grade", "")

        context.notify_progress(f"Building simulation: {scenario}...")

        try:
            from clawed.compile_simulation import compile_simulation
            from clawed.models import TeacherPersona

            persona = None
            if context.persona:
                try:
                    persona = TeacherPersona(**context.persona)
                except Exception:
                    pass

            master = {
                "topic": scenario,
                "subject": subject or (context.persona or {}).get("subject_area", ""),
                "grade_level": grade
                or ((context.persona or {}).get("grade_levels", [""])[0] if context.persona else ""),
            }

            result_path = await compile_simulation(
                master=master,
                persona=persona,
                output_dir=None,
            )

            if result_path and result_path.exists():
                return ToolResult(
                    text=f"Created simulation '{scenario}': {result_path}",
                    files=[result_path],
                )
            return ToolResult(text="Simulation generation completed but no file was produced.")

        except Exception as e:
            logger.error("Simulation generation failed: %s", e)
            return ToolResult(text=f"Simulation generation failed: {e}")
