"""Tests for collaborative lesson share — import command, embed snippet, /api/import."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from clawed.api.server import create_app
from clawed.commands.export import _extract_token, export_app
from clawed.database import Database

runner = CliRunner()


# ── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture
def db(tmp_path):
    d = Database(tmp_path / "test.db")
    yield d
    d.close()


@pytest.fixture
def app(db):
    import clawed.api.deps as deps

    old_db = deps._db
    deps._db = db
    test_app = create_app()
    yield test_app
    deps._db = old_db


@pytest.fixture
def client(app):
    return TestClient(app)


def _seed_lesson(db: Database, title: str = "Photosynthesis") -> str:
    tid = db.upsert_teacher("T", "{}")
    uid = db.insert_unit(tid, "U", "Sci", "8", "Cells", "{}")
    return db.insert_lesson(uid, 1, title, json.dumps({"title": title, "objective": "Learn"}))


def _mock_async_client(mock_resp):
    """Build a mock httpx.AsyncClient that works as an async context manager."""
    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    return mock_client


# ── Token extraction ───────────────────────────────────────────────────


class TestTokenExtraction:
    def test_url_with_shared_path(self):
        assert _extract_token("https://example.com/shared/abc123") == "abc123"

    def test_url_with_share_path(self):
        assert _extract_token("https://example.com/share/abc123") == "abc123"

    def test_plain_token(self):
        assert _extract_token("abc123") == "abc123"

    def test_url_with_trailing_slash(self):
        assert _extract_token("https://example.com/share/tok99/") == "tok99"

    def test_empty_token(self):
        assert _extract_token("") == ""

    def test_url_with_deep_path(self):
        assert _extract_token("https://school.io/a/b/c/mytoken") == "mytoken"

    def test_url_preserves_case(self):
        assert _extract_token("https://example.com/share/AbC123") == "AbC123"


# ── GET /share/{token} API ─────────────────────────────────────────────


class TestShareAPI:
    def test_get_share_valid_token(self, client, db):
        lid = _seed_lesson(db)
        lesson = db.get_lesson(lid)
        token = lesson["share_token"]
        resp = client.get(f"/api/share/{token}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Photosynthesis"
        assert data["share_token"] == token
        assert "lesson" in data

    def test_get_share_invalid_token(self, client):
        resp = client.get("/api/share/nonexistent")
        assert resp.status_code == 404

    def test_get_share_returns_lesson_data(self, client, db):
        lid = _seed_lesson(db, "Mitosis")
        lesson = db.get_lesson(lid)
        token = lesson["share_token"]
        resp = client.get(f"/api/share/{token}")
        data = resp.json()
        assert data["lesson"]["objective"] == "Learn"


# ── POST /api/import ───────────────────────────────────────────────────


class TestImportAPI:
    def test_import_with_token(self, client, db):
        lid = _seed_lesson(db, "Original")
        lesson = db.get_lesson(lid)
        token = lesson["share_token"]

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "lesson_id": lid,
            "title": "Original",
            "share_token": token,
            "lesson": {"title": "Original", "objective": "Learn"},
        }

        mock_client = _mock_async_client(mock_resp)

        with patch("clawed.api.routes.export.httpx.AsyncClient", return_value=mock_client):
            resp = client.post(
                "/api/import",
                json={"token": token, "server": "http://localhost:8000"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "lesson_id" in data
        assert data["title"] == "[Imported] Original"

    def test_import_with_url(self, client, db):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "title": "Remote Lesson",
            "lesson": {"title": "Remote Lesson"},
        }

        mock_client = _mock_async_client(mock_resp)

        with patch("clawed.api.routes.export.httpx.AsyncClient", return_value=mock_client):
            resp = client.post(
                "/api/import",
                json={"url": "http://localhost:8000/api/share/tok55"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "[Imported] Remote Lesson"
        # The URL is fetched as provided by the caller
        mock_client.get.assert_called_once()

    def test_import_404(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 404

        mock_client = _mock_async_client(mock_resp)

        with patch("clawed.api.routes.export.httpx.AsyncClient", return_value=mock_client):
            resp = client.post(
                "/api/import",
                json={"token": "bad", "server": "http://localhost:8000"},
            )
        assert resp.status_code == 404

    def test_import_no_token_or_url(self, client):
        resp = client.post("/api/import", json={})
        assert resp.status_code == 400

    def test_import_network_error(self, client):
        import httpx as _httpx

        mock_client = MagicMock()
        mock_client.get = AsyncMock(side_effect=_httpx.ConnectError("fail"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("clawed.api.routes.export.httpx.AsyncClient", return_value=mock_client):
            resp = client.post(
                "/api/import",
                json={"token": "t", "server": "http://localhost:8000"},
            )
        assert resp.status_code == 502


# ── Share command --embed / --copy ─────────────────────────────────────


class TestShareCommand:
    def test_share_embed_flag(self, db):
        lid = _seed_lesson(db, "Embed Test")

        with patch("clawed.commands.export.Database", return_value=db):
            result = runner.invoke(export_app, ["share", "--lesson-id", lid, "--embed"])
        assert result.exit_code == 0
        assert "widget.js" in result.output
        assert "data-token" in result.output
        assert "<script" in result.output

    def test_share_shows_url(self, db):
        lid = _seed_lesson(db, "URL Test")

        with patch("clawed.commands.export.Database", return_value=db):
            result = runner.invoke(export_app, ["share", "--lesson-id", lid])
        assert result.exit_code == 0
        assert "/shared/" in result.output

    def test_share_copy_flag_on_macos(self, db):
        lid = _seed_lesson(db, "Copy Test")

        with (
            patch("clawed.commands.export.Database", return_value=db),
            patch("clawed.commands.export.platform") as mock_platform,
            patch("clawed.commands.export.subprocess") as mock_sub,
        ):
            mock_platform.system.return_value = "Darwin"
            mock_sub.run.return_value = None

            result = runner.invoke(
                export_app,
                ["share", "--lesson-id", lid, "--copy"],
            )
        assert result.exit_code == 0
        mock_sub.run.assert_called_once()

    def test_share_copy_skipped_on_linux(self, db):
        lid = _seed_lesson(db, "Linux Test")

        with (
            patch("clawed.commands.export.Database", return_value=db),
            patch("clawed.commands.export.platform") as mock_platform,
            patch("clawed.commands.export.subprocess") as mock_sub,
        ):
            mock_platform.system.return_value = "Linux"

            result = runner.invoke(
                export_app,
                ["share", "--lesson-id", lid, "--copy"],
            )
        assert result.exit_code == 0
        mock_sub.run.assert_not_called()


# ── Import command (CLI) ───────────────────────────────────────────────


class TestImportCommand:
    def test_import_command_creates_lesson(self, db):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "title": "Shared Lesson",
            "lesson": {"title": "Shared Lesson", "objective": "Teach"},
        }

        with (
            patch("clawed.commands.export.Database", return_value=db),
            patch("httpx.get", return_value=mock_resp),
        ):
            result = runner.invoke(
                export_app,
                ["import", "abc123", "--server", "http://fake:8000"],
            )
        assert result.exit_code == 0
        assert "Imported lesson" in result.output
        assert "[Imported] Shared Lesson" in result.output

    def test_import_command_malformed_url(self, db):
        """Malformed URL that has no scheme still works as a plain token."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "title": "OK",
            "lesson": {"title": "OK"},
        }

        with (
            patch("clawed.commands.export.Database", return_value=db),
            patch("httpx.get", return_value=mock_resp),
        ):
            result = runner.invoke(
                export_app,
                ["import", "just-a-token"],
            )
        assert result.exit_code == 0
        assert "Imported lesson" in result.output
