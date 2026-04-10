"""Tests for self-equipping tools (Phase 6)."""

from __future__ import annotations

import pytest

from clawed.agent_core.tools.self_equip import CreateCustomToolTool, InstallPackageTool


class TestInstallPackageTool:
    def test_schema_valid(self):
        tool = InstallPackageTool()
        schema = tool.schema()
        assert schema["function"]["name"] == "install_package"
        assert "package_name" in schema["function"]["parameters"]["properties"]

    @pytest.mark.asyncio
    async def test_already_installed(self):
        from clawed.agent_core.context import AgentContext
        from clawed.models import AppConfig

        tool = InstallPackageTool()
        ctx = AgentContext(
            teacher_id="t1",
            config=AppConfig(),
            teacher_profile={},
            persona=None,
            session_history=[],
            improvement_context="",
        )
        # json is always available
        result = await tool.execute({"package_name": "json"}, ctx)
        assert "already installed" in result.text

    @pytest.mark.asyncio
    async def test_blocked_package(self):
        from clawed.agent_core.context import AgentContext
        from clawed.models import AppConfig

        tool = InstallPackageTool()
        ctx = AgentContext(
            teacher_id="t1",
            config=AppConfig(),
            teacher_profile={},
            persona=None,
            session_history=[],
            improvement_context="",
        )
        result = await tool.execute({"package_name": "os"}, ctx)
        assert "built-in" in result.text

    @pytest.mark.asyncio
    async def test_empty_name_error(self):
        from clawed.agent_core.context import AgentContext
        from clawed.models import AppConfig

        tool = InstallPackageTool()
        ctx = AgentContext(
            teacher_id="t1",
            config=AppConfig(),
            teacher_profile={},
            persona=None,
            session_history=[],
            improvement_context="",
        )
        result = await tool.execute({"package_name": ""}, ctx)
        assert "ERROR" in result.text


class TestCreateCustomToolTool:
    def test_schema_valid(self):
        tool = CreateCustomToolTool()
        schema = tool.schema()
        assert schema["function"]["name"] == "create_custom_tool"
        assert "tool_name" in schema["function"]["parameters"]["properties"]
        assert "prompt_template" in schema["function"]["parameters"]["properties"]

    @pytest.mark.asyncio
    async def test_create_tool_writes_yaml(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EDUAGENT_DATA_DIR", str(tmp_path))
        from clawed.agent_core.context import AgentContext
        from clawed.models import AppConfig

        tool = CreateCustomToolTool()
        ctx = AgentContext(
            teacher_id="t1",
            config=AppConfig(),
            teacher_profile={},
            persona=None,
            session_history=[],
            improvement_context="",
        )
        result = await tool.execute(
            {
                "tool_name": "vocab_quiz",
                "description": "Generate vocabulary quizzes",
                "prompt_template": "Create a vocab quiz on {topic} for grade {grade}.",
            },
            ctx,
        )
        assert "Created custom tool" in result.text
        # Verify file exists
        yaml_path = tmp_path / "tools" / "vocab_quiz.yaml"
        assert yaml_path.exists()

    @pytest.mark.asyncio
    async def test_missing_fields_error(self):
        from clawed.agent_core.context import AgentContext
        from clawed.models import AppConfig

        tool = CreateCustomToolTool()
        ctx = AgentContext(
            teacher_id="t1",
            config=AppConfig(),
            teacher_profile={},
            persona=None,
            session_history=[],
            improvement_context="",
        )
        result = await tool.execute({"tool_name": "test"}, ctx)
        assert "ERROR" in result.text


class TestToolDiscovery:
    def test_self_equip_tools_discovered(self):
        from pathlib import Path

        from clawed.agent_core.tools.base import ToolRegistry

        reg = ToolRegistry()
        reg.discover(Path(__file__).parent.parent / "clawed" / "agent_core" / "tools")
        names = reg.tool_names()
        assert "install_package" in names
        assert "create_custom_tool" in names
