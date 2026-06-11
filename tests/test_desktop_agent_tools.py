"""Tests for the desktop-agent additions: run_command, mac_files,
the interactive approval broker, and per-params approval scoping."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from clawed.agent_core.approval_broker import ApprovalBroker, ApprovalDecision
from clawed.agent_core.approvals import ApprovalManager
from clawed.agent_core.context import AgentContext
from clawed.agent_core.tools.base import ToolRegistry
from clawed.agent_core.tools.mac_files import (
    EditAnyFileTool,
    ListDirectoryTool,
    ReadAnyFileTool,
    WriteAnyFileTool,
)
from clawed.agent_core.tools.run_command import RunCommandTool


def _context(**overrides: Any) -> AgentContext:
    defaults: dict[str, Any] = dict(
        teacher_id="t-test",
        config=None,  # tools under test never touch config
        teacher_profile={},
        persona=None,
        session_history=[],
        improvement_context="",
    )
    defaults.update(overrides)
    return AgentContext(**defaults)


# ── run_command ──────────────────────────────────────────────────────


async def test_run_command_executes_and_captures_output() -> None:
    tool = RunCommandTool()
    result = await tool.execute({"command": "echo hello-clawed"}, _context())
    assert "hello-clawed" in result.text
    assert result.data["exit_code"] == 0


async def test_run_command_reports_failure_exit_code() -> None:
    tool = RunCommandTool()
    result = await tool.execute({"command": "exit 3"}, _context())
    assert result.text.startswith("ERROR:")
    assert result.data["exit_code"] == 3


async def test_run_command_times_out() -> None:
    tool = RunCommandTool()
    result = await tool.execute(
        {"command": "sleep 5", "timeout_seconds": 1}, _context(),
    )
    assert "timed out" in result.text


async def test_run_command_blocks_keychain_commands() -> None:
    tool = RunCommandTool()
    result = await tool.execute(
        {"command": "security show-keychain-info"}, _context(),
    )
    assert result.text.startswith("BLOCKED")


async def test_run_command_streams_output_events() -> None:
    events: list[tuple[str, dict[str, Any]]] = []
    ctx = _context(event_callback=lambda t, d: events.append((t, d)))
    tool = RunCommandTool()
    await tool.execute({"command": "echo streamed-bytes"}, ctx)
    chunks = [d["chunk"] for t, d in events if t == "command_output"]
    assert any("streamed-bytes" in c for c in chunks)


def test_run_command_signature_normalizes_whitespace() -> None:
    sig_a = RunCommandTool.approval_signature({"command": "ls   -la\n ~"})
    sig_b = RunCommandTool.approval_signature({"command": "ls -la ~"})
    assert sig_a == sig_b


# ── approval gating through the registry ────────────────────────────


def _registry_with(tool: Any) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(tool)
    return registry


async def test_registry_blocks_run_command_without_approval(tmp_path: Path) -> None:
    mgr = ApprovalManager(base_dir=tmp_path)
    registry = _registry_with(RunCommandTool())
    import clawed.agent_core.tools.base as base_mod

    orig = base_mod.ToolRegistry._check_approval
    result = await registry.execute(
        "run_command", {"command": "echo should-not-run"}, _context(),
    )
    assert base_mod.ToolRegistry._check_approval is orig
    assert result.text.startswith("BLOCKED")
    assert mgr.pending_for_teacher("t-test") == []


async def test_interactive_approval_allows_once() -> None:
    events: list[tuple[str, dict[str, Any]]] = []
    registry = _registry_with(RunCommandTool())

    async def resolve_when_requested() -> None:
        while not events:
            await asyncio.sleep(0.01)
        approval_id = events[0][1]["approval_id"]
        ApprovalBroker.instance().resolve(
            approval_id, ApprovalDecision(approved=True, always=False),
        )

    task = asyncio.create_task(resolve_when_requested())
    result = await registry.execute(
        "run_command",
        {"command": "echo approved-once"},
        _context(event_callback=lambda t, d: events.append((t, d))),
    )
    await task
    assert "approved-once" in result.text
    assert events[0][0] == "approval_required"


async def test_standing_approval_is_scoped_to_exact_command(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    mgr = ApprovalManager(base_dir=tmp_path)
    mgr.create(
        teacher_id="t-test",
        action_description="Run approved command",
        action_payload={
            "tool_name": "run_command",
            "params_signature": RunCommandTool.approval_signature({"command": "echo allowed"}),
        },
        agent_state={},
        transport="app",
    )
    approval = next(iter(tmp_path.glob("*.json"))).stem
    mgr.approve(approval)

    # base.py imports ApprovalManager lazily from the approvals module,
    # so patch it at the source.
    monkeypatch.setattr(
        "clawed.agent_core.approvals.ApprovalManager", lambda: mgr,
    )
    registry = _registry_with(RunCommandTool())
    allowed = await registry.execute("run_command", {"command": "echo allowed"}, _context())
    blocked = await registry.execute("run_command", {"command": "echo denied"}, _context())

    assert "allowed" in allowed.text
    assert blocked.text.startswith("BLOCKED")


async def test_file_tools_read_write_edit_and_list(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    ctx = _context()
    target = tmp_path / "Desktop" / "note.txt"

    write = await WriteAnyFileTool().execute({"path": str(target), "content": "old text"}, ctx)
    read = await ReadAnyFileTool().execute({"path": str(target)}, ctx)
    edit = await EditAnyFileTool().execute(
        {"path": str(target), "old_string": "old", "new_string": "new"}, ctx,
    )
    listed = await ListDirectoryTool().execute({"path": str(target.parent)}, ctx)

    assert "Wrote" in write.text
    assert "old text" in read.text
    assert "Replaced 1" in edit.text
    assert "note.txt" in listed.text
    assert target.read_text(encoding="utf-8") == "new text"


async def test_file_tools_deny_secrets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    secret = tmp_path / ".env"
    secret.write_text("TOKEN=secret", encoding="utf-8")

    result = await ReadAnyFileTool().execute({"path": str(secret)}, _context())

    assert result.text.startswith("ERROR: access denied")
