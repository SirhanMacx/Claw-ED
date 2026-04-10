"""Security boundary tests — auth, rate limiting, access control.

Proves the security model works, not just that routes exist.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from clawed.api.server import create_app
from clawed.database import Database


@pytest.fixture
def db(tmp_path):
    d = Database(tmp_path / "test.db")
    yield d
    d.close()


@pytest.fixture
def app(db, monkeypatch):
    monkeypatch.setattr("clawed.api.deps._db", db)
    a = create_app()
    old = __import__("clawed.api.deps", fromlist=["_db"])._db
    __import__("clawed.api.deps", fromlist=["set_db"]).set_db(db)
    yield a
    __import__("clawed.api.deps", fromlist=["set_db"]).set_db(old)


@pytest.fixture
def unauthed_client(app, monkeypatch):
    """Client WITHOUT localhost bypass — tests real auth."""
    monkeypatch.delenv("EDUAGENT_LOCAL_AUTH_BYPASS", raising=False)
    return TestClient(app)


@pytest.fixture
def authed_client(app, monkeypatch):
    """Client WITH valid auth token."""
    monkeypatch.delenv("EDUAGENT_LOCAL_AUTH_BYPASS", raising=False)
    from clawed.api.deps import get_api_token

    token = get_api_token()
    client = TestClient(app)
    client.headers["Authorization"] = f"Bearer {token}"
    return client


@pytest.fixture
def bypass_client(app, monkeypatch):
    """Client with localhost bypass enabled."""
    monkeypatch.setenv("EDUAGENT_LOCAL_AUTH_BYPASS", "1")
    return TestClient(app)


class TestHealthPublic:
    """Health liveness endpoint should be public."""

    def test_health_no_auth(self, unauthed_client):
        resp = unauthed_client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_health_has_version(self, unauthed_client):
        resp = unauthed_client.get("/api/health")
        assert "version" in resp.json()


class TestAuthRequired:
    """Protected routes return 401 without token."""

    @pytest.mark.parametrize(
        "route",
        [
            "/api/settings",
            "/api/health/diagnostics",
        ],
    )
    def test_get_routes_reject_no_auth(self, unauthed_client, route):
        resp = unauthed_client.get(route)
        assert resp.status_code == 401

    @pytest.mark.parametrize(
        "route,body",
        [
            ("/api/settings", {"provider": "ollama"}),
            ("/api/settings/clear-content", {}),
            ("/api/settings/reset", {}),
            ("/api/gateway/chat", {"message": "hello"}),
        ],
    )
    def test_post_routes_reject_no_auth(self, unauthed_client, route, body):
        resp = unauthed_client.post(route, json=body)
        assert resp.status_code == 401


class TestAuthAccepted:
    """Protected routes accept valid Bearer token."""

    def test_settings_with_token(self, authed_client):
        resp = authed_client.get("/api/settings")
        assert resp.status_code == 200

    def test_health_diagnostics_with_token(self, authed_client):
        resp = authed_client.get("/api/health/diagnostics")
        # May fail if no LLM configured, but should not be 401
        assert resp.status_code != 401


class TestInvalidToken:
    """Invalid tokens are rejected."""

    def test_wrong_token_rejected(self, unauthed_client):
        unauthed_client.headers["Authorization"] = "Bearer wrong-token-123"
        resp = unauthed_client.get("/api/settings")
        assert resp.status_code == 401

    def test_missing_bearer_prefix(self, unauthed_client):
        from clawed.api.deps import get_api_token

        unauthed_client.headers["Authorization"] = get_api_token()
        resp = unauthed_client.get("/api/settings")
        assert resp.status_code == 401


class TestBypassDisabledByDefault:
    """Verify bypass is NOT active in unauthed_client tests."""

    def test_bypass_env_not_set(self, unauthed_client):
        import os

        assert os.environ.get("EDUAGENT_LOCAL_AUTH_BYPASS") != "1", "Bypass should be disabled for unauthed tests"

    def test_testclient_still_rejected_without_bypass(self, unauthed_client):
        """Even though TestClient sends from 'testclient' host,
        auth is enforced when bypass env var is not set."""
        resp = unauthed_client.get("/api/settings")
        assert resp.status_code == 401


class TestLocalhostBypass:
    """Localhost bypass allows access without token ONLY when enabled."""

    def test_bypass_allows_settings(self, bypass_client):
        resp = bypass_client.get("/api/settings")
        assert resp.status_code == 200

    def test_bypass_allows_health_diagnostics(self, bypass_client):
        resp = bypass_client.get("/api/health/diagnostics")
        assert resp.status_code != 401

    def test_bypass_requires_env_var(self, unauthed_client):
        """Without EDUAGENT_LOCAL_AUTH_BYPASS=1, bypass does not work."""
        resp = unauthed_client.get("/api/settings")
        assert resp.status_code == 401


class TestRateLimiting:
    """Rate limiter returns 429 after threshold."""

    def test_rate_limit_triggers(self, bypass_client):
        # Gateway chat is limited to 30/minute
        # Send 35 rapid requests — some should be rejected
        statuses = []
        for _ in range(35):
            resp = bypass_client.post(
                "/api/gateway/chat",
                json={"message": "test"},
            )
            statuses.append(resp.status_code)

        assert 429 in statuses, f"Expected 429 in responses but got: {set(statuses)}"


class TestPublicShareRoutes:
    """Share routes should be accessible without auth."""

    def test_share_returns_content_or_404(self, unauthed_client):
        resp = unauthed_client.get("/api/share/nonexistent-token")
        # Should be 404 (not found) not 401 (unauthorized)
        assert resp.status_code in (200, 404)
        assert resp.status_code != 401


class TestImportSSRF:
    """Import endpoint blocks non-localhost URLs."""

    def test_external_url_blocked(self, bypass_client):
        resp = bypass_client.post(
            "/api/import",
            json={"url": "https://evil.com/steal-data"},
        )
        assert resp.status_code == 403
        assert "not allowed" in resp.json().get("error", "").lower()

    def test_localhost_url_allowed_shape(self, bypass_client):
        # This will fail to actually fetch, but should not be 403
        resp = bypass_client.post(
            "/api/import",
            json={"url": "http://localhost:9999/fake"},
        )
        # Should be 502 (fetch failed) not 403 (blocked)
        assert resp.status_code != 403
