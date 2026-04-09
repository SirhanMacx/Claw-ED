"""Tool: drive_create_doc — create a Google Doc."""
from __future__ import annotations

from typing import Any

from clawed.agent_core.context import AgentContext, ToolResult


class DriveCreateDocTool:
    """Create a native Google Doc in Drive."""

    risk_level = "network_call"

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "drive_create_doc",
                "description": (
                    "Create a native Google Doc in Drive. "
                    "Returns the web link to the new document."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "Title of the document",
                        },
                        "content": {
                            "type": "string",
                            "description": (
                                "Content or outline for the document"
                            ),
                        },
                        "folder_id": {
                            "type": "string",
                            "description": "Drive folder ID to create in",
                            "default": "root",
                        },
                    },
                    "required": ["title", "content"],
                },
            },
        }

    async def execute(
        self, params: dict[str, Any], context: AgentContext
    ) -> ToolResult:
        from clawed.agent_core.drive.client import DriveClient

        title = params["title"]
        content = params.get("content", "")
        folder_id = params.get("folder_id", "root")

        client = DriveClient()
        try:
            result = await client.create_doc(
                title=title,
                content=content,
                folder_id=folder_id,
            )
            link = result.get("webViewLink", "(no link)")
            name = result.get("name", title)
            return ToolResult(
                text=f"Created document '{name}': {link}",
                data=result,
                side_effects=[f"Created Google Doc '{name}' in folder {folder_id}"],
            )
        except Exception as e:
            return ToolResult(text=f"Failed to create document: {e}")
