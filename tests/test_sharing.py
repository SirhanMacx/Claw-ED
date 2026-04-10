"""Tests for shareable lesson URLs."""

import pytest
from fastapi.testclient import TestClient

from clawed.api.server import create_app
from clawed.database import Database


@pytest.fixture
def db(tmp_path):
    """Create a temporary database for testing."""
    db = Database(tmp_path / "test.db")
    yield db
    db.close()


@pytest.fixture
def app(db):
    """Create a test app with the temp database injected."""
    import clawed.api.deps as deps

    old_db = deps._db
    deps._db = db
    test_app = create_app()
    yield test_app
    deps._db = old_db


@pytest.fixture
def client(app):
    """Create a test client."""
    return TestClient(app)


class TestShareDatabase:
    def test_lesson_has_share_token(self, db):
        tid = db.upsert_teacher("T", "{}")
        uid = db.insert_unit(tid, "U", "Sci", "8", "Cells", "{}")
        lid = db.insert_lesson(uid, 1, "Lesson 1", '{"title": "Lesson 1"}')
        lesson = db.get_lesson(lid)
        assert lesson is not None
        assert lesson["share_token"] is not None
        assert len(lesson["share_token"]) == 32  # UUID hex

    def test_get_lesson_by_token(self, db):
        tid = db.upsert_teacher("T", "{}")
        uid = db.insert_unit(tid, "U", "Sci", "8", "Cells", "{}")
        lid = db.insert_lesson(uid, 1, "Lesson 1", '{"title": "Lesson 1"}')
        lesson = db.get_lesson(lid)
        token = lesson["share_token"]
        found = db.get_lesson_by_token(token)
        assert found is not None
        assert found["id"] == lid

    def test_get_lesson_by_invalid_token(self, db):
        result = db.get_lesson_by_token("nonexistent-token")
        assert result is None


class TestShareAPI:
    def test_create_share_link(self, client, db):
        tid = db.upsert_teacher("T", "{}")
        uid = db.insert_unit(tid, "U", "Sci", "8", "Cells", "{}")
        lid = db.insert_lesson(uid, 1, "Lesson 1", '{"title": "Lesson 1"}')
        resp = client.post(f"/api/lessons/{lid}/share")
        assert resp.status_code == 200
        data = resp.json()
        assert "share_url" in data
        assert "token" in data
        assert data["share_url"].startswith("/shared/")

    def test_create_share_link_not_found(self, client):
        resp = client.post("/api/lessons/nonexistent/share")
        assert resp.status_code == 404

    def test_get_shared_lesson(self, client, db):
        tid = db.upsert_teacher("T", "{}")
        uid = db.insert_unit(tid, "U", "Sci", "8", "Cells", "{}")
        lid = db.insert_lesson(uid, 1, "Lesson 1", '{"title": "Lesson 1"}')
        lesson = db.get_lesson(lid)
        token = lesson["share_token"]
        resp = client.get(f"/api/share/{token}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Lesson 1"
        assert data["share_token"] == token

    def test_shared_page_html(self, client, db):
        tid = db.upsert_teacher("T", "{}")
        uid = db.insert_unit(tid, "U", "Sci", "8", "Cells", "{}")
        lid = db.insert_lesson(uid, 1, "Lesson 1", '{"title": "Lesson 1"}')
        lesson = db.get_lesson(lid)
        token = lesson["share_token"]
        resp = client.get(f"/shared/{token}")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_shared_page_not_found(self, client):
        resp = client.get("/shared/nonexistent-token")
        assert resp.status_code in (200, 404)  # May return HTML error page or 404
        assert "not found" in resp.text.lower()
