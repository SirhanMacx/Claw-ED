"""Tool: drive_list — list files in a Google Drive folder."""

from __future__ import annotations

from typing import Any

from clawed.agent_core.context import AgentContext, ToolResult


class DriveListTool:
    """List files in a Google Drive folder."""

    risk_level = "network_call"

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "drive_list",
                "description": (
                    "List files in a Google Drive folder. Returns file names, IDs, and modification times."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "folder_id": {
                            "type": "string",
                            "description": "Drive folder ID to list",
                            "default": "root",
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of files to return",
                            "default": 20,
                        },
                    },
                    "required": [],
                },
            },
        }

    async def execute(self, params: dict[str, Any], context: AgentContext) -> ToolResult:
        from clawed.agent_core.drive.client import DriveClient

        folder_id = params.get("folder_id", "root")
        max_results = params.get("max_results", 20)

        client = DriveClient()
        try:
            files = await client.list_files(
                folder_id=folder_id,
                max_results=max_results,
            )
            if not files:
                return ToolResult(
                    text=f"No files found in folder '{folder_id}'.",
                    data={"files": [], "count": 0},
                )
            lines = [f"Found {len(files)} file(s) in folder '{folder_id}':"]
            for f in files:
                name = f.get("name", "?")
                fid = f.get("id", "?")
                mime = f.get("mimeType", "?")
                modified = f.get("modifiedTime", "?")
                lines.append(f"  - {name} ({mime}) [id={fid}, modified={modified}]")
            return ToolResult(
                text="\n".join(lines),
                data={"files": files, "count": len(files)},
            )
        except Exception as e:
            return ToolResult(text=f"Failed to list files: {e}")
