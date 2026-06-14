"""Reconnect / resume: GET /api/agent/latest-turn lets a phone that dropped the
SSE stream re-attach to the turn the Mac kept running in the background."""
from __future__ import annotations

import asyncio

from clawed.api.routes import agent_stream
from clawed.api.routes.agent_stream import _LATEST_TURN, _strip_turn_footer, latest_turn


def test_strip_turn_footer_removes_authoritative_log() -> None:
    text = (
        "Here is your lesson on the Age of Exploration.\n\n"
        "Authoritative approval log for this turn:\n"
        "- run_command: approved; risk=command_exec"
    )
    assert _strip_turn_footer(text) == "Here is your lesson on the Age of Exploration."


def test_strip_turn_footer_noop_without_footer() -> None:
    assert _strip_turn_footer("plain reply") == "plain reply"


def test_latest_turn_returns_recorded_turn(monkeypatch) -> None:
    teacher = "teacher-resume-test"
    recorded = {
        "turn_id": "abc123",
        "status": "done",
        "message": "Build tomorrow's lesson",
        "final_text": "Done — saved to your Mac.",
        "files": ["/Users/x/clawed_output/teacher.docx"],
        "started_at": 1.0,
        "done_at": 2.0,
    }
    _LATEST_TURN[teacher] = recorded

    monkeypatch.setattr(
        "clawed.agent_core.identity.get_teacher_id", lambda: teacher,
    )

    class _NoPending:
        def pending_for_teacher(self, _tid: str) -> list:
            return []

    monkeypatch.setattr(
        "clawed.agent_core.approvals.ApprovalManager", lambda: _NoPending(),
    )

    try:
        result = asyncio.run(latest_turn(request=None))  # type: ignore[arg-type]
    finally:
        _LATEST_TURN.pop(teacher, None)

    assert result["turn"]["turn_id"] == "abc123"
    assert result["turn"]["status"] == "done"
    assert result["turn"]["files"] == ["/Users/x/clawed_output/teacher.docx"]
    assert result["pending_approvals"] == []


def test_latest_turn_none_when_no_turn(monkeypatch) -> None:
    teacher = "teacher-never-ran"
    _LATEST_TURN.pop(teacher, None)
    monkeypatch.setattr(
        "clawed.agent_core.identity.get_teacher_id", lambda: teacher,
    )

    class _NoPending:
        def pending_for_teacher(self, _tid: str) -> list:
            return []

    monkeypatch.setattr(
        "clawed.agent_core.approvals.ApprovalManager", lambda: _NoPending(),
    )

    result = asyncio.run(latest_turn(request=None))  # type: ignore[arg-type]
    assert result["turn"] is None
    assert result["pending_approvals"] == []


# keep a reference so linters don't flag the module import as unused
assert agent_stream is not None
