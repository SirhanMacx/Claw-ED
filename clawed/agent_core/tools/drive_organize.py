"""Tool: drive_organize — create a folder in Google Drive."""
from __future__ import annotations

from typing import Any

from clawed.agent_core.context import AgentContext, ToolResult


class DriveOrganizeTool:
    """Create a folder in Google Drive for organizing files."""

    risk_level = "network_call"

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "drive_organize",
                "description": (
                    "Create a new folder in Google Drive for organizing files. "
                    "Returns the folder ID."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "folder_name": {
                            "type": "string",
                            "description": "Name for the new folder",
                        },
                        "parent_id": {
                            "type": "string",
                            "description": "Parent folder ID",
                            "default": "root",
                        },
                    },
                    "required": ["folder_name"],
                },
            },
        }

    async def execute(
        self, params: dict[str, Any], context: AgentContext
    ) -> ToolResult:
        from clawed.agent_core.drive.client import DriveClient

        folder_name = params["folder_name"]
        parent_id = params.get("parent_id", "root")

        client = DriveClient()
        try:
            result = await client.create_folder(
                name=folder_name,
                parent_id=parent_id,
            )
            folder_id = result.get("id", "?")
            name = result.get("name", folder_name)
            return ToolResult(
                text=f"Created folder '{name}' (id={folder_id})",
                data=result,
                side_effects=[
                    f"Created Drive folder '{name}' under {parent_id}"
                ],
            )
        except Exception as e:
            return ToolResult(text=f"Failed to create folder: {e}")
