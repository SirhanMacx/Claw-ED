"""Security regression tests for the public-tunnel auth boundary.

The agent binds loopback only and the public ingress is the named Cloudflare
tunnel. cloudflared connects to the agent *from* 127.0.0.1, so without care the
local-auth bypass would treat every tunnel request as local and turn the public
URL into an open door. The guard: Cloudflare stamps proxied requests with a
``Cf-Ray`` header that genuine loopback traffic never has, so the bypass keys on
its ABSENCE. These tests pin that behavior down.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException

from clawed.api.deps import get_api_token, local_bypass_ok, require_auth


class _CIHeaders(dict):  # type: ignore[type-arg]
    """Minimal case-insensitive headers, like Starlette's Headers.get()."""

    def get(self, key: str, default: Any = None) -> Any:
        return dict.get(self, key.lower(), default)


def _req(headers: dict[str, str] | None = None, host: str | None = "127.0.0.1") -> Any:
    h = _CIHeaders()
    for key, value in (headers or {}).items():
        h[key.lower()] = value
    client = SimpleNamespace(host=host) if host is not None else None
    return SimpleNamespace(headers=h, client=client)


# ── local_bypass_ok ──────────────────────────────────────────────────


def test_bypass_when_genuinely_local(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EDUAGENT_LOCAL_AUTH_BYPASS", "1")
    assert local_bypass_ok(_req()) is True


def test_no_bypass_for_tunnel_traffic(monkeypatch: pytest.MonkeyPatch) -> None:
    # Carries Cf-Ray → came through Cloudflare → never bypass, even though the
    # connector reaches the agent from loopback.
    monkeypatch.setenv("EDUAGENT_LOCAL_AUTH_BYPASS", "1")
    assert local_bypass_ok(_req(headers={"Cf-Ray": "8ab1c2d3e4f5-EWR"})) is False


def test_no_bypass_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EDUAGENT_LOCAL_AUTH_BYPASS", raising=False)
    assert local_bypass_ok(_req()) is False


def test_no_bypass_for_nonlocal_ip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EDUAGENT_LOCAL_AUTH_BYPASS", "1")
    assert local_bypass_ok(_req(host="203.0.113.9")) is False


# ── require_auth end-to-end ──────────────────────────────────────────


def test_require_auth_rejects_tunnel_without_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EDUAGENT_LOCAL_AUTH_BYPASS", "1")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(require_auth(_req(headers={"Cf-Ray": "8ab1c2d3e4f5-EWR"})))
    assert exc.value.status_code == 401


def test_require_auth_accepts_tunnel_with_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EDUAGENT_LOCAL_AUTH_BYPASS", "1")
    token = get_api_token()
    headers = {"Cf-Ray": "8ab1c2d3e4f5-EWR", "Authorization": f"Bearer {token}"}
    # Must NOT raise — a valid token over the tunnel is accepted.
    asyncio.run(require_auth(_req(headers=headers)))


def test_require_auth_rejects_tunnel_with_bad_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EDUAGENT_LOCAL_AUTH_BYPASS", "1")
    headers = {"Cf-Ray": "8ab1c2d3e4f5-EWR", "Authorization": "Bearer not-the-real-token"}
    with pytest.raises(HTTPException) as exc:
        asyncio.run(require_auth(_req(headers=headers)))
    assert exc.value.status_code == 401


def test_require_auth_bypasses_genuine_local(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EDUAGENT_LOCAL_AUTH_BYPASS", "1")
    # No Cf-Ray, loopback → genuine local → bypass, no token needed.
    asyncio.run(require_auth(_req()))
