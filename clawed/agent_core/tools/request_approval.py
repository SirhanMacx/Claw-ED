"""Tool: request_approval — creates a PendingApproval via ApprovalManager."""
from __future__ import annotations

import json
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
                            "description": "Exact action: tool_name and params. Approval permits this action once.",
                            "properties": {
                                "tool_name": {"type": "string"},
                                "params": {"type": "object"},
                            },
                            "required": ["tool_name", "params"],
                            "additionalProperties": False,
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
        if not action_payload.get("tool_name") or not isinstance(action_payload.get("params"), dict):
            return ToolResult(text="Approval needs a tool_name and the exact params object.")

        try:
            mgr = ApprovalManager()
            pa = mgr.create(
                teacher_id=context.approval_owner or context.teacher_id,
                action_description=action_description,
                action_payload=action_payload,
                agent_state={},
                transport=context.transport,
                timeout_hours=timeout_hours,
            )
            return ToolResult(
                text=(f"Approval requested: {action_description}\n"
                      f"{json.dumps(action_payload, indent=2, ensure_ascii=False)}\n"
                      f"Approve once: /approve {pa.id}\nReject: /reject {pa.id}\n"
                      f"Expires in {timeout_hours}h."),
                data=pa.to_dict(),
                side_effects=[f"Created pending approval {pa.id}"],
                approval_id=pa.id,
            )
        except Exception as e:
            return ToolResult(text=f"Failed to create approval: {e}")
