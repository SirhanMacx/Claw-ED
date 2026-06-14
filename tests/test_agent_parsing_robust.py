"""A misbehaving provider response (empty choices, malformed tool-call JSON)
must degrade gracefully instead of crashing the agent turn with a raw
IndexError / JSONDecodeError. Regression for the live OpenRouter hot path
(clawed/agent.py:_openai_with_tools)."""
from __future__ import annotations

import httpx
import pytest

import clawed.agent as agent_mod
from clawed.models import AppConfig, LLMProvider


class _FakeResp:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _FakeClient:
    """Stands in for httpx.AsyncClient; returns a canned payload from .post()."""

    payload: dict = {}

    def __init__(self, *a, **k) -> None:
        pass

    async def __aenter__(self) -> "_FakeClient":
        return self

    async def __aexit__(self, *a) -> None:
        return None

    async def post(self, *a, **k) -> _FakeResp:
        return _FakeResp(_FakeClient.payload)


@pytest.fixture()
def _patched(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)
    monkeypatch.setattr("clawed.config.get_api_key", lambda *_a, **_k: "test-key")
    cfg = AppConfig()
    cfg.provider = LLMProvider.OPENROUTER
    return cfg


async def test_empty_choices_degrades_to_friendly_text(_patched) -> None:
    _FakeClient.payload = {"choices": []}
    out = await agent_mod._openai_with_tools([{"role": "user", "content": "hi"}], "sys", _patched)
    assert out["type"] == "text"
    assert "snag" in out["content"].lower() or out["content"]  # no crash, some text


async def test_malformed_tool_arguments_are_skipped(_patched) -> None:
    _FakeClient.payload = {
        "choices": [{"message": {"tool_calls": [
            {"id": "1", "function": {"name": "read_persona", "arguments": "{not valid json"}},
        ]}}],
    }
    # Must not raise json.JSONDecodeError; the bad call is skipped → text result.
    out = await agent_mod._openai_with_tools([{"role": "user", "content": "hi"}], "sys", _patched)
    assert out["type"] == "text"


async def test_valid_tool_call_still_parses(_patched) -> None:
    _FakeClient.payload = {
        "choices": [{"message": {"tool_calls": [
            {"id": "1", "function": {"name": "read_persona", "arguments": "{\"x\": 1}"}},
        ]}}],
    }
    out = await agent_mod._openai_with_tools([{"role": "user", "content": "hi"}], "sys", _patched)
    assert out["type"] == "tool_calls"
    assert out["tool_calls"][0]["name"] == "read_persona"
    assert out["tool_calls"][0]["arguments"] == {"x": 1}
