"""Tests for the conversational agent with tool use."""

from unittest.mock import patch

import pytest

from clawed.models import AppConfig, LLMProvider
from clawed.tools import TOOL_DEFINITIONS, execute_tool


def _ollama_config() -> AppConfig:
    """Return a config with provider=OLLAMA for testing the agent loop."""
    return AppConfig(provider=LLMProvider.OLLAMA)


class TestToolDefinitions:
    def test_all_tools_have_required_fields(self):
        for tool in TOOL_DEFINITIONS:
            assert tool["type"] == "function"
            f = tool["function"]
            assert "name" in f
            assert "description" in f
            assert "parameters" in f

    def test_expected_tools_exist(self):
        names = {t["function"]["name"] for t in TOOL_DEFINITIONS}
        assert "generate_lesson" in names
        assert "generate_unit" in names
        assert "search_standards" in names
        assert "read_persona" in names
        assert "list_files" in names
        assert "read_file" in names
        assert "search_files" in names


class TestToolExecution:
    @pytest.mark.asyncio
    async def test_read_persona_no_session(self):
        result = await execute_tool("read_persona", {}, "nonexistent")
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_list_files_returns_string(self):
        result = await execute_tool("list_files", {"directory": "all"}, "t1")
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_search_files_no_results(self):
        result = await execute_tool("search_files", {"query": "xyznonexistent123"}, "t1")
        assert "No files" in result

    @pytest.mark.asyncio
    async def test_read_file_security(self):
        result = await execute_tool("read_file", {"path": "/etc/passwd"}, "t1")
        assert "Cannot read" in result or "not found" in result.lower()

    @pytest.mark.asyncio
    async def test_unknown_tool(self):
        result = await execute_tool("nonexistent_tool", {}, "t1")
        assert "Unknown tool" in result

    @pytest.mark.asyncio
    async def test_search_standards(self):
        result = await execute_tool("search_standards", {"subject": "math", "grade": "8"}, "t1")
        assert isinstance(result, str)


class TestAgentLoop:
    @pytest.mark.asyncio
    async def test_agent_returns_string(self):
        from clawed.agent import run_agent

        with patch("clawed.agent._call_with_ollama_tools") as mock_call:
            mock_call.return_value = {"type": "text", "content": "Hey! How can I help today?"}
            result = await run_agent(
                "hey",
                system="You are Claw-ED.",
                teacher_id="t1",
                config=_ollama_config(),
            )
            assert isinstance(result, str)
            assert "help" in result.lower() or "hey" in result.lower()

    @pytest.mark.asyncio
    async def test_agent_executes_tool_call(self):
        from clawed.agent import run_agent

        call_count = 0

        async def mock_call(messages, system, config):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {
                    "type": "tool_calls",
                    "tool_calls": [{"id": "1", "name": "read_persona", "arguments": {}}],
                }
            return {"type": "text", "content": "Here's your persona info!"}

        with patch("clawed.agent._call_with_ollama_tools", side_effect=mock_call):
            result = await run_agent(
                "show me my persona",
                system="test",
                teacher_id="t1",
                config=_ollama_config(),
            )
            assert isinstance(result, str)
            assert call_count == 2  # First call returned tool, second returned text

    @pytest.mark.asyncio
    async def test_agent_max_iterations(self):
        from clawed.agent import run_agent

        async def always_tool(messages, system, config):
            return {
                "type": "tool_calls",
                "tool_calls": [{"id": "1", "name": "list_files", "arguments": {}}],
            }

        with patch("clawed.agent._call_with_ollama_tools", side_effect=always_tool):
            result = await run_agent(
                "test",
                system="test",
                teacher_id="t1",
                config=_ollama_config(),
            )
            assert "limit" in result.lower()

    @pytest.mark.asyncio
    async def test_agent_executes_multiple_tool_calls(self):
        """When the LLM returns 2 tool calls, both should execute."""
        from clawed.agent import run_agent

        executed_tools = []

        async def mock_execute(name, arguments, teacher_id=""):
            executed_tools.append(name)
            return f"Result for {name}"

        call_count = 0

        async def mock_call(messages, system, config):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {
                    "type": "tool_calls",
                    "tool_calls": [
                        {"id": "1", "name": "search_standards", "arguments": {"subject": "history", "grade": "8"}},
                        {"id": "2", "name": "read_persona", "arguments": {}},
                    ],
                }
            return {"type": "text", "content": "Here are your standards and persona."}

        with patch("clawed.agent._call_with_ollama_tools", side_effect=mock_call):
            with patch("clawed.agent.execute_tool", side_effect=mock_execute):
                await run_agent(
                    "look up standards and show my persona",
                    system="test",
                    teacher_id="t1",
                    config=_ollama_config(),
                )
                assert "search_standards" in executed_tools
                assert "read_persona" in executed_tools
                assert len(executed_tools) == 2

    @pytest.mark.asyncio
    async def test_multi_tool_conversation_history(self):
        """Verify conversation history is built correctly for multi-tool responses."""
        from clawed.agent import run_agent

        captured_messages = []

        async def mock_call(messages, system, config):
            captured_messages.clear()
            captured_messages.extend(messages)
            # First call: return 2 tools. Second call: return text.
            if len(messages) <= 2:  # user message only
                return {
                    "type": "tool_calls",
                    "tool_calls": [
                        {"id": "a", "name": "list_files", "arguments": {}},
                        {"id": "b", "name": "read_persona", "arguments": {}},
                    ],
                }
            return {"type": "text", "content": "Done!"}

        with patch("clawed.agent._call_with_ollama_tools", side_effect=mock_call):
            await run_agent("test", system="test", teacher_id="t1", config=_ollama_config())

        # After tool execution, messages should have:
        # [user, assistant (with 2 tool_calls), tool_result_a, tool_result_b]
        assistant_msgs = [m for m in captured_messages if m["role"] == "assistant"]
        tool_msgs = [m for m in captured_messages if m["role"] == "tool"]
        assert len(assistant_msgs) == 1  # ONE assistant message
        assert len(assistant_msgs[0]["tool_calls"]) == 2  # with 2 tool calls
        assert len(tool_msgs) == 2  # Two separate tool results
