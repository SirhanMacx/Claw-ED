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

    async def execute(
        self, params: dict[str, Any], context: AgentContext
    ) -> ToolResult:
        scenario = params.get("scenario", "").strip()
        if not scenario:
            return ToolResult(text="ERROR: scenario is required")

        subject = params.get("subject", "")
        grade = params.get("grade", "")

        context.notify_progress(f"Building simulation: {scenario}...")

        try:
            from clawed.compile_simulation import compile_simulation
            from clawed.master_content import MasterContent
            from clawed.models import TeacherPersona

            persona = None
            if context.persona:
                try:
                    persona = TeacherPersona(**context.persona)
                except Exception:
                    pass

            # v4.11.2026 fix: ``compile_simulation`` expects a real
            # ``MasterContent`` instance (it calls ``master.title``,
            # ``master.vocabulary``, etc. as object attributes). The
            # previous version passed a plain dict, which crashed with
            # ``AttributeError: 'dict' object has no attribute 'title'``
            # on every invocation. Build a minimal MasterContent with
            # the fields the simulation extractor actually reads.
            subject_val = (
                subject
                or (context.persona or {}).get("subject_area", "")
                or "Science"
            )
            grade_val = grade or (
                (context.persona or {}).get("grade_levels", [""])[0]
                if context.persona else ""
            )
            from clawed.master_content import (
                DoNow,
                GuidedNote,
                InstructionSection,
                StimulusQuestion,
            )
            from clawed.models import DifferentiationNotes

            # MasterContent has several required nested models. For a
            # simulation-only request the agent has no lesson content to
            # attach, so we provide minimal stub values that satisfy the
            # Pydantic schema without being used by compile_simulation.
            master = MasterContent(
                title=scenario[:120],
                subject=subject_val,
                grade_level=str(grade_val or ""),
                topic=scenario[:200],
                objective=(
                    f"Students will explore the dynamics of {scenario} "
                    f"through an interactive simulation."
                ),
                do_now=DoNow(
                    stimulus=f"Warm-up for {scenario}",
                    stimulus_type="text_excerpt",
                    questions=["What do you predict will happen?"],
                    answers=["Responses vary."],
                ),
                direct_instruction=[
                    InstructionSection(
                        heading="Introduction",
                        content=f"Overview of {scenario}.",
                        teacher_script="Introduce the simulation context.",
                        key_points=["Key concept 1"],
                    ),
                ],
                guided_notes=[
                    GuidedNote(
                        prompt="The simulation models ______.",
                        answer=scenario,
                        section_ref="Introduction",
                    ),
                ],
                exit_ticket=[
                    StimulusQuestion(
                        stimulus=f"Observed behavior of {scenario}.",
                        stimulus_type="text_excerpt",
                        question="What variables mattered most?",
                        answer="Responses vary.",
                    ),
                ],
                differentiation=DifferentiationNotes(),
            )

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
