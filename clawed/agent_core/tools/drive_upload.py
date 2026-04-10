"""Tool: drive_upload — upload a file to Google Drive."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from clawed.agent_core.context import AgentContext, ToolResult


class DriveUploadTool:
    """Upload a local file to Google Drive."""

    risk_level = "network_call"

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "drive_upload",
                "description": ("Upload a local file to Google Drive. Returns the web link to the uploaded file."),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Local path to the file to upload",
                        },
                        "folder_id": {
                            "type": "string",
                            "description": "Drive folder ID to upload into",
                            "default": "root",
                        },
                        "file_name": {
                            "type": "string",
                            "description": ("Name for the file in Drive (defaults to local filename)"),
                        },
                    },
                    "required": ["file_path"],
                },
            },
        }

    async def execute(self, params: dict[str, Any], context: AgentContext) -> ToolResult:
        from clawed.agent_core.drive.client import DriveClient

        file_path = Path(params["file_path"]).expanduser().resolve()
        folder_id = params.get("folder_id", "root")
        file_name = params.get("file_name")

        if not file_path.exists():
            return ToolResult(text=f"Error: file not found: {file_path}")

        client = DriveClient()
        try:
            result = await client.upload_file(
                file_path=file_path,
                folder_id=folder_id,
                file_name=file_name,
            )
            link = result.get("webViewLink", "(no link)")
            name = result.get("name", file_path.name)
            return ToolResult(
                text=f"Uploaded '{name}' to Drive: {link}",
                data=result,
                side_effects=[f"Uploaded {name} to Drive folder {folder_id}"],
            )
        except Exception as e:
            return ToolResult(text=f"Failed to upload file: {e}")
