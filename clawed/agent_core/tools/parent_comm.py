"""Tool: parent_comm — wraps clawed.parent_comm.generate_parent_comm."""
from __future__ import annotations

from typing import Any

from clawed.agent_core.context import AgentContext, ToolResult


class ParentCommTool:
    """Generate a professional parent communication email."""

    risk_level = "read_only"

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "parent_comm",
                "description": (
                    "Generate a professional parent communication email. "
                    "Supports progress updates, behavior concerns, positive notes, "
                    "and other communication types."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "comm_type": {
                            "type": "string",
                            "description": (
                                "Type of communication: 'progress_update', "
                                "'behavior_concern', 'positive_note', "
                                "'upcoming_unit', 'permission_request', "
                                "'general_update'"
                            ),
                            "enum": [
                                "progress_update",
                                "behavior_concern",
                                "positive_note",
                                "upcoming_unit",
                                "permission_request",
                                "general_update",
                            ],
                        },
                        "student_description": {
                            "type": "string",
                            "description": (
                                "Brief description of the student situation "
                                "(no real names)"
                            ),
                        },
                        "class_context": {
                            "type": "string",
                            "description": "Context about the class and subject",
                        },
                        "tone": {
                            "type": "string",
                            "description": "Desired tone of the email",
                            "default": "professional and warm",
                        },
                        "additional_notes": {
                            "type": "string",
                            "description": "Any additional context or notes",
                            "default": "",
                        },
                    },
                    "required": ["comm_type", "student_description", "class_context"],
                },
            },
        }

    async def execute(
        self, params: dict[str, Any], context: AgentContext
    ) -> ToolResult:
        from clawed.llm import LLMClient
        from clawed.parent_comm import (
            CommType,
            ParentCommRequest,
            generate_parent_comm,
            parent_comm_to_text,
        )

        try:
            request = ParentCommRequest(
                comm_type=CommType(params["comm_type"]),
                student_description=params["student_description"],
                class_context=params["class_context"],
                tone=params.get("tone", "professional and warm"),
                additional_notes=params.get("additional_notes", ""),
            )
            llm = LLMClient(context.config)
            comm = await generate_parent_comm(request, llm)
            text = parent_comm_to_text(comm)
            return ToolResult(
                text=f"Generated parent email:\n\n{text}",
                data={
                    "subject_line": comm.subject_line,
                    "email_body": comm.email_body,
                    "follow_up_suggestions": comm.follow_up_suggestions,
                },
                side_effects=["Generated parent communication"],
            )
        except Exception as e:
            return ToolResult(text=f"Failed to generate parent communication: {e}")
