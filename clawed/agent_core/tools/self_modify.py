"""Self-modification tool — Ed can change his own config and workspace files."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, ClassVar

from clawed.agent_core.context import AgentContext, ToolResult
from clawed.paths import path_is_within

logger = logging.getLogger(__name__)


class SelfModifyConfigTool:
    """Ed can modify his own configuration settings."""

    risk_level = "write_local"  # Requires approval unless auto-approve is on

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "modify_config",
                "description": (
                    "Modify Ed's own configuration. Can change: max_agent_iterations "
                    "(how many tool steps per task), output_dir, export_format, "
                    "image_fetch_timeout, agent_name, and any other config field. "
                    "Use when you need more iterations for complex tasks, want to "
                    "change output settings, or need to adjust your own behavior."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "key": {
                            "type": "string",
                            "description": (
                                "Config key to change (e.g., "
                                "'max_agent_iterations', 'output_dir')"
                            ),
                        },
                        "value": {
                            "type": "string",
                            "description": "New value (will be auto-converted to correct type)",
                        },
                    },
                    "required": ["key", "value"],
                },
            },
        }

    async def execute(
        self, params: dict[str, Any], context: AgentContext
    ) -> ToolResult:
        key = params.get("key", "").strip()
        value = params.get("value", "").strip()

        if not key or not value:
            return ToolResult(text="ERROR: key and value are required")

        # Safety: block dangerous fields
        blocked = {"provider", "anthropic_model", "openai_model", "google_model",
                    "ollama_model", "openrouter_model", "telegram_bot_token",
                    "ollama_api_key", "dashboard_password"}
        if key in blocked:
            return ToolResult(text=f"Cannot modify '{key}' — use switch_model or configure_profile for auth settings.")

        try:
            from clawed.models import AppConfig
            config = AppConfig.load()

            if not hasattr(config, key):
                return ToolResult(text=f"Unknown config key: '{key}'. Check available fields.")

            # Auto-convert type
            current = getattr(config, key)
            new_val: Any
            if isinstance(current, bool):
                new_val = value.lower() in ("true", "1", "yes")
            elif isinstance(current, int):
                new_val = int(value)
            elif isinstance(current, float):
                new_val = float(value)
            else:
                new_val = value

            old_val = current
            setattr(config, key, new_val)
            config.save()

            # Also update the running context if applicable
            if key == "max_agent_iterations" and hasattr(context.config, key):
                setattr(context.config, key, new_val)

            logger.info("Self-modify: %s changed from %s to %s", key, old_val, new_val)
            return ToolResult(text=f"Updated {key}: {old_val} → {new_val}")

        except Exception as e:
            return ToolResult(text=f"Config modification failed: {e}")


class WriteFileTool:
    """Ed can create and modify files in his workspace and output directory."""

    risk_level = "write_local"  # Requires approval unless auto-approve is on

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "write_file",
                "description": (
                    "Write content to a file in Ed's workspace or output directory. "
                    "Can create new files or overwrite existing ones. "
                    "Use for: updating soul.md, writing notes, creating templates, "
                    "saving research, generating custom documents."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": (
                                "File path relative to workspace or output. "
                                "E.g. 'workspace/soul.md', 'workspace/notes/x.md'"
                            ),
                        },
                        "content": {
                            "type": "string",
                            "description": "Content to write to the file",
                        },
                        "append": {
                            "type": "boolean",
                            "description": "If true, append to existing file instead of overwriting. Default: false.",
                        },
                    },
                    "required": ["path", "content"],
                },
            },
        }

    async def execute(
        self, params: dict[str, Any], context: AgentContext
    ) -> ToolResult:
        rel_path = params.get("path", "").strip()
        content = params.get("content", "")
        append = params.get("append", False)

        if not rel_path:
            return ToolResult(text="ERROR: path is required")

        # Resolve to absolute path within allowed directories
        data_dir = Path(os.environ.get(
            "EDUAGENT_DATA_DIR", str(Path.home() / ".eduagent")
        ))
        output_dir = Path(getattr(context.config, "output_dir", "~/clawed_output")).expanduser()

        # Security: only allow writes to workspace subdirs or output (P0-5 audit fix)
        # DENY writes to sensitive files — even within data_dir
        denied_files = {
            "config.json", "secrets.json", "api_token", "schedule.json",
            "bot.lock", "bot_state.db", "approvals.db", "state.db",
            "classroom_profile.json", "drive_token.json",
        }
        denied_dirs = {"memory", "corpus", "cache"}

        basename = Path(rel_path).name.lower()
        if basename in denied_files:
            return ToolResult(
                text=f"BLOCKED: cannot write to '{basename}' — "
                     f"this is a protected system file."
            )

        first_dir = rel_path.split("/")[0] if "/" in rel_path else ""
        if first_dir in denied_dirs:
            return ToolResult(
                text=f"BLOCKED: cannot write to '{first_dir}/' — "
                     f"this is a protected system directory."
            )

        if rel_path.startswith("workspace/") or rel_path == "workspace":
            full_path = data_dir / rel_path
        elif rel_path.startswith("output/"):
            full_path = output_dir / rel_path[7:]
        else:
            # Default to workspace for safety
            full_path = data_dir / "workspace" / rel_path

        # Block path traversal
        try:
            full_path = full_path.resolve()
            if not (
                path_is_within(full_path, data_dir)
                or path_is_within(full_path, output_dir)
            ):
                return ToolResult(text="ERROR: path must be within workspace or output directory")
        except Exception:
            logger.debug("operation_failed", exc_info=True)
            return ToolResult(text="ERROR: invalid path")

        try:
            full_path.parent.mkdir(parents=True, exist_ok=True)
            mode = "a" if append else "w"
            with open(full_path, mode, encoding="utf-8") as f:
                if append and content and not content.startswith("\n"):
                    f.write("\n")
                f.write(content)

            action = "Appended to" if append else "Wrote"
            logger.info("Self-modify: %s %s (%d chars)", action, full_path, len(content))
            return ToolResult(text=f"{action} {full_path} ({len(content)} chars)")

        except Exception as e:
            return ToolResult(text=f"File write failed: {e}")


class ReadFileTool:
    """Ed can read any file in his workspace or output directory."""

    risk_level = "read_only"

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": (
                    "Read the contents of a file from Ed's workspace or output directory. "
                    "Use for: reading soul.md, checking notes, reviewing generated content, "
                    "reading teacher's curriculum files."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "File path relative to workspace or output dir",
                        },
                    },
                    "required": ["path"],
                },
            },
        }

    # Sensitive filenames that must never be read through this tool,
    # regardless of containment. Mirrors the block-list pattern in
    # WriteFileTool and catches cases like "secrets.json" being supplied
    # as a workspace-relative path.
    _DENIED_FILENAMES: ClassVar[frozenset[str]] = frozenset({
        "secrets.json",
        "api_token",
        ".env",
        ".env.local",
        "credentials.json",
        "oauth_token.json",
        "bot_token.json",
    })

    async def execute(
        self, params: dict[str, Any], context: AgentContext
    ) -> ToolResult:
        rel_path = params.get("path", "").strip()
        if not rel_path:
            return ToolResult(text="ERROR: path is required")

        data_dir = Path(os.environ.get(
            "EDUAGENT_DATA_DIR", str(Path.home() / ".eduagent")
        ))
        output_dir = Path(getattr(context.config, "output_dir", "~/clawed_output")).expanduser()

        # v4.11.2026 security fix: block sensitive filenames early, before
        # any path resolution. Catches "secrets.json", "api_token", etc.
        # regardless of which workspace prefix they would otherwise land in.
        base_name = Path(rel_path).name.lower()
        if base_name in self._DENIED_FILENAMES:
            return ToolResult(
                text=f"ERROR: access denied for sensitive file: {base_name}"
            )

        # Canonical allowed roots. Any read must resolve inside one of these.
        try:
            data_root = data_dir.resolve()
            output_root = output_dir.resolve()
        except Exception:
            logger.debug("operation_failed", exc_info=True)
            return ToolResult(text="ERROR: could not resolve data/output directories")

        # Try workspace first, then output
        candidates = [
            data_dir / rel_path,
            output_dir / rel_path,
            data_dir / "workspace" / rel_path,
        ]

        for full_path in candidates:
            try:
                full_path = full_path.resolve()
                # v4.11.2026 security fix: enforce containment. Without
                # this, an attacker-supplied absolute path or a relative
                # path containing "../" sequences could read arbitrary
                # files on disk. WriteFileTool had this check; ReadFileTool
                # did not.
                if not (
                    path_is_within(full_path, data_root)
                    or path_is_within(full_path, output_root)
                ):
                    continue
                if full_path.exists() and full_path.is_file():
                    content = full_path.read_text(encoding="utf-8")
                    return ToolResult(
                        text=f"Contents of {full_path}:\n\n{content[:8000]}",
                        data={"path": str(full_path), "size": len(content)},
                    )
            except (FileNotFoundError, OSError):
                continue

        return ToolResult(text=f"File not found or out of bounds: {rel_path}")
