"""Tool: drive_create_slides — create a Google Slides presentation."""

from __future__ import annotations

from typing import Any

from clawed.agent_core.context import AgentContext, ToolResult


class DriveCreateSlidesTool:
    """Create a native Google Slides presentation in Drive."""

    risk_level = "network_call"

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "drive_create_slides",
                "description": (
                    "Create a native Google Slides presentation in Drive. Returns the web link to the new presentation."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "Title of the presentation",
                        },
                        "content": {
                            "type": "string",
                            "description": ("Outline or content for the slides (used as initial description)"),
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

    async def execute(self, params: dict[str, Any], context: AgentContext) -> ToolResult:
        from clawed.agent_core.drive.client import DriveClient

        title = params["title"]
        content = params.get("content", "")
        folder_id = params.get("folder_id", "root")

        client = DriveClient()
        try:
            result = await client.create_slides(
                title=title,
                content=content,
                folder_id=folder_id,
            )
            link = result.get("webViewLink", "(no link)")
            name = result.get("name", title)
            return ToolResult(
                text=f"Created presentation '{name}': {link}",
                data=result,
                side_effects=[f"Created Google Slides '{name}' in folder {folder_id}"],
            )
        except Exception as e:
            return ToolResult(text=f"Failed to create slides: {e}")
