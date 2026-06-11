"""Shell command execution — the general "act on my Mac" tool.

This is what makes Claw-ED a real desktop agent (Claude Code / Codex
class) rather than an education web app. Every invocation is gated:

- risk_level = command_exec → ALWAYS requires teacher approval; the
  CLAWED_AUTO_APPROVE escape hatch does NOT apply.
- approval_scope = per_params → an "Always allow" grant is scoped to the
  EXACT command string; a different command re-prompts.
- Output is streamed to the UI via ``command_output`` events and
  truncated in the transcript so huge outputs can't blow up the loop.

Machine rule (see docs/product/HANDOFF.md): ``security`` / ``codesign``
invocations are refused — on this Mac any keychain touch pops GUI
password prompts at the teacher. Opt out with CLAWED_ALLOW_KEYCHAIN_CMDS=1.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import shlex
from pathlib import Path
from typing import Any

from clawed.agent_core.context import AgentContext, ToolResult
from clawed.agent_core.tools.base import RISK_COMMAND_EXEC

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 60
_MAX_TIMEOUT = 600
_MAX_OUTPUT_CHARS = 20_000
_STREAM_CHUNK_CHARS = 800

# Commands that touch the macOS keychain — refused by default on this
# machine because the locked login keychain turns every call into a GUI
# password prompt at the teacher (see HANDOFF.md, "the keychain rule").
_KEYCHAIN_BINARIES = frozenset({"security", "codesign"})


def _keychain_blocked(command: str) -> bool:
    if os.environ.get("CLAWED_ALLOW_KEYCHAIN_CMDS", "").lower() in ("1", "true", "yes"):
        return False
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()
    return any(Path(tok).name in _KEYCHAIN_BINARIES for tok in tokens)


class RunCommandTool:
    """Run a shell command on the teacher's Mac (approval-gated)."""

    risk_level = RISK_COMMAND_EXEC
    approval_scope = "per_params"

    @staticmethod
    def approval_signature(params: dict[str, Any]) -> str:
        """Scope 'Always allow' to the exact command (whitespace-normalized)."""
        command = str(params.get("command", ""))
        return re.sub(r"\s+", " ", command).strip()

    @staticmethod
    def approval_description(params: dict[str, Any]) -> str:
        command = str(params.get("command", ""))[:300]
        return f"Run command: {command}"

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "run_command",
                "description": (
                    "Execute a shell command on the teacher's Mac and return "
                    "its output. Use for anything the other tools don't cover: "
                    "moving files, inspecting folders, converting documents, "
                    "git, installed CLIs, opening apps. The teacher approves "
                    "every command before it runs. Prefer short, single-purpose "
                    "commands; output is truncated past 20k characters."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "The shell command to run (zsh -c).",
                        },
                        "cwd": {
                            "type": "string",
                            "description": (
                                "Working directory (default: the teacher's home)."
                            ),
                        },
                        "timeout_seconds": {
                            "type": "integer",
                            "description": (
                                f"Max seconds to wait (default {_DEFAULT_TIMEOUT}, "
                                f"cap {_MAX_TIMEOUT})."
                            ),
                        },
                    },
                    "required": ["command"],
                },
            },
        }

    async def execute(
        self, params: dict[str, Any], context: AgentContext,
    ) -> ToolResult:
        command = str(params.get("command", "")).strip()
        if not command:
            return ToolResult(text="ERROR: run_command needs a non-empty 'command'.")

        if _keychain_blocked(command):
            return ToolResult(
                text=(
                    "BLOCKED: this command touches the macOS keychain "
                    "(`security`/`codesign`), which is locked on this Mac and "
                    "pops password prompts at the teacher. Use a different "
                    "approach, or the teacher can set CLAWED_ALLOW_KEYCHAIN_CMDS=1."
                ),
            )

        cwd = Path(str(params.get("cwd") or Path.home())).expanduser()
        if not cwd.is_dir():
            return ToolResult(text=f"ERROR: cwd does not exist: {cwd}")

        try:
            timeout = int(params.get("timeout_seconds") or _DEFAULT_TIMEOUT)
        except (TypeError, ValueError):
            timeout = _DEFAULT_TIMEOUT
        timeout = max(1, min(timeout, _MAX_TIMEOUT))

        env = dict(os.environ)
        # The agent must never touch the keychain (HANDOFF.md).
        env["PYTHON_KEYRING_BACKEND"] = "keyring.backends.null.Keyring"

        logger.info("run_command: %s (cwd=%s, timeout=%ss)", command[:200], cwd, timeout)

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                cwd=str(cwd),
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
        except Exception as exc:
            return ToolResult(text=f"ERROR: failed to start command: {exc}")

        chunks: list[str] = []
        total = 0
        truncated = False

        async def _drain() -> None:
            nonlocal total, truncated
            assert proc.stdout is not None
            buffer = ""
            while True:
                data = await proc.stdout.read(4096)
                if not data:
                    break
                text = data.decode("utf-8", errors="replace")
                if total < _MAX_OUTPUT_CHARS:
                    keep = text[: _MAX_OUTPUT_CHARS - total]
                    chunks.append(keep)
                    total += len(keep)
                    if len(keep) < len(text):
                        truncated = True
                else:
                    truncated = True
                buffer += text
                while len(buffer) >= _STREAM_CHUNK_CHARS:
                    context.emit_event("command_output", {
                        "chunk": buffer[:_STREAM_CHUNK_CHARS],
                    })
                    buffer = buffer[_STREAM_CHUNK_CHARS:]
            if buffer:
                context.emit_event("command_output", {"chunk": buffer})

        try:
            await asyncio.wait_for(_drain(), timeout=timeout)
            exit_code = await asyncio.wait_for(proc.wait(), timeout=10)
        except TimeoutError:
            proc.kill()
            output = "".join(chunks)
            return ToolResult(
                text=(
                    f"ERROR: command timed out after {timeout}s and was killed.\n"
                    f"Partial output:\n{output[-4000:]}"
                ),
            )

        output = "".join(chunks).rstrip()
        if truncated:
            output += "\n… [output truncated at 20k characters]"

        status = "succeeded" if exit_code == 0 else f"failed (exit {exit_code})"
        body = output if output else "(no output)"
        text = f"Command {status}.\n{body}"
        if exit_code != 0:
            text = (
                f"ERROR: command {status}. Do not claim success.\n{body}"
            )
        return ToolResult(
            text=text,
            data={"exit_code": exit_code, "truncated": truncated},
            side_effects=[f"ran command: {command[:120]}"],
        )
