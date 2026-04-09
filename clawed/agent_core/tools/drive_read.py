"""Tool: drive_read — read file metadata and content from Google Drive."""
from __future__ import annotations

from typing import Any

from clawed.agent_core.context import AgentContext, ToolResult


class DriveReadTool:
    """Read file metadata and content from Google Drive."""

    risk_level = "network_call"

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "drive_read",
                "description": (
                    "Read a file's metadata and content from Google Drive. "
                    "For Google Docs/Sheets/Slides, exports as plain text."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_id": {
                            "type": "string",
                            "description": "The Drive file ID to read",
                        },
                    },
                    "required": ["file_id"],
                },
            },
        }

    async def execute(
        self, params: dict[str, Any], context: AgentContext
    ) -> ToolResult:
        from clawed.agent_core.drive.client import DriveClient

        file_id = params["file_id"]

        client = DriveClient()
        try:
            result = await client.read_file(file_id=file_id)
            name = result.get("name", "unknown")
            mime = result.get("mimeType", "unknown")
            modified = result.get("modifiedTime", "unknown")
            content = result.get("content", "")

            lines = [
                f"File: {name}",
                f"Type: {mime}",
                f"Modified: {modified}",
                f"ID: {file_id}",
            ]
            if content:
                lines.append(f"\nContent:\n{content}")
            else:
                lines.append("\n(No text content available)")

            return ToolResult(
                text="\n".join(lines),
                data=result,
            )
        except Exception as e:
            return ToolResult(text=f"Failed to read file: {e}")
