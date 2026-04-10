"""Tests for browser and research tools (Phase 3)."""

from __future__ import annotations

import pytest

from clawed.agent_core.tools.browser import (
    BrowserNavigateTool,
    BrowserSearchTool,
)
from clawed.agent_core.tools.research import (
    ResearchTopicTool,
    _build_research_queries,
)


class TestBrowserNavigateSchema:
    def test_schema_valid(self):
        tool = BrowserNavigateTool()
        schema = tool.schema()
        assert schema["function"]["name"] == "browse_web"
        assert "url" in schema["function"]["parameters"]["properties"]
        assert "url" in schema["function"]["parameters"]["required"]

    def test_tool_discoverable(self):
        tool = BrowserNavigateTool()
        assert hasattr(tool, "schema")
        assert hasattr(tool, "execute")


class TestBrowserSearchSchema:
    def test_schema_valid(self):
        tool = BrowserSearchTool()
        schema = tool.schema()
        assert schema["function"]["name"] == "web_search"
        assert "query" in schema["function"]["parameters"]["properties"]

    def test_tool_discoverable(self):
        tool = BrowserSearchTool()
        assert hasattr(tool, "schema")
        assert hasattr(tool, "execute")


class TestResearchTopicSchema:
    def test_schema_valid(self):
        tool = ResearchTopicTool()
        schema = tool.schema()
        assert schema["function"]["name"] == "research_topic"
        assert "topic" in schema["function"]["parameters"]["properties"]
        assert "subject" in schema["function"]["parameters"]["properties"]
        assert "focus" in schema["function"]["parameters"]["properties"]

    def test_focus_enum(self):
        tool = ResearchTopicTool()
        schema = tool.schema()
        focus = schema["function"]["parameters"]["properties"]["focus"]
        assert "enum" in focus
        assert "primary_sources" in focus["enum"]
        assert "current_events" in focus["enum"]


class TestBuildResearchQueries:
    def test_general_queries(self):
        queries = _build_research_queries("French Revolution", "", "general")
        assert len(queries) >= 2
        assert any("French Revolution" in q for q in queries)

    def test_primary_sources_queries(self):
        queries = _build_research_queries("Civil War", "US History", "primary_sources")
        assert any("primary source" in q for q in queries)
        assert any("US History" in q for q in queries)

    def test_current_events_queries(self):
        queries = _build_research_queries("democracy", "", "current_events")
        assert any("current events" in q for q in queries)

    def test_images_queries(self):
        queries = _build_research_queries("mitosis", "Biology", "images")
        assert any("diagram" in q or "image" in q for q in queries)


class TestBrowserExecuteValidation:
    @pytest.mark.asyncio
    async def test_empty_url_returns_error(self):
        from clawed.agent_core.context import AgentContext
        from clawed.models import AppConfig

        tool = BrowserNavigateTool()
        ctx = AgentContext(
            teacher_id="t1",
            config=AppConfig(),
            teacher_profile={},
            persona=None,
            session_history=[],
            improvement_context="",
        )
        result = await tool.execute({"url": ""}, ctx)
        assert "ERROR" in result.text

    @pytest.mark.asyncio
    async def test_empty_query_returns_error(self):
        from clawed.agent_core.context import AgentContext
        from clawed.models import AppConfig

        tool = BrowserSearchTool()
        ctx = AgentContext(
            teacher_id="t1",
            config=AppConfig(),
            teacher_profile={},
            persona=None,
            session_history=[],
            improvement_context="",
        )
        result = await tool.execute({"query": ""}, ctx)
        assert "ERROR" in result.text

    @pytest.mark.asyncio
    async def test_empty_topic_returns_error(self):
        from clawed.agent_core.context import AgentContext
        from clawed.models import AppConfig

        tool = ResearchTopicTool()
        ctx = AgentContext(
            teacher_id="t1",
            config=AppConfig(),
            teacher_profile={},
            persona=None,
            session_history=[],
            improvement_context="",
        )
        result = await tool.execute({"topic": ""}, ctx)
        assert "ERROR" in result.text


class TestToolDiscovery:
    def test_browser_tools_auto_discovered(self):
        """All 3 new tools should be discoverable by ToolRegistry."""
        from pathlib import Path

        from clawed.agent_core.tools.base import ToolRegistry

        reg = ToolRegistry()
        reg.discover(Path(__file__).parent.parent / "clawed" / "agent_core" / "tools")
        names = reg.tool_names()
        assert "browse_web" in names
        assert "web_search" in names
        assert "research_topic" in names
