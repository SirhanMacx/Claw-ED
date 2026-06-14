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


# ── remote (tunnel) approval hardening ───────────────────────────────


async def test_remote_turn_ignores_standing_approval(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """A standing 'Always allow' must NOT let a remote turn through — even the
    exact same command must be confirmed fresh on the device."""
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
    monkeypatch.setattr("clawed.agent_core.approvals.ApprovalManager", lambda: mgr)

    registry = _registry_with(RunCommandTool())
    # Local turn with the standing grant → allowed.
    local = await registry.execute("run_command", {"command": "echo allowed"}, _context())
    # Remote turn, same command, same standing grant, NO live channel → blocked.
    remote = await registry.execute(
        "run_command", {"command": "echo allowed"}, _context(is_remote=True),
    )
    assert "allowed" in local.text
    assert remote.text.startswith("BLOCKED")


async def test_remote_always_does_not_create_standing_grant(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """A remote 'Always allow' is downgraded to one-time: it must not persist
    as a standing grant, and the resolved event reports always=False."""
    mgr = ApprovalManager(base_dir=tmp_path)
    monkeypatch.setattr("clawed.agent_core.approvals.ApprovalManager", lambda: mgr)
    registry = _registry_with(RunCommandTool())

    events: list[tuple[str, dict[str, Any]]] = []

    async def resolve_when_requested() -> None:
        while not any(e == "approval_required" for e, _ in events):
            await asyncio.sleep(0.01)
        aid = next(d["approval_id"] for e, d in events if e == "approval_required")
        ApprovalBroker.instance().resolve(aid, ApprovalDecision(approved=True, always=True))

    task = asyncio.create_task(resolve_when_requested())
    result = await registry.execute(
        "run_command", {"command": "echo remote-once"},
        _context(is_remote=True, event_callback=lambda t, d: events.append((t, d))),
    )
    await task

    assert "remote-once" in result.text
    resolved = next(d for e, d in events if e == "approval_resolved")
    assert resolved["always"] is False  # downgraded — no standing grant
    # No standing 'approved' record persisted for this command.
    sig = RunCommandTool.approval_signature({"command": "echo remote-once"})
    assert mgr.get_standing_approval("t-test", "run_command", params_signature=sig) is None


async def test_remote_turn_disables_auto_approve(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """CLAWED_AUTO_APPROVE never applies to a remote write — it must still ask."""
    monkeypatch.setenv("CLAWED_AUTO_APPROVE", "1")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(
        "clawed.agent_core.approvals.ApprovalManager",
        lambda: ApprovalManager(base_dir=tmp_path / "appr"),
    )
    registry = _registry_with(WriteAnyFileTool())
    target = tmp_path / "Documents" / "remote.txt"

    # Local + auto-approve → write goes through.
    local = await registry.execute(
        "write_file", {"path": str(target), "content": "x"}, _context(),
    )
    assert "Wrote" in local.text
    # Remote + auto-approve, no live channel → blocked (must confirm on device).
    remote = await registry.execute(
        "write_file", {"path": str(tmp_path / "Documents" / "r2.txt"), "content": "y"},
        _context(is_remote=True),
    )
    assert remote.text.startswith("BLOCKED")


# ── secret denylist + path-escape hardening ──────────────────────────


@pytest.mark.parametrize("rel", [
    ".aws/credentials", ".kube/config", ".docker/config.json",
    ".git-credentials", ".config/gcloud/access_tokens.db", ".pgpass",
    ".azure/accessTokens.json", ".ssh/id_rsa", ".npmrc",
])
async def test_file_tools_deny_credential_stores(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, rel: str,
) -> None:
    """Reads and writes to known credential stores are refused even with
    approval — they must never reach the model or be clobbered."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("SECRET=value", encoding="utf-8")

    read = await ReadAnyFileTool().execute({"path": str(target)}, _context())
    write = await WriteAnyFileTool().execute(
        {"path": str(target), "content": "x"}, _context(),
    )
    assert read.text.startswith("ERROR: access denied"), rel
    assert write.text.startswith("ERROR: access denied"), rel
    # The write must NOT have modified the real secret.
    assert target.read_text(encoding="utf-8") == "SECRET=value"


@pytest.mark.parametrize("rel", [
    ".ENV", ".Env", ".AWS/credentials", ".SSH/id_rsa", ".Git-Credentials",
    ".NPMRC",
])
async def test_file_tools_deny_is_case_insensitive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, rel: str,
) -> None:
    """macOS's default filesystem is case-insensitive, so ~/.ENV opens the real
    ~/.env. The credential denylist must match regardless of typed case — a
    case-sensitive check would let read_file('~/.AWS/credentials') slip through."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    target = tmp_path / rel

    read = await ReadAnyFileTool().execute({"path": str(target)}, _context())
    write = await WriteAnyFileTool().execute(
        {"path": str(target), "content": "x"}, _context(),
    )
    assert read.text.startswith("ERROR: access denied"), rel
    assert write.text.startswith("ERROR: access denied"), rel


async def test_file_tools_deny_path_escape_outside_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A path that resolves outside the teacher's home is refused, including
    a ../ traversal."""
    home = tmp_path / "home"
    home.mkdir()
    outside = tmp_path / "etc-passwd"
    outside.write_text("root:x:0:0", encoding="utf-8")
    monkeypatch.setattr(Path, "home", lambda: home)

    escape = await ReadAnyFileTool().execute(
        {"path": str(home / ".." / "etc-passwd")}, _context(),
    )
    absolute = await ReadAnyFileTool().execute({"path": "/etc/hosts"}, _context())
    assert escape.text.startswith("ERROR: access denied")
    assert absolute.text.startswith("ERROR: access denied")
