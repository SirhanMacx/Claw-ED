"""Tests for file management tools (Phase 7)."""

from __future__ import annotations

from pathlib import Path

import pytest

from clawed.agent_core.tools.file_manager import (
    FileListTool,
    FileOrganizeTool,
    WorkspaceStatusTool,
    _human_size,
)


@pytest.fixture
def output_dir(tmp_path):
    d = tmp_path / "clawed_output"
    d.mkdir()
    (d / "lesson1.docx").write_text("lesson content")
    (d / "lesson2.pdf").write_bytes(b"pdf content")
    (d / "sub").mkdir()
    (d / "sub" / "quiz.docx").write_text("quiz content")
    return d


class TestHumanSize:
    def test_bytes(self):
        assert _human_size(500) == "500B"

    def test_kb(self):
        assert _human_size(2048) == "2KB"

    def test_mb(self):
        assert _human_size(5 * 1024 * 1024) == "5MB"


class TestFileListTool:
    def test_schema_valid(self):
        tool = FileListTool()
        s = tool.schema()
        assert s["function"]["name"] == "list_output_files"

    @pytest.mark.asyncio
    async def test_list_files(self, output_dir, monkeypatch):
        from clawed.agent_core.context import AgentContext
        from clawed.models import AppConfig

        config = AppConfig()
        config.output_dir = str(output_dir)
        ctx = AgentContext(
            teacher_id="t1",
            config=config,
            teacher_profile={},
            persona=None,
            session_history=[],
            improvement_context="",
        )
        tool = FileListTool()
        result = await tool.execute({}, ctx)
        assert "lesson1.docx" in result.text
        assert "lesson2.pdf" in result.text

    @pytest.mark.asyncio
    async def test_list_subdirectory(self, output_dir, monkeypatch):
        from clawed.agent_core.context import AgentContext
        from clawed.models import AppConfig

        config = AppConfig()
        config.output_dir = str(output_dir)
        ctx = AgentContext(
            teacher_id="t1",
            config=config,
            teacher_profile={},
            persona=None,
            session_history=[],
            improvement_context="",
        )
        tool = FileListTool()
        result = await tool.execute({"path": "sub"}, ctx)
        assert "quiz.docx" in result.text


class TestFileOrganizeTool:
    def test_schema_valid(self):
        tool = FileOrganizeTool()
        s = tool.schema()
        assert s["function"]["name"] == "organize_files"

    @pytest.mark.asyncio
    async def test_create_folder(self, output_dir):
        from clawed.agent_core.context import AgentContext
        from clawed.models import AppConfig

        config = AppConfig()
        config.output_dir = str(output_dir)
        ctx = AgentContext(
            teacher_id="t1",
            config=config,
            teacher_profile={},
            persona=None,
            session_history=[],
            improvement_context="",
        )
        tool = FileOrganizeTool()
        result = await tool.execute({"action": "create_folder", "destination": "history/unit1"}, ctx)
        assert "Created folder" in result.text
        assert (output_dir / "history" / "unit1").exists()

    @pytest.mark.asyncio
    async def test_move_file(self, output_dir):
        from clawed.agent_core.context import AgentContext
        from clawed.models import AppConfig

        config = AppConfig()
        config.output_dir = str(output_dir)
        ctx = AgentContext(
            teacher_id="t1",
            config=config,
            teacher_profile={},
            persona=None,
            session_history=[],
            improvement_context="",
        )
        tool = FileOrganizeTool()
        result = await tool.execute(
            {
                "action": "move_file",
                "source": "lesson1.docx",
                "destination": "sub/lesson1.docx",
            },
            ctx,
        )
        assert "Moved" in result.text
        assert (output_dir / "sub" / "lesson1.docx").exists()
        assert not (output_dir / "lesson1.docx").exists()


class TestWorkspaceStatusTool:
    def test_schema_valid(self):
        tool = WorkspaceStatusTool()
        s = tool.schema()
        assert s["function"]["name"] == "workspace_status"

    @pytest.mark.asyncio
    async def test_status_report(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EDUAGENT_DATA_DIR", str(tmp_path))
        # Create workspace files
        ws = tmp_path / "workspace"
        ws.mkdir()
        (ws / "soul.md").write_text("Teaching philosophy here")
        from clawed.agent_core.context import AgentContext
        from clawed.models import AppConfig

        ctx = AgentContext(
            teacher_id="t1",
            config=AppConfig(),
            teacher_profile={},
            persona=None,
            session_history=[],
            improvement_context="",
        )
        tool = WorkspaceStatusTool()
        result = await tool.execute({}, ctx)
        assert "SOUL.md" in result.text
        assert "24 chars" in result.text


class TestToolDiscovery:
    def test_file_tools_discovered(self):
        from clawed.agent_core.tools.base import ToolRegistry

        reg = ToolRegistry()
        reg.discover(Path(__file__).parent.parent / "clawed" / "agent_core" / "tools")
        names = reg.tool_names()
        assert "list_output_files" in names
        assert "organize_files" in names
        assert "workspace_status" in names
