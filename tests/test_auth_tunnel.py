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


def _req(
    headers: dict[str, str] | None = None,
    host: str | None = "127.0.0.1",
    cookies: dict[str, str] | None = None,
) -> Any:
    h = _CIHeaders()
    for key, value in (headers or {}).items():
        h[key.lower()] = value
    client = SimpleNamespace(host=host) if host is not None else None
    return SimpleNamespace(headers=h, client=client, cookies=dict(cookies or {}))


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


# ── cookie auth over the tunnel (how the iOS WebView authenticates) ──


def test_require_auth_accepts_cookie_over_tunnel(monkeypatch: pytest.MonkeyPatch) -> None:
    # The phone's WebView carries the clawed_token cookie on same-origin /api
    # fetches. Over the tunnel (Cf-Ray present) there is no bypass, so the cookie
    # is what must grant access.
    monkeypatch.setenv("EDUAGENT_LOCAL_AUTH_BYPASS", "1")
    token = get_api_token()
    req = _req(headers={"Cf-Ray": "8ab1c2d3e4f5-EWR"}, cookies={"clawed_token": token})
    asyncio.run(require_auth(req))  # must NOT raise


def test_require_auth_rejects_bad_cookie_over_tunnel(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EDUAGENT_LOCAL_AUTH_BYPASS", "1")
    req = _req(headers={"Cf-Ray": "8ab1c2d3e4f5-EWR"}, cookies={"clawed_token": "not-the-token"})
    with pytest.raises(HTTPException) as exc:
        asyncio.run(require_auth(req))
    assert exc.value.status_code == 401


# ── bootstrap cookie attributes (the CSRF / transport guards) ────────


def _bootstrap_client() -> Any:
    from fastapi.testclient import TestClient

    from clawed.api.server import create_app

    return TestClient(create_app())


def test_bootstrap_cookie_is_lax_and_httponly() -> None:
    client = _bootstrap_client()
    token = get_api_token()
    resp = client.post("/api/auth/bootstrap", data={"token": token}, follow_redirects=False)
    assert resp.status_code == 303
    set_cookie = resp.headers.get("set-cookie", "").lower()
    assert "clawed_token=" in set_cookie
    # SameSite=Lax is the CSRF guard (a cross-site POST can't carry the cookie).
    assert "samesite=lax" in set_cookie
    assert "httponly" in set_cookie


def test_bootstrap_cookie_secure_when_forwarded_https() -> None:
    client = _bootstrap_client()
    token = get_api_token()
    # The tunnel terminates TLS at Cloudflare and forwards X-Forwarded-Proto=https.
    resp = client.post(
        "/api/auth/bootstrap",
        data={"token": token},
        headers={"X-Forwarded-Proto": "https"},
        follow_redirects=False,
    )
    assert "secure" in resp.headers.get("set-cookie", "").lower()
