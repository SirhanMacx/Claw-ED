"""Tests for the agent loop with FakeLLM."""

import pytest

from clawed.agent_core.context import AgentContext, ToolResult
from clawed.agent_core.fake_llm import FakeLLM, FakeLLMExhaustedError
from clawed.agent_core.loop import run_agent_loop
from clawed.agent_core.tools.base import ToolRegistry
from clawed.models import AppConfig


class TestFakeLLM:
    @pytest.mark.asyncio
    async def test_text_response(self):
        llm = FakeLLM([{"type": "text", "content": "Hello!"}])
        resp = await llm.generate(messages=[], tools=None, system="")
        assert resp["type"] == "text"
        assert resp["content"] == "Hello!"

    @pytest.mark.asyncio
    async def test_tool_call_response(self):
        llm = FakeLLM(
            [
                {
                    "type": "tool_calls",
                    "tool_calls": [{"id": "1", "name": "generate_lesson", "arguments": {"topic": "fractions"}}],
                }
            ]
        )
        resp = await llm.generate(messages=[], tools=None, system="")
        assert resp["type"] == "tool_calls"
        assert resp["tool_calls"][0]["name"] == "generate_lesson"

    @pytest.mark.asyncio
    async def test_sequence(self):
        llm = FakeLLM(
            [
                {"type": "tool_calls", "tool_calls": [{"id": "1", "name": "search_standards", "arguments": {}}]},
                {"type": "text", "content": "Found standards."},
            ]
        )
        r1 = await llm.generate(messages=[], tools=None, system="")
        assert r1["type"] == "tool_calls"
        r2 = await llm.generate(messages=[], tools=None, system="")
        assert r2["type"] == "text"

    @pytest.mark.asyncio
    async def test_exhausted_raises(self):
        llm = FakeLLM([{"type": "text", "content": "only one"}])
        await llm.generate(messages=[], tools=None, system="")
        with pytest.raises(FakeLLMExhaustedError):
            await llm.generate(messages=[], tools=None, system="")


class _EchoTool:
    def schema(self):
        return {
            "type": "function",
            "function": {
                "name": "echo",
                "description": "Echo back",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                    },
                },
            },
        }

    async def execute(self, params, context):
        return ToolResult(text=f"echoed: {params.get('text', '')}")


def _make_ctx():
    return AgentContext(
        teacher_id="t1",
        config=AppConfig(),
        teacher_profile={},
        persona=None,
        session_history=[],
        improvement_context="",
    )


class TestAgentLoop:
    @pytest.mark.asyncio
    async def test_text_only_response(self):
        llm = FakeLLM([{"type": "text", "content": "Hello teacher!"}])
        reg = ToolRegistry()
        result = await run_agent_loop(
            message="hi",
            system="You are helpful.",
            context=_make_ctx(),
            llm=llm,
            registry=reg,
        )
        assert result.text == "Hello teacher!"

    @pytest.mark.asyncio
    async def test_tool_call_then_text(self):
        llm = FakeLLM(
            [
                {
                    "type": "tool_calls",
                    "tool_calls": [
                        {"id": "1", "name": "echo", "arguments": {"text": "hello"}},
                    ],
                },
                {"type": "text", "content": "I echoed hello for you."},
            ]
        )
        reg = ToolRegistry()
        reg.register(_EchoTool())
        result = await run_agent_loop(
            message="echo hello",
            system="",
            context=_make_ctx(),
            llm=llm,
            registry=reg,
        )
        assert result.text == "I echoed hello for you."

    @pytest.mark.asyncio
    async def test_safety_limit(self):
        infinite_tools = [
            {
                "type": "tool_calls",
                "tool_calls": [
                    {"id": str(i), "name": "echo", "arguments": {"text": "loop"}},
                ],
            }
            for i in range(25)
        ]
        llm = FakeLLM(infinite_tools)
        reg = ToolRegistry()
        reg.register(_EchoTool())
        result = await run_agent_loop(
            message="loop",
            system="",
            context=_make_ctx(),
            llm=llm,
            registry=reg,
            max_iterations=20,
        )
        assert "working" in result.text.lower() or "iteration" in result.text.lower()

    @pytest.mark.asyncio
    async def test_unknown_tool_handled(self):
        llm = FakeLLM(
            [
                {
                    "type": "tool_calls",
                    "tool_calls": [
                        {"id": "1", "name": "nonexistent_tool", "arguments": {}},
                    ],
                },
                {"type": "text", "content": "Sorry, I couldn't do that."},
            ]
        )
        reg = ToolRegistry()
        result = await run_agent_loop(
            message="do something",
            system="",
            context=_make_ctx(),
            llm=llm,
            registry=reg,
        )
        assert result.text == "Sorry, I couldn't do that."
