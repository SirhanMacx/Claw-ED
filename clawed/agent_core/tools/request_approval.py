"""Tool: request_approval — creates a PendingApproval via ApprovalManager."""
from __future__ import annotations

from typing import Any

from clawed.agent_core.context import AgentContext, ToolResult


class RequestApprovalTool:
    """Request teacher approval before performing a sensitive action."""

    risk_level = "read_only"

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "request_approval",
                "description": (
                    "Request teacher approval before performing a sensitive action. "
                    "Creates a pending approval that the teacher must accept or reject."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action_description": {
                            "type": "string",
                            "description": "Human-readable description of what will happen",
                        },
                        "action_payload": {
                            "type": "object",
                            "description": "Data needed to execute the action once approved",
                        },
                        "timeout_hours": {
                            "type": "integer",
                            "description": "Hours before the approval expires",
                            "default": 48,
                        },
                    },
                    "required": ["action_description", "action_payload"],
                },
            },
        }

    async def execute(
        self, params: dict[str, Any], context: AgentContext
    ) -> ToolResult:
        from clawed.agent_core.approvals import ApprovalManager

        action_description = params["action_description"]
        action_payload = params.get("action_payload", {})
        timeout_hours = params.get("timeout_hours", 48)

        try:
            mgr = ApprovalManager()
            pa = mgr.create(
                teacher_id=context.teacher_id,
                action_description=action_description,
                action_payload=action_payload,
                agent_state={},
                transport="agent_core",
                timeout_hours=timeout_hours,
            )
            return ToolResult(
                text=f"Approval requested: {action_description} "
                f"(ID: {pa.id}, expires in {timeout_hours}h)",
                data=pa.to_dict(),
                side_effects=[f"Created pending approval {pa.id}"],
            )
        except Exception as e:
            return ToolResult(text=f"Failed to create approval: {e}")
