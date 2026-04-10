"""Tests for quality review fail-closed behavior."""

from unittest.mock import AsyncMock

import pytest


class TestReviewFailsClosed:
    @pytest.mark.asyncio
    async def test_review_fails_closed_on_llm_error(self):
        """review_lesson_package returns passed=False when generate() raises."""
        from clawed.llm import LLMClient

        client = LLMClient.__new__(LLMClient)
        client.generate = AsyncMock(side_effect=ConnectionError("network down"))
        result = await client.review_lesson_package(
            "lesson json",
            True,
            True,
            True,
        )
        assert result["passed"] is False
        assert any("ConnectionError" in i for i in result["issues"])

    @pytest.mark.asyncio
    async def test_review_fails_closed_on_missing_key(self):
        """Result without 'passed' key returns passed=False."""
        from clawed.llm import LLMClient

        client = LLMClient.__new__(LLMClient)
        client.generate = AsyncMock(return_value='{"result": "ok"}')
        result = await client.review_lesson_package(
            "lesson json",
            True,
            True,
            True,
        )
        assert result["passed"] is False
        assert any("missing" in i.lower() for i in result["issues"])

    @pytest.mark.asyncio
    async def test_review_passes_on_valid_response(self):
        """Valid LLM response with passed=True is returned."""
        from clawed.llm import LLMClient

        client = LLMClient.__new__(LLMClient)
        client.generate = AsyncMock(
            return_value='{"passed": true, "issues": []}',
        )
        result = await client.review_lesson_package(
            "lesson json",
            True,
            True,
            True,
        )
        assert result["passed"] is True
