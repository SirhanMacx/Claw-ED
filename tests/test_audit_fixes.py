"""Tests for audit remediation — verifies security and correctness fixes."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from clawed.agent_core.context import AgentContext, ToolResult
from clawed.agent_core.tools.base import (
    RISK_PACKAGE_INSTALL,
    RISK_READ_ONLY,
    RISK_WRITE_LOCAL,
    ToolRegistry,
)


def _ctx() -> AgentContext:
    return AgentContext(
        teacher_id="test",
        config=MagicMock(),
        teacher_profile={},
        persona=None,
        session_history=[],
        improvement_context="",
    )


class _ReadOnlyTool:
    risk_level = RISK_READ_ONLY

    def schema(self):
        return {"type": "function", "function": {"name": "safe_tool",
                "description": "t", "parameters": {"type": "object", "properties": {}}}}

    async def execute(self, params, context):
        return ToolResult(text="safe output")


class _WriteTool:
    risk_level = RISK_WRITE_LOCAL

    def schema(self):
        return {"type": "function", "function": {"name": "write_tool",
                "description": "t", "parameters": {"type": "object", "properties": {}}}}

    async def execute(self, params, context):
        return ToolResult(text="wrote something")


class _DangerousTool:
    risk_level = RISK_PACKAGE_INSTALL

    def schema(self):
        return {"type": "function", "function": {"name": "install_tool",
                "description": "t", "parameters": {"type": "object", "properties": {}}}}

    async def execute(self, params, context):
        return ToolResult(text="installed something")


class TestApprovalPolicyEnforcement:
    """F1 audit fix: tools are gated by risk_level at dispatch."""

    @pytest.mark.asyncio
    async def test_read_only_tool_always_allowed(self):
        reg = ToolRegistry()
        reg.register(_ReadOnlyTool())
        result = await reg.execute("safe_tool", {}, _ctx())
        assert result.text == "safe output"

    @pytest.mark.asyncio
    async def test_package_install_blocked_without_approval(self, monkeypatch):
        """Package install tools are ALWAYS blocked without approval."""
        monkeypatch.delenv("CLAWED_AUTO_APPROVE", raising=False)
        reg = ToolRegistry()
        reg.register(_DangerousTool())
        result = await reg.execute("install_tool", {}, _ctx())
        assert "BLOCKED" in result.text

    @pytest.mark.asyncio
    async def test_write_tool_blocked_without_auto_approve(self, monkeypatch):
        """Write tools blocked when auto-approve is off."""
        monkeypatch.setenv("CLAWED_AUTO_APPROVE", "0")
        reg = ToolRegistry()
        reg.register(_WriteTool())
        result = await reg.execute("write_tool", {}, _ctx())
        assert "BLOCKED" in result.text

    @pytest.mark.asyncio
    async def test_write_tool_allowed_with_auto_approve(self, monkeypatch):
        """Write tools allowed when auto-approve is on."""
        monkeypatch.setenv("CLAWED_AUTO_APPROVE", "1")
        reg = ToolRegistry()
        reg.register(_WriteTool())
        result = await reg.execute("write_tool", {}, _ctx())
        assert "wrote something" in result.text
        assert "auto-approve policy" in result.text
        assert result.data["approval_policy"]["risk_level"] == RISK_WRITE_LOCAL


class TestInstallPackageAllowlist:
    """F2 audit fix: only allowlisted packages can be installed."""

    @pytest.mark.asyncio
    async def test_allowlisted_package_check(self):
        from clawed.agent_core.tools.self_equip import InstallPackageTool

        tool = InstallPackageTool()
        # numpy is already installed — should return "already installed"
        result = await tool.execute(
            {"package_name": "json", "reason": "test"},
            _ctx(),
        )
        assert "already installed" in result.text

    @pytest.mark.asyncio
    async def test_non_allowlisted_package_blocked(self):
        from clawed.agent_core.tools.self_equip import InstallPackageTool

        tool = InstallPackageTool()
        result = await tool.execute(
            {"package_name": "evil-package", "reason": "test"},
            _ctx(),
        )
        assert "BLOCKED" in result.text
        assert "approved package list" in result.text


class TestUDLVocabSimplification:
    """H4 audit fix: 'Dr. King' no longer becomes 'Dr.'"""

    def test_dr_king_preserved(self):
        from clawed.compile_lms import generate_udl_tiers
        from clawed.master_content import (
            DoNow,
            GuidedNote,
            InstructionSection,
            MasterContent,
            StimulusQuestion,
            VocabularyEntry,
        )
        from clawed.models import DifferentiationNotes

        mc = MasterContent(
            title="T", subject="S", grade_level="8", topic="T",
            objective="O",
            vocabulary=[
                VocabularyEntry(
                    term="MLK",
                    definition=(
                        "Dr. Martin Luther King Jr. was a civil "
                        "rights leader. He led the movement."
                    ),
                    context_sentence="C.",
                ),
            ],
            primary_sources=[],
            do_now=DoNow(
                stimulus="S", stimulus_type="t",
                questions=["Q"], answers=["A"],
            ),
            direct_instruction=[
                InstructionSection(
                    heading="H", content="C",
                    teacher_script="Ask?", image_spec="t",
                ),
            ],
            guided_notes=[GuidedNote(prompt="P", answer="A", section_ref="H")] * 5,
            exit_ticket=[
                StimulusQuestion(
                    stimulus="S" * 60, stimulus_type="text",
                    question="Q", answer="A", cognitive_level="recall",
                ),
            ],
            differentiation=DifferentiationNotes(
                struggling=["x"], advanced=["y"], ell=["z"],
            ),
        )

        tiers = generate_udl_tiers(mc)
        scaffolded_def = tiers["scaffolded"]["vocabulary"][0]["definition"]
        # Should NOT be just "Dr."
        assert len(scaffolded_def) > 5
        assert "Dr. Martin Luther King Jr" in scaffolded_def


class TestCommonCartridgeExport:
    """B4 audit fix: CC export produces valid ZIP with namespace."""

    def test_exports_valid_zip(self, tmp_path):
        import zipfile

        from clawed.compile_lms import compile_common_cartridge
        from clawed.master_content import (
            DoNow,
            GuidedNote,
            InstructionSection,
            MasterContent,
            StimulusQuestion,
            VocabularyEntry,
        )
        from clawed.models import DifferentiationNotes

        mc = MasterContent(
            title="CC Test", subject="History", grade_level="8",
            topic="Rev", objective="SWBAT test",
            vocabulary=[VocabularyEntry(term="T", definition="D.", context_sentence="C.")],
            primary_sources=[],
            do_now=DoNow(stimulus="S", stimulus_type="t", questions=["Q"], answers=["A"]),
            direct_instruction=[InstructionSection(heading="H", content="C", teacher_script="Ask?", image_spec="t")],
            guided_notes=[GuidedNote(prompt="P", answer="A", section_ref="H")] * 5,
            exit_ticket=[StimulusQuestion(
                stimulus="S" * 60, stimulus_type="text",
                question="Q", answer="A", cognitive_level="recall",
            )],
            differentiation=DifferentiationNotes(struggling=["x"], advanced=["y"], ell=["z"]),
        )

        path = compile_common_cartridge(mc, tmp_path)
        assert path.exists()
        assert path.suffix == ".imscc"

        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            assert "imsmanifest.xml" in names
            manifest = zf.read("imsmanifest.xml").decode("utf-8")
            assert "xmlns:xsi" in manifest


class TestSendNotification:
    """B1 audit fix: send_notification function exists and handles missing config."""

    def test_returns_false_without_config(self, monkeypatch):
        monkeypatch.setenv("EDUAGENT_DATA_DIR", "/nonexistent")
        from clawed.transports.telegram import send_notification

        result = send_notification("test message")
        assert result is False


class TestPathContainment:
    """Path checks must be boundary-aware, not string-prefix checks."""

    def test_path_is_within_rejects_prefix_sibling(self, tmp_path):
        from clawed.paths import path_is_within

        root = tmp_path / "base"
        sibling = tmp_path / "base-evil"
        root.mkdir()
        sibling.mkdir()

        assert path_is_within(root / "child.txt", root)
        assert not path_is_within(sibling / "child.txt", root)

    @pytest.mark.asyncio
    async def test_read_file_blocks_prefix_sibling_escape(self, tmp_path, monkeypatch):
        from clawed.agent_core.tools.self_modify import ReadFileTool

        data_root = tmp_path / "ed"
        sibling = tmp_path / "ed-evil"
        data_root.mkdir()
        sibling.mkdir()
        (sibling / "secret.txt").write_text("do not read", encoding="utf-8")
        monkeypatch.setenv("EDUAGENT_DATA_DIR", str(data_root))

        result = await ReadFileTool().execute(
            {"path": "../ed-evil/secret.txt"},
            _ctx(),
        )

        assert "out of bounds" in result.text
        assert "do not read" not in result.text

    @pytest.mark.asyncio
    async def test_write_file_blocks_prefix_sibling_escape(self, tmp_path, monkeypatch):
        from clawed.agent_core.tools.self_modify import WriteFileTool

        data_root = tmp_path / "ed"
        sibling = tmp_path / "ed-evil"
        data_root.mkdir()
        sibling.mkdir()
        monkeypatch.setenv("EDUAGENT_DATA_DIR", str(data_root))

        result = await WriteFileTool().execute(
            {
                "path": "workspace/../../ed-evil/pwned.txt",
                "content": "do not write",
            },
            _ctx(),
        )

        assert "within workspace or output directory" in result.text
        assert not (sibling / "pwned.txt").exists()

    @pytest.mark.asyncio
    async def test_read_workspace_blocks_prefix_sibling_escape(self, tmp_path, monkeypatch):
        from clawed.agent_core.tools.read_workspace import ReadWorkspaceTool

        data_root = tmp_path / "ed"
        workspace = data_root / "workspace"
        sibling = data_root / "workspace-evil"
        workspace.mkdir(parents=True)
        sibling.mkdir()
        (sibling / "secret.txt").write_text("do not read", encoding="utf-8")
        monkeypatch.setenv("EDUAGENT_DATA_DIR", str(data_root))

        result = await ReadWorkspaceTool().execute(
            {"filename": "../workspace-evil/secret.txt"},
            _ctx(),
        )

        assert "outside the workspace" in result.text
        assert "do not read" not in result.text

    def test_api_token_respects_runtime_data_dir(self, tmp_path, monkeypatch):
        from clawed.api.deps import get_api_token

        first = tmp_path / "first"
        second = tmp_path / "second"

        monkeypatch.setenv("EDUAGENT_DATA_DIR", str(first))
        first_token = get_api_token()

        monkeypatch.setenv("EDUAGENT_DATA_DIR", str(second))
        second_token = get_api_token()

        assert (first / "api_token").read_text(encoding="utf-8").strip() == first_token
        assert (second / "api_token").read_text(encoding="utf-8").strip() == second_token
        assert first_token != second_token
