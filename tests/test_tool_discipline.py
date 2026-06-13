"""Tests for M2 backend polish: tool-call discipline in the system prompt
and the /api/agent/tools registry endpoint (Skills gallery).

The discipline block exists because minimax-m3 was observed claiming
actions ("I created the folder") after a denial, without calling any
tool. The prompt must make "no tool call → no claim" explicit, and must
forbid silently retrying a denied action.
"""
from __future__ import annotations

import os
import tempfile

# ── Environment must be configured before importing the app ──────────────
os.environ["EDUAGENT_LOCAL_AUTH_BYPASS"] = "1"
os.environ["PYTHON_KEYRING_BACKEND"] = "keyring.backends.null.Keyring"
os.environ.setdefault(
    "EDUAGENT_DATA_DIR", tempfile.mkdtemp(prefix="clawed_test_discipline_")
)

import pytest
from fastapi.testclient import TestClient

from clawed.agent_core.prompt import build_system_prompt


def _prompt() -> str:
    return build_system_prompt(
        teacher_name="Ms. Smith",
        identity_summary="8th grade Science",
        improvement_context="",
        tool_names=["run_command", "generate_lesson_bundle"],
    )


class TestTruthfulnessBlock:
    def test_actions_require_tools_block_present(self) -> None:
        prompt = _prompt()
        assert "TRUTHFULNESS — ACTIONS REQUIRE TOOLS" in prompt
        assert "Words are not actions" in prompt

    def test_denial_means_not_done(self) -> None:
        prompt = _prompt()
        # A denied / blocked action must be reported as NOT done…
        assert "DID NOT HAPPEN" in prompt
        # …and must not be silently retried.
        assert "NOT silently retry the same denied action" in prompt

    def test_forbids_invented_results(self) -> None:
        prompt = _prompt()
        assert "Never invent file paths, file contents, or command output" in prompt

    def test_blocked_and_error_results_covered(self) -> None:
        prompt = _prompt()
        assert "BLOCKED or ERROR" in prompt

    def test_history_is_not_action_rule(self) -> None:
        # Session history replays past "Done" replies WITHOUT their tool
        # calls — the model must not learn to answer from memory.
        prompt = _prompt()
        assert "Every new action request starts at zero" in prompt

    def test_endgame_guideline_present(self) -> None:
        # Recency-biased models need the rule near the END of the prompt too.
        prompt = _prompt()
        tail = prompt[-2500:]
        assert "ACTIONS REQUIRE TOOLS, EVERY TIME" in tail

    def test_block_survives_minimal_prompt(self) -> None:
        # The block must not depend on optional context sections.
        prompt = build_system_prompt(
            teacher_name="T",
            identity_summary="",
            improvement_context="",
            tool_names=[],
        )
        assert "TRUTHFULNESS — ACTIONS REQUIRE TOOLS" in prompt


# ── /api/agent/tools (Skills gallery source) ─────────────────────────────


@pytest.fixture(scope="module")
def client() -> TestClient:
    from clawed.api.server import create_app

    return TestClient(create_app())


class TestAgentToolsEndpoint:
    def test_lists_real_registry(self, client: TestClient) -> None:
        resp = client.get("/api/agent/tools")
        assert resp.status_code == 200
        tools = resp.json()["tools"]
        names = {t["name"] for t in tools}
        # The desktop-agent backbone tools must be present.
        assert "run_command" in names
        assert "generate_lesson" in names
        # ~45 tools in the registry — guard against an empty/stub answer.
        assert len(tools) >= 30

    def test_tool_shape(self, client: TestClient) -> None:
        tools = client.get("/api/agent/tools").json()["tools"]
        for tool in tools:
            assert tool["name"]
            assert "description" in tool
            assert tool["risk_level"]

    def test_run_command_declares_exec_risk(self, client: TestClient) -> None:
        tools = client.get("/api/agent/tools").json()["tools"]
        run_command = next(t for t in tools if t["name"] == "run_command")
        assert run_command["risk_level"] == "command_exec"

    def test_lesson_bundle_declares_local_write_risk(self, client: TestClient) -> None:
        tools = client.get("/api/agent/tools").json()["tools"]
        lesson_bundle = next(t for t in tools if t["name"] == "generate_lesson_bundle")
        assert lesson_bundle["risk_level"] == "write_local"

    def test_sorted_by_name(self, client: TestClient) -> None:
        names = [t["name"] for t in client.get("/api/agent/tools").json()["tools"]]
        assert names == sorted(names)

    def test_empty_gateway_registry_falls_back(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from clawed.agent_core.tools.base import ToolRegistry
        from clawed.api.routes import agent_stream

        class EmptyGateway:
            _registry = ToolRegistry()

        monkeypatch.setattr(agent_stream, "_get_gateway", lambda: EmptyGateway())
        tools = client.get("/api/agent/tools").json()["tools"]
        names = {t["name"] for t in tools}
        assert "run_command" in names
        assert len(tools) >= 30


# ── Registry collision regression ────────────────────────────────────────
# self_modify.py used to register a workspace-sandboxed "write_file" /
# "read_file" that silently SHADOWED the general Mac tools in mac_files.py
# (discover() loads modules alphabetically; last registration won). The
# desktop app's "write a file on my Desktop" flow then wrote into
# ~/.eduagent/workspace/~/Desktop instead. Lock the names down.


class TestRegistryCollisions:
    @pytest.fixture(scope="class")
    def registry(self):  # type: ignore[no-untyped-def]
        from pathlib import Path

        import clawed.agent_core.tools as tools_pkg
        from clawed.agent_core.tools.base import ToolRegistry

        reg = ToolRegistry()
        reg.discover(Path(tools_pkg.__file__).parent)
        return reg

    def test_general_write_file_wins(self, registry) -> None:  # type: ignore[no-untyped-def]
        from clawed.agent_core.tools.mac_files import WriteAnyFileTool

        assert isinstance(registry.get("write_file"), WriteAnyFileTool)

    def test_general_read_file_wins(self, registry) -> None:  # type: ignore[no-untyped-def]
        from clawed.agent_core.tools.mac_files import ReadAnyFileTool

        assert isinstance(registry.get("read_file"), ReadAnyFileTool)

    def test_workspace_variants_renamed(self, registry) -> None:  # type: ignore[no-untyped-def]
        from clawed.agent_core.tools.self_modify import ReadFileTool, WriteFileTool

        assert isinstance(registry.get("write_workspace_file"), WriteFileTool)
        assert isinstance(registry.get("read_workspace_file"), ReadFileTool)
