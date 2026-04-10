"""Tests for the rewritten gateway — the brain of Claw-ED."""

from unittest.mock import AsyncMock, patch

import pytest

from clawed.gateway_response import GatewayResponse
from clawed.models import AppConfig


class TestGatewayHandle:
    def setup_method(self):
        from clawed.gateway import Gateway

        # Explicitly use legacy gateway for these tests
        self.gw = Gateway(config=AppConfig(agent_gateway=False))
        # Ensure clean onboard state (no leakage from prior tests)
        self.gw._onboard._state.clear()

    @pytest.mark.asyncio
    async def test_handle_returns_gateway_response(self):
        with patch("clawed._legacy_gateway.has_config", return_value=True):
            with patch.object(self.gw, "_dispatch", new_callable=AsyncMock) as mock_d:
                mock_d.return_value = GatewayResponse(text="Hello!")
                r = await self.gw.handle("hi", "teacher_1")
                assert isinstance(r, GatewayResponse)
                assert r.text == "Hello!"

    @pytest.mark.asyncio
    async def test_new_teacher_enters_onboarding(self):
        with patch("clawed._legacy_gateway.has_config", return_value=False):
            r = await self.gw.handle("hello", "new_teacher")
            assert "subject" in r.text.lower() or "teach" in r.text.lower()

    @pytest.mark.asyncio
    async def test_existing_teacher_skips_onboarding(self):
        with patch("clawed._legacy_gateway.has_config", return_value=True):
            with patch.object(self.gw, "_dispatch", new_callable=AsyncMock) as mock_d:
                mock_d.return_value = GatewayResponse(text="Lesson response")
                r = await self.gw.handle("lesson on fractions", "teacher_1")
                assert r.text == "Lesson response"
                mock_d.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_onboarding_continues_across_messages(self):
        with patch("clawed._legacy_gateway.has_config", return_value=False):
            r1 = await self.gw.handle("hi", "t1")
            assert "subject" in r1.text.lower() or "teach" in r1.text.lower()
            r2 = await self.gw.handle("math", "t1")
            assert "grade" in r2.text.lower()

    @pytest.mark.asyncio
    async def test_callback_handling(self):
        with patch("clawed._legacy_gateway.has_config", return_value=True):
            r = await self.gw.handle_callback("rate:lesson_abc:5", "teacher_1")
            assert isinstance(r, GatewayResponse)


class TestGatewayStats:
    def setup_method(self):
        from clawed.gateway import Gateway

        self.gw = Gateway(config=AppConfig(agent_gateway=False))

    @pytest.mark.asyncio
    async def test_stats_increment(self):
        with patch("clawed._legacy_gateway.has_config", return_value=True):
            with patch.object(self.gw, "_dispatch", new_callable=AsyncMock) as mock_d:
                mock_d.return_value = GatewayResponse(text="ok")
                await self.gw.handle("hello", "t1")
                stats = await self.gw.stats()
                assert stats["messages_today"] >= 1

    @pytest.mark.asyncio
    async def test_initial_stats(self):
        stats = await self.gw.stats()
        assert stats["messages_today"] == 0
        assert "uptime_seconds" in stats


class TestGatewayEventBus:
    def setup_method(self):
        from clawed.gateway import Gateway

        self.gw = Gateway(config=AppConfig(agent_gateway=False))

    @pytest.mark.asyncio
    async def test_events_emitted(self):
        with patch("clawed._legacy_gateway.has_config", return_value=True):
            with patch.object(self.gw, "_dispatch", new_callable=AsyncMock) as mock_d:
                mock_d.return_value = GatewayResponse(text="ok")
                await self.gw.handle("hi", "t1")
                assert not self.gw.event_bus.empty()
