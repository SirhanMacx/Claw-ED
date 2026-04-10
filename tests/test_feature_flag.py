"""Tests for feature flag routing between legacy and agent gateway."""

from clawed.models import AppConfig


class TestFeatureFlag:
    def test_flag_defaults_to_true(self):
        cfg = AppConfig()
        assert cfg.agent_gateway is True

    def test_legacy_gateway_when_flag_off(self):
        from clawed.gateway import Gateway

        gw = Gateway(config=AppConfig(agent_gateway=False))
        assert gw.__class__.__module__ == "clawed._legacy_gateway"

    def test_shim_reexports_compat_names(self):
        from clawed.gateway import ActivityEvent, EduAgentGateway, GatewayStats

        assert EduAgentGateway is not None
        assert ActivityEvent is not None
        assert GatewayStats is not None


class TestFlagOffParity:
    """With flag OFF, everything works exactly as before."""

    def test_gateway_is_legacy_class(self):
        from clawed.gateway import Gateway

        gw = Gateway(config=AppConfig(agent_gateway=False))
        assert gw.__class__.__name__ == "Gateway"
        assert gw.__class__.__module__ == "clawed._legacy_gateway"

    async def test_handle_returns_response(self):
        from unittest.mock import AsyncMock, patch

        from clawed.gateway import Gateway
        from clawed.gateway_response import GatewayResponse

        gw = Gateway(config=AppConfig(agent_gateway=False))
        # Patch onboarding + config checks so we reach _dispatch
        with (
            patch.object(gw._onboard, "is_onboarding", return_value=False),
            patch("clawed._legacy_gateway.has_config", return_value=True),
            patch.object(gw, "_dispatch", new_callable=AsyncMock) as mock,
        ):
            mock.return_value = GatewayResponse(text="Legacy response")
            result = await gw.handle("hi", "t1")
        assert result.text == "Legacy response"

    async def test_handle_callback_works(self):
        from clawed.gateway import Gateway

        gw = Gateway(config=AppConfig())
        result = await gw.handle_callback("unknown:action", "t1")
        assert result is not None


class TestFlagOnAgent:
    """With flag ON, the agent gateway handles messages."""

    def test_gateway_is_agent_class(self):
        from clawed.gateway import Gateway

        gw = Gateway(config=AppConfig(agent_gateway=True))
        assert gw.__class__.__module__ == "clawed.agent_core.core"

    async def test_agent_handle_with_fake_llm(self):
        from unittest.mock import patch

        from clawed.agent_core.fake_llm import FakeLLM
        from clawed.gateway import Gateway

        llm = FakeLLM([{"type": "text", "content": "Agent response!"}])
        gw = Gateway(config=AppConfig(agent_gateway=True), llm=llm)
        # Patch onboarding + config checks so we reach the agent loop
        with (
            patch.object(gw._onboard, "is_onboarding", return_value=False),
            patch("clawed.agent_core.core.has_config", return_value=True),
            patch("clawed.agent_core.core.has_teacher_profile", return_value=True),
        ):
            result = await gw.handle("hello", "t1")
        assert result.text == "Agent response!"

    async def test_agent_callback_approval(self):
        from clawed.gateway import Gateway

        gw = Gateway(config=AppConfig(agent_gateway=True))
        result = await gw.handle_callback("approve:nonexistent", "t1")
        assert result is not None
        assert result.text  # should have some response text

    async def test_agent_stats(self):
        from clawed.gateway import Gateway

        gw = Gateway(config=AppConfig(agent_gateway=True))
        s = await gw.stats()
        assert isinstance(s, dict)
        assert "messages_today" in s

    async def test_fallback_on_llm_error(self):
        """When the LLM adapter is broken, the gateway should not crash."""
        from unittest.mock import patch

        from clawed.agent_core.fake_llm import FakeLLM
        from clawed.gateway import Gateway

        # Empty FakeLLM will raise on first call
        llm = FakeLLM([])
        gw = Gateway(config=AppConfig(agent_gateway=True), llm=llm)
        # Patch onboarding + config checks so we reach the agent loop
        with (
            patch.object(gw._onboard, "is_onboarding", return_value=False),
            patch("clawed.agent_core.core.has_config", return_value=True),
            patch("clawed.agent_core.core.has_teacher_profile", return_value=True),
        ):
            result = await gw.handle("hello", "t1")
        # Should get some response (error fallback), not crash
        assert result is not None
        assert result.text
