"""Tests for the Hermes Agent transport."""

from unittest.mock import AsyncMock, patch

import pytest

from clawed.transports.hermes import _get_gateway, handle_callback, handle_message


class TestHermesTransport:
    @pytest.mark.asyncio
    async def test_handle_message_returns_string(self):
        with patch("clawed.transports.hermes._get_gateway") as mock_gw_fn:
            mock_gw = AsyncMock()
            mock_gw_fn.return_value = mock_gw
            from clawed.gateway_response import GatewayResponse

            mock_gw.handle.return_value = GatewayResponse(text="Here's your lesson!")
            result = await handle_message("lesson on fractions", "teacher_1")
            assert result == "Here's your lesson!"
            mock_gw.handle.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_handle_callback_returns_string(self):
        with patch("clawed.transports.hermes._get_gateway") as mock_gw_fn:
            mock_gw = AsyncMock()
            mock_gw_fn.return_value = mock_gw
            from clawed.gateway_response import GatewayResponse

            mock_gw.handle_callback.return_value = GatewayResponse(text="Rated 5/5")
            result = await handle_callback("rate:abc:5", "teacher_1")
            assert result == "Rated 5/5"

    @pytest.mark.asyncio
    async def test_handle_message_with_files(self):
        from pathlib import Path

        with patch("clawed.transports.hermes._get_gateway") as mock_gw_fn:
            mock_gw = AsyncMock()
            mock_gw_fn.return_value = mock_gw
            from clawed.gateway_response import GatewayResponse

            mock_gw.handle.return_value = GatewayResponse(text="Ingested 3 docs")
            result = await handle_message("ingest", "t1", files=[Path("/tmp/a.pdf")])
            assert "Ingested" in result

    def test_gateway_singleton(self):
        import clawed.transports.hermes as m

        m._gateway = None
        gw1 = _get_gateway()
        gw2 = _get_gateway()
        assert gw1 is gw2
        m._gateway = None  # cleanup


class TestBackwardCompat:
    """Verify the openclaw.py shim still works."""

    def test_openclaw_imports_redirect(self):
        from clawed.transports.hermes import handle_message as hm_new
        from clawed.transports.openclaw import handle_message as hm_old

        assert hm_old is hm_new

    def test_openclaw_plugin_imports_redirect(self):
        from clawed.hermes_plugin import get_last_lesson_id as new
        from clawed.openclaw_plugin import get_last_lesson_id as old

        assert old is new
