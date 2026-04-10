"""Fake LLM for deterministic testing of the agent loop."""

from __future__ import annotations

from typing import Any


class FakeLLMExhaustedError(Exception):
    """All scripted FakeLLM responses have been consumed."""


class FakeLLM:
    """Deterministic LLM responses for testing agent behavior."""

    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self._responses = list(responses)
        self._index = 0

    async def generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        system: str = "",
    ) -> dict[str, Any]:
        """Return the next scripted response."""
        if self._index >= len(self._responses):
            raise FakeLLMExhaustedError("FakeLLM responses exhausted")
        resp = self._responses[self._index]
        self._index += 1
        return resp
