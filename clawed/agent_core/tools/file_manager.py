"""File management tool — Ed can organize and manage lesson files."""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Any

from clawed.agent_core.context import AgentContext, ToolResult

logger = logging.getLogger(__name__)


def _get_output_dir(context: AgentContext) -> Path:
    """Get the teacher's output directory."""
    output_dir = getattr(context.config, "output_dir", "~/clawed_output")
    return Path(output_dir).expanduser()


class FileListTool:
    """List files in the output directory."""

    risk_level = "write_local"

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "list_output_files",
                "description": (
                    "List files in the teacher's output directory. Can filter by subject, unit, date, or file type."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Subdirectory to list (relative to output dir). Default: root",
                        },
                        "pattern": {
                            "type": "string",
                            "description": "Glob pattern to filter (e.g., '*.docx', '**/*.pdf')",
                        },
                    },
                },
            },
        }

    async def execute(self, params: dict[str, Any], context: AgentContext) -> ToolResult:
        output_dir = _get_output_dir(context)
        subpath = params.get("path", "")
        pattern = params.get("pattern", "*")

        target = (output_dir / subpath).resolve() if subpath else output_dir.resolve()
        # Prevent path traversal outside output directory
        if not str(target).startswith(str(output_dir.resolve())):
            return ToolResult(text="ERROR: path outside output directory")
        if not target.exists():
            return ToolResult(text=f"Directory not found: {target}")

        try:
            files = sorted(target.glob(pattern))
            if not files:
                return ToolResult(text=f"No files matching '{pattern}' in {target}")

            lines = [f"Files in {target}:\n"]
            for f in files[:50]:  # Cap at 50
                rel = f.relative_to(output_dir)
                size = f.stat().st_size if f.is_file() else 0
                icon = "📁" if f.is_dir() else "📄"
                size_str = _human_size(size) if f.is_file() else ""
                lines.append(f"  {icon} {rel}  {size_str}")

            if len(files) > 50:
                lines.append(f"  ... and {len(files) - 50} more")

            return ToolResult(text="\n".join(lines))
        except Exception as e:
            return ToolResult(text=f"Error listing files: {e}")


class FileOrganizeTool:
    """Organize files into folders by subject/unit/date."""

    risk_level = "write_local"

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "organize_files",
                "description": (
                    "Organize generated files into folders. Can create folders, "
                    "move files, and set up a clean directory structure."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["create_folder", "move_file", "archive_old"],
                            "description": "What to do",
                        },
                        "source": {
                            "type": "string",
                            "description": "Source file path (relative to output dir)",
                        },
                        "destination": {
                            "type": "string",
                            "description": "Destination path (relative to output dir)",
                        },
                    },
                    "required": ["action"],
                },
            },
        }

    async def execute(self, params: dict[str, Any], context: AgentContext) -> ToolResult:
        output_dir = _get_output_dir(context)
        action = params.get("action", "")
        source = params.get("source", "")
        dest = params.get("destination", "")

        try:
            if action == "create_folder":
                folder = output_dir / (dest or source)
                folder.mkdir(parents=True, exist_ok=True)
                return ToolResult(text=f"Created folder: {folder}")

            elif action == "move_file":
                if not source or not dest:
                    return ToolResult(text="ERROR: both source and destination required for move_file")
                src_path = output_dir / source
                dst_path = output_dir / dest
                if not src_path.exists():
                    return ToolResult(text=f"Source not found: {src_path}")
                dst_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src_path), str(dst_path))
                return ToolResult(text=f"Moved {source} → {dest}")

            elif action == "archive_old":
                # Move files older than 30 days to archive/
                import time

                archive_dir = output_dir / "archive"
                archive_dir.mkdir(exist_ok=True)
                cutoff = time.time() - (30 * 86400)
                moved = 0
                for f in output_dir.iterdir():
                    if f.is_file() and f.stat().st_mtime < cutoff:
                        shutil.move(str(f), str(archive_dir / f.name))
                        moved += 1
                return ToolResult(text=f"Archived {moved} files older than 30 days.")

            else:
                return ToolResult(text=f"Unknown action: {action}")

        except Exception as e:
            return ToolResult(text=f"File operation failed: {e}")


class WorkspaceStatusTool:
    """Check workspace health and organization."""

    risk_level = "write_local"

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "workspace_status",
                "description": (
                    "Check the state of Ed's workspace — memory usage, "
                    "file counts, soul.md health, knowledge base size."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        }

    async def execute(self, params: dict[str, Any], context: AgentContext) -> ToolResult:
        data_dir = os.environ.get("EDUAGENT_DATA_DIR", str(Path.home() / ".eduagent"))
        base = Path(data_dir)

        parts = ["Workspace Status:\n"]

        # Soul.md
        soul = base / "workspace" / "soul.md"
        if soul.exists():
            size = len(soul.read_text(encoding="utf-8"))
            parts.append(f"  SOUL.md: {size} chars")
        else:
            parts.append("  SOUL.md: not created yet")

        # Memory.md
        memory = base / "workspace" / "memory.md"
        if memory.exists():
            size = len(memory.read_text(encoding="utf-8"))
            parts.append(f"  memory.md: {size} chars")

        # KB size
        kb_path = base / "memory" / "curriculum_kb.db"
        if kb_path.exists():
            size = kb_path.stat().st_size
            parts.append(f"  Knowledge base: {_human_size(size)}")

        # Episodes
        ep_path = base / "memory" / "episodes.db"
        if ep_path.exists():
            size = ep_path.stat().st_size
            parts.append(f"  Episodes DB: {_human_size(size)}")

        # Output files
        output_dir = _get_output_dir(context)
        if output_dir.exists():
            file_count = sum(1 for _ in output_dir.rglob("*") if _.is_file())
            parts.append(f"  Output files: {file_count}")

        # Wiki
        wiki_dir = base / "wiki"
        if wiki_dir.exists():
            wiki_count = sum(1 for _ in wiki_dir.glob("*.md"))
            parts.append(f"  Wiki articles: {wiki_count}")

        return ToolResult(text="\n".join(parts))


def _human_size(size: int) -> str:
    """Convert bytes to human-readable size."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.0f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"
