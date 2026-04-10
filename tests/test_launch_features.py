"""Tests for demo mode and shareable URLs."""

import json
from pathlib import Path

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


# ── Feature 1: Landing Page ──────────────────────────────────────────


# ── Demo Mode ────────────────────────────────────────────────────────


class TestDemoMode:
    def test_demo_files_exist(self):
        demo_dir = Path(__file__).parent.parent / "clawed" / "demo"
        assert (demo_dir / "demo_lesson_social_studies_g8.json").exists()
        assert (demo_dir / "demo_lesson_science_g6.json").exists()
        assert (demo_dir / "demo_unit_plan.json").exists()
        assert (demo_dir / "demo_assessment.json").exists()

    def test_demo_lesson_social_studies_valid_json(self):
        demo_dir = Path(__file__).parent.parent / "clawed" / "demo"
        data = json.loads((demo_dir / "demo_lesson_social_studies_g8.json").read_text())
        assert data["subject"] == "Social Studies"
        assert data["grade_level"] == "8"
        assert "objective" in data
        assert "do_now" in data
        assert "exit_ticket" in data
        assert "differentiation" in data

    def test_demo_lesson_science_valid_json(self):
        demo_dir = Path(__file__).parent.parent / "clawed" / "demo"
        data = json.loads((demo_dir / "demo_lesson_science_g6.json").read_text())
        assert data["subject"] == "Science"
        assert data["grade_level"] == "6"
        assert "objective" in data

    def test_demo_unit_plan_valid_json(self):
        demo_dir = Path(__file__).parent.parent / "clawed" / "demo"
        data = json.loads((demo_dir / "demo_unit_plan.json").read_text())
        assert "daily_lessons" in data
        assert len(data["daily_lessons"]) >= 3

    def test_demo_assessment_valid_json(self):
        demo_dir = Path(__file__).parent.parent / "clawed" / "demo"
        data = json.loads((demo_dir / "demo_assessment.json").read_text())
        assert data["assessment_type"] == "dbq"
        assert "documents" in data
        assert len(data["documents"]) >= 5
        assert "rubric" in data

    def test_load_demo(self):
        from clawed.demo import load_demo

        data = load_demo("lesson_social_studies_g8")
        assert data["title"] == "The Causes of the American Revolution"

    def test_load_all_demos(self):
        from clawed.demo import load_all_demos

        demos = load_all_demos()
        assert len(demos) >= 4
        assert "lesson_social_studies_g8" in demos
        assert "lesson_science_g6" in demos
        assert "unit_plan" in demos
        assert "assessment" in demos

    def test_list_demo_files(self):
        from clawed.demo import list_demo_files

        files = list_demo_files()
        assert len(files) >= 4

    def test_is_demo_mode_without_keys(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        from clawed.demo import is_demo_mode

        # May or may not be demo mode depending on config, but shouldn't crash
        result = is_demo_mode()
        assert isinstance(result, bool)

    def test_demo_response_in_llm(self):
        from clawed.llm import LLMClient

        # Test the static _demo_response method
        response = LLMClient._demo_response("Generate a social studies lesson")
        data = json.loads(response)
        assert "title" in data

    def test_demo_response_science(self):
        from clawed.llm import LLMClient

        response = LLMClient._demo_response("Create a science lesson about water")
        data = json.loads(response)
        assert data["subject"] == "Science"

    def test_demo_response_assessment(self):
        from clawed.llm import LLMClient

        response = LLMClient._demo_response("Generate a DBQ assessment")
        data = json.loads(response)
        assert data["assessment_type"] == "dbq"


# ── Shareable Lesson URLs ─────────────────────────────────────────────


class TestShareableURLs:
    def test_share_token_on_insert(self, db):
        tid = db.upsert_teacher("T", "{}")
        uid = db.insert_unit(tid, "U", "S", "8", "T", "{}")
        lid = db.insert_lesson(uid, 1, "L1", "{}")
        lesson = db.get_lesson(lid)
        assert lesson["share_token"] is not None
        assert len(lesson["share_token"]) == 32

    def test_get_by_share_token(self, db):
        tid = db.upsert_teacher("T", "{}")
        uid = db.insert_unit(tid, "U", "S", "8", "T", "{}")
        lid = db.insert_lesson(uid, 1, "L1", '{"title": "Test"}')
        lesson = db.get_lesson(lid)
        by_token = db.get_lesson_by_token(lesson["share_token"])
        assert by_token is not None
        assert by_token["id"] == lid

    def test_share_api_create(self, client, db):
        tid = db.upsert_teacher("T", "{}")
        uid = db.insert_unit(tid, "U", "S", "8", "T", "{}")
        lid = db.insert_lesson(uid, 1, "L1", '{"title": "Hello"}')
        resp = client.post(f"/api/lessons/{lid}/share")
        assert resp.status_code == 200
        data = resp.json()
        assert "share_url" in data
        assert "/shared/" in data["share_url"]
        assert "token" in data

    def test_share_api_lesson_not_found(self, client):
        resp = client.post("/api/lessons/nonexistent/share")
        assert resp.status_code == 404

    def test_shared_page_renders(self, client, db):
        from clawed.models import DailyLesson

        tid = db.upsert_teacher("T", '{"name": "T"}')
        uid = db.insert_unit(tid, "U", "S", "8", "T", "{}")
        lesson = DailyLesson(title="Shared Test", lesson_number=1, objective="Test sharing")
        lid = db.insert_lesson(uid, 1, "Shared Test", lesson.model_dump_json())
        row = db.get_lesson(lid)
        resp = client.get(f"/shared/{row['share_token']}")
        assert resp.status_code == 200
        assert "Shared Test" in resp.text

    def test_shared_page_404(self, client):
        resp = client.get("/shared/nonexistent")
        assert resp.status_code == 404

    def test_share_api_json(self, client, db):
        tid = db.upsert_teacher("T", "{}")
        uid = db.insert_unit(tid, "U", "S", "8", "T", "{}")
        lid = db.insert_lesson(uid, 1, "L1", '{"title": "JSON Test"}')
        lesson = db.get_lesson(lid)
        resp = client.get(f"/api/share/{lesson['share_token']}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "L1"
        assert data["lesson"]["title"] == "JSON Test"
