"""Tool: read_workspace — read any file in the agent's workspace."""
from __future__ import annotations

from typing import Any

from clawed.agent_core.context import AgentContext, ToolResult


class ReadWorkspaceTool:
    """Read any file from the agent's workspace (~/.eduagent/workspace/)."""

    risk_level = "read_only"

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "read_workspace",
                "description": (
                    "Read any file in the agent's workspace directory. "
                    "Use this to read SOUL.md, HEARTBEAT.md, reading_report.md, "
                    "or any other workspace file."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filename": {
                            "type": "string",
                            "description": (
                                "Name of the file to read, e.g. 'SOUL.md', "
                                "'HEARTBEAT.md', 'reading_report.md'"
                            ),
                        },
                    },
                    "required": ["filename"],
                },
            },
        }

    async def execute(
        self, params: dict[str, Any], context: AgentContext
    ) -> ToolResult:
        from clawed.paths import path_is_within, workspace_dir
        workspace = workspace_dir()
        filename = params["filename"]
        target = (workspace / filename).resolve()
        if not path_is_within(target, workspace):
            return ToolResult(text="Access denied: path is outside the workspace.")

        if not target.exists():
            # List what IS in the workspace so the agent knows what's available
            if workspace.exists():
                files = sorted(f.name for f in workspace.iterdir() if f.is_file())
                if files:
                    listing = ", ".join(files)
                    return ToolResult(
                        text=f"File '{filename}' not found. "
                        f"Available workspace files: {listing}"
                    )
            return ToolResult(
                text=f"File '{filename}' not found and workspace is empty."
            )

        try:
            content = target.read_text(encoding="utf-8")
            return ToolResult(text=content)
        except Exception as e:
            return ToolResult(text=f"Failed to read '{filename}': {e}")
