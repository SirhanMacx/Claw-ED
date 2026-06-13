"""General Mac file access — read / list / write / edit anywhere the
teacher allows (their home directory), not just the sandboxed output dir.

Policy:
- Paths must resolve inside the teacher's home directory.
- Secrets are denied even for reads (keys, tokens, keychains, .ssh, .env).
- Reads / listings are ``read_only`` (no approval — same as Claude Code).
- Writes / edits are ``write_local`` → approval-gated, "Always allow"
  scoped to the exact file path (per_params).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from clawed.agent_core.context import AgentContext, ToolResult
from clawed.agent_core.tools.base import RISK_READ_ONLY, RISK_WRITE_LOCAL

logger = logging.getLogger(__name__)

_MAX_READ_CHARS = 50_000
_MAX_LIST_ENTRIES = 500

# Never readable or writable, even with approval — secrets and credentials.
# Any path that contains one of these as a path segment (file OR directory)
# is refused, so a whole credential store like ~/.aws is off-limits, not just
# its individual files. Keep this list conservative-but-broad: the cost of a
# false positive (the teacher must use a different path) is far lower than the
# cost of the agent silently reading a cloud or git token into the model.
_DENY_NAMES = frozenset({
    # SSH / GPG key material
    ".ssh", ".gnupg", "id_rsa", "id_ed25519", "id_ecdsa", "id_dsa",
    # Claw-ED's own secrets + the device token
    ".credentials.json", "secrets.json", "api_token",
    # Package / language ecosystem credentials
    ".pypirc", ".netrc", ".npmrc",
    # Environment files (commonly hold API keys)
    ".env",
    # Cloud / container / orchestration credential stores
    ".aws", ".azure", ".gcloud", "gcloud", ".kube", ".docker", ".dockercfg",
    # VCS / database / object-store credentials
    ".git-credentials", ".pgpass", ".my.cnf", ".s3cfg", ".boto",
})
_DENY_SUFFIXES = (".p8", ".p12", ".pem", ".key", ".keychain", ".keychain-db")


def _resolve(path_str: str) -> tuple[Path | None, str]:
    """Resolve a teacher-supplied path. Returns (path, error_message)."""
    if not path_str:
        return None, "ERROR: a 'path' is required."
    try:
        path = Path(path_str).expanduser().resolve()
    except (OSError, RuntimeError) as exc:
        return None, f"ERROR: invalid path: {exc}"

    home = Path.home().resolve()
    if path != home and home not in path.parents:
        return None, (
            f"ERROR: access denied — {path} is outside the teacher's home "
            f"directory. Only paths under {home} are allowed."
        )

    for part in path.parts:
        if part in _DENY_NAMES:
            return None, f"ERROR: access denied — '{part}' holds credentials."
    if path.name in _DENY_NAMES or path.suffix.lower() in _DENY_SUFFIXES:
        return None, f"ERROR: access denied — '{path.name}' looks like a secret."
    return path, ""


class ReadAnyFileTool:
    """Read any (non-secret) file in the teacher's home directory."""

    risk_level = RISK_READ_ONLY

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": (
                    "Read a text file anywhere in the teacher's home directory "
                    "(Desktop, Documents, Downloads, project folders…). "
                    "Returns up to 50k characters. Use list_directory first "
                    "if you don't know the exact path."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Absolute or ~ path."},
                        "offset": {
                            "type": "integer",
                            "description": "Character offset to start from (default 0).",
                        },
                    },
                    "required": ["path"],
                },
            },
        }

    async def execute(
        self, params: dict[str, Any], context: AgentContext,
    ) -> ToolResult:
        path, err = _resolve(str(params.get("path", "")))
        if path is None:
            return ToolResult(text=err)
        if not path.is_file():
            return ToolResult(text=f"ERROR: not a file: {path}")
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return ToolResult(text=f"ERROR: could not read {path}: {exc}")
        offset = max(0, int(params.get("offset") or 0))
        chunk = text[offset : offset + _MAX_READ_CHARS]
        suffix = ""
        if offset + len(chunk) < len(text):
            suffix = (
                f"\n… [truncated — {len(text)} chars total; "
                f"re-call with offset={offset + len(chunk)} for more]"
            )
        return ToolResult(text=f"{path} ({len(text)} chars):\n{chunk}{suffix}")


class ListDirectoryTool:
    """List any directory in the teacher's home."""

    risk_level = RISK_READ_ONLY

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "list_directory",
                "description": (
                    "List files and folders in a directory anywhere in the "
                    "teacher's home (Desktop, Documents, Downloads…). "
                    "Shows names, sizes, and which entries are folders."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Absolute or ~ path."},
                        "glob": {
                            "type": "string",
                            "description": "Optional glob filter, e.g. '*.docx'.",
                        },
                    },
                    "required": ["path"],
                },
            },
        }

    async def execute(
        self, params: dict[str, Any], context: AgentContext,
    ) -> ToolResult:
        path, err = _resolve(str(params.get("path", "")))
        if path is None:
            return ToolResult(text=err)
        if not path.is_dir():
            return ToolResult(text=f"ERROR: not a directory: {path}")
        pattern = str(params.get("glob") or "*")
        try:
            entries = sorted(
                path.glob(pattern),
                key=lambda p: (not p.is_dir(), p.name.lower()),
            )
        except OSError as exc:
            return ToolResult(text=f"ERROR: could not list {path}: {exc}")
        lines: list[str] = []
        for entry in entries[:_MAX_LIST_ENTRIES]:
            if entry.name.startswith(".") and entry.name in _DENY_NAMES:
                continue
            try:
                size = entry.stat().st_size if entry.is_file() else 0
            except OSError:
                size = 0
            kind = "dir " if entry.is_dir() else "file"
            lines.append(f"{kind}  {size:>10}  {entry.name}")
        more = "" if len(entries) <= _MAX_LIST_ENTRIES else f"\n… +{len(entries) - _MAX_LIST_ENTRIES} more"
        return ToolResult(text=f"{path} — {len(entries)} entries:\n" + "\n".join(lines) + more)


class WriteAnyFileTool:
    """Write/create a file anywhere in the teacher's home (approval-gated)."""

    risk_level = RISK_WRITE_LOCAL
    approval_scope = "per_params"

    @staticmethod
    def approval_signature(params: dict[str, Any]) -> str:
        return f"write:{params.get('path', '')}"

    @staticmethod
    def approval_description(params: dict[str, Any]) -> str:
        return f"Write file: {params.get('path', '')}"

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "write_file",
                "description": (
                    "Create or overwrite a text file anywhere in the teacher's "
                    "home directory. The teacher approves each path. Creates "
                    "parent folders as needed."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Absolute or ~ path."},
                        "content": {"type": "string", "description": "Full file content."},
                    },
                    "required": ["path", "content"],
                },
            },
        }

    async def execute(
        self, params: dict[str, Any], context: AgentContext,
    ) -> ToolResult:
        path, err = _resolve(str(params.get("path", "")))
        if path is None:
            return ToolResult(text=err)
        content = str(params.get("content", ""))
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        except OSError as exc:
            return ToolResult(text=f"ERROR: could not write {path}: {exc}")
        return ToolResult(
            text=f"Wrote {len(content)} chars to {path}.",
            files=[path],
            side_effects=[f"wrote file: {path}"],
        )


class EditAnyFileTool:
    """Exact string replacement in a file (approval-gated)."""

    risk_level = RISK_WRITE_LOCAL
    approval_scope = "per_params"

    @staticmethod
    def approval_signature(params: dict[str, Any]) -> str:
        return f"edit:{params.get('path', '')}"

    @staticmethod
    def approval_description(params: dict[str, Any]) -> str:
        return f"Edit file: {params.get('path', '')}"

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "edit_file",
                "description": (
                    "Replace an exact string in a text file in the teacher's "
                    "home directory. old_string must appear exactly once "
                    "(or pass replace_all)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Absolute or ~ path."},
                        "old_string": {"type": "string", "description": "Text to find."},
                        "new_string": {"type": "string", "description": "Replacement text."},
                        "replace_all": {
                            "type": "boolean",
                            "description": "Replace every occurrence (default false).",
                        },
                    },
                    "required": ["path", "old_string", "new_string"],
                },
            },
        }

    async def execute(
        self, params: dict[str, Any], context: AgentContext,
    ) -> ToolResult:
        path, err = _resolve(str(params.get("path", "")))
        if path is None:
            return ToolResult(text=err)
        if not path.is_file():
            return ToolResult(text=f"ERROR: not a file: {path}")
        old = str(params.get("old_string", ""))
        new = str(params.get("new_string", ""))
        if not old:
            return ToolResult(text="ERROR: old_string must be non-empty.")
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            return ToolResult(text=f"ERROR: could not read {path}: {exc}")
        count = text.count(old)
        if count == 0:
            return ToolResult(text=f"ERROR: old_string not found in {path}.")
        if count > 1 and not params.get("replace_all"):
            return ToolResult(
                text=(
                    f"ERROR: old_string appears {count} times in {path}. "
                    "Provide more context or set replace_all=true."
                ),
            )
        updated = text.replace(old, new) if params.get("replace_all") else text.replace(old, new, 1)
        try:
            path.write_text(updated, encoding="utf-8")
        except OSError as exc:
            return ToolResult(text=f"ERROR: could not write {path}: {exc}")
        replaced = count if params.get("replace_all") else 1
        return ToolResult(
            text=f"Replaced {replaced} occurrence(s) in {path}.",
            files=[path],
            side_effects=[f"edited file: {path}"],
        )
