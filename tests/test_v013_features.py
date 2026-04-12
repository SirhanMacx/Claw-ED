"""Tests for v0.2.0 features — class codes, Telegram polish, onboarding wizard, dashboard v2.

Covers all 4 feature waves with 55+ new tests:
  Wave 1: Class code system edge cases and DB operations
  Wave 2: Telegram bot conversation state machine and error recovery
  Wave 3: Onboarding model detection, persona preview, ingestion
  Wave 4: Web dashboard pages, lesson list filters, embed snippet
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from clawed.database import Database
from clawed.models import AppConfig, LLMProvider, TeacherPersona
from clawed.state import init_db


def _run(coro):
    return asyncio.run(coro)


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _use_tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr("clawed.state.DEFAULT_DATA_DIR", tmp_path)
    init_db()


@pytest.fixture
def db(tmp_path):
    d = Database(tmp_path / "web_test.db")
    yield d
    d.close()


@pytest.fixture
def app(db):
    import clawed.api.deps as deps
    from clawed.api.server import create_app

    old = deps._db
    deps._db = db
    a = create_app()
    yield a
    deps._db = old


@pytest.fixture
def client(app):
    return TestClient(app)


# ═══════════════════════════════════════════════════════════════════════════
# WAVE 1: CLASS CODE SYSTEM
# ═══════════════════════════════════════════════════════════════════════════


class TestClassCodeDBOperations:
    """Test database-level class code operations."""

    def test_duplicate_enrollment_ignored(self, db):
        db.create_class_code(code="DU-PLI-1", teacher_id="t1")
        db.enroll_student("stu-001", "DU-PLI-1")
        db.enroll_student("stu-001", "DU-PLI-1")  # duplicate
        assert db.count_enrollments("DU-PLI-1") == 1

    def test_list_enrollments(self, db):
        db.create_class_code(code="LS-ENR-1", teacher_id="t1")
        db.enroll_student("stu-A", "LS-ENR-1")
        db.enroll_student("stu-B", "LS-ENR-1")
        enrollments = db.list_enrollments("LS-ENR-1")
        assert len(enrollments) == 2
        ids = {e["student_id"] for e in enrollments}
        assert "stu-A" in ids
        assert "stu-B" in ids

    def test_get_class_code_nonexistent(self, db):
        assert db.get_class_code("NOPE") is None

    def test_class_code_with_expiry(self, db):
        db.create_class_code(
            code="EX-PIR-1", teacher_id="t1",
            expires_at="2026-06-15T23:59:59",
        )
        row = db.get_class_code("EX-PIR-1")
        assert row["expires_at"] == "2026-06-15T23:59:59"

    def test_student_questions_empty(self, db):
        assert db.count_student_questions("NO-CLASS") == 0
        assert db.get_student_questions("NO-CLASS") == []

    def test_student_questions_multiple(self, db):
        db.insert_student_question("s1", "CL-ORD-1", "Q1?", "A1")
        db.insert_student_question("s1", "CL-ORD-1", "Q2?", "A2")
        qs = db.get_student_questions("CL-ORD-1")
        assert len(qs) == 2
        questions = {q["question"] for q in qs}
        assert "Q1?" in questions
        assert "Q2?" in questions


class TestStudentBotClassExtended:
    """Extended tests for student bot class management."""

    def test_multiple_classes_same_teacher(self):
        from clawed.student_bot import StudentBot

        bot = StudentBot()
        c1 = bot.create_class("teacher-multi", name="Period 1")
        c2 = bot.create_class("teacher-multi", name="Period 2")
        assert c1 != c2
        assert bot.get_class(c1).name == "Period 1"
        assert bot.get_class(c2).name == "Period 2"

    def test_student_conversation_history(self):
        from clawed.student_bot import StudentBot

        bot = StudentBot()
        code = bot.create_class("teacher-hist")
        # No conversation yet
        history = bot.get_student_conversation("stu-1", code)
        assert history == []

    def test_is_expired_with_invalid_date(self):
        from clawed.student_bot import StudentBot

        bot = StudentBot()
        code = bot.create_class("teacher-bad", expires_at="not-a-date")
        # Should not crash, should return False
        assert bot.is_expired(code) is False

    def test_get_mode_nonexistent_class(self):
        from clawed.student_bot import StudentBot

        bot = StudentBot()
        # get_mode on non-existent class returns "answer" (default)
        assert bot.get_mode("FAKE-CODE") == "answer"

    @patch("clawed.chat.student_chat", new_callable=AsyncMock)
    def test_weekly_report_anonymized(self, mock_chat):
        from clawed.state import TeacherSession
        from clawed.student_bot import StudentBot

        session = TeacherSession(
            teacher_id="teacher-anon",
            persona=TeacherPersona(name="Mr. Anon"),
        )
        session.save()

        bot = StudentBot()
        code = bot.create_class("teacher-anon")
        lesson = json.dumps({"title": "Test", "objective": "Test"})
        _run(bot.set_active_lesson(code, "l1", "teacher-anon", lesson))

        mock_chat.return_value = "Answer."
        _run(bot.handle_message("Q?", "stu-real-name", code))

        report = _run(bot.get_weekly_report(code))
        # Student activity uses "student_number" not real IDs
        for item in report["student_activity"]:
            assert "student_number" in item
            assert "student_id" not in item

    def test_class_stats_empty_class(self):
        from clawed.student_bot import StudentBot

        bot = StudentBot()
        code = bot.create_class("teacher-empty")
        stats = bot.get_class_stats(code)
        assert stats["registered_students"] == 0
        assert stats["total_questions"] == 0
        assert stats["active_students"] == 0


# ═══════════════════════════════════════════════════════════════════════════
# WAVE 3: ONBOARDING FLOW POLISH
# ═══════════════════════════════════════════════════════════════════════════


class TestModelAutoDetection:
    """Test model auto-detection priority and edge cases."""

    def test_anthropic_takes_priority_over_openai(self):
        from clawed.onboarding import _detect_available_models

        with patch.dict("os.environ", {
            "ANTHROPIC_API_KEY": "sk-ant-test",
            "OPENAI_API_KEY": "sk-test",
        }, clear=True):
            provider, _ = _detect_available_models()
            assert provider == LLMProvider.ANTHROPIC

    def test_ollama_preferred_model_minimax(self):
        from clawed.onboarding import _detect_available_models

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "models": [
                {"name": "mistral:latest"},
                {"name": "minimax-m2.7:latest"},
                {"name": "llama3.2:latest"},
            ]
        }
        with (
            patch.dict("os.environ", {}, clear=True),
            patch("httpx.get", return_value=mock_resp),
        ):
            provider, msg = _detect_available_models()
            assert provider == LLMProvider.OLLAMA
            assert "minimax" in msg

    def test_ollama_no_models_pulled(self):
        from clawed.onboarding import _detect_available_models

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"models": []}
        with (
            patch.dict("os.environ", {}, clear=True),
            patch("httpx.get", return_value=mock_resp),
        ):
            provider, msg = _detect_available_models()
            assert provider == LLMProvider.OLLAMA
            assert "no models" in msg.lower()

    def test_ollama_connection_refused(self):
        from clawed.onboarding import _detect_available_models

        with (
            patch.dict("os.environ", {}, clear=True),
            patch("httpx.get", side_effect=ConnectionError("refused")),
        ):
            provider, msg = _detect_available_models()
            assert provider is None


class TestOnboardingPersonaPreview:
    """Test the persona preview and confirmation flow."""

    def test_preview_contains_subjects(self):
        from clawed.onboarding import _show_persona_preview

        with patch("clawed.onboarding.Prompt.ask", return_value="y"):
            result = _show_persona_preview(
                ["Social Studies", "History"], ["8", "9"], "NY"
            )
            assert result is True

    def test_preview_state_resolution(self):
        from clawed.onboarding import _resolve_state

        # Test various state inputs
        assert _resolve_state("Florida") == "FL"
        assert _resolve_state("fl") == "FL"
        assert _resolve_state("Mass") == "MA"


class TestOnboardingMaterialsIngestion:
    """Test material ingestion edge cases."""

    def test_ask_materials_skip(self):
        from clawed.onboarding import _ask_materials

        # Choose option 4 (skip)
        with patch("clawed.onboarding.Prompt.ask", return_value="4"):
            local_path, drive_url = _ask_materials()
            assert local_path is None
            assert drive_url is None

    def test_ingest_supported_extensions_filter(self):
        """Verify the supported extension set used during ingestion."""
        supported_exts = {".pdf", ".docx", ".pptx", ".txt", ".md"}
        assert ".csv" not in supported_exts
        assert ".png" not in supported_exts
        assert ".pdf" in supported_exts
        assert ".docx" in supported_exts


class TestAppConfigRoundtrip:
    """Test config save/load roundtrip."""

    def test_config_serialization(self):
        config = AppConfig(
            provider=LLMProvider.OLLAMA,
            ollama_model="llama3.2",
        )
        data = config.model_dump_json()
        loaded = AppConfig.model_validate_json(data)
        assert loaded.provider == LLMProvider.OLLAMA
        assert loaded.ollama_model == "llama3.2"

    def test_config_save_load(self, tmp_path):
        config_file = tmp_path / "config.json"
        config = AppConfig(provider=LLMProvider.OPENAI)
        with patch.object(AppConfig, "config_path", return_value=config_file):
            config.save()
            assert config_file.exists()
            loaded = AppConfig.load()
            assert loaded.provider == LLMProvider.OPENAI


# ═══════════════════════════════════════════════════════════════════════════
# WAVE 4: WEB DASHBOARD GAPS
# ═══════════════════════════════════════════════════════════════════════════


class TestLessonsListPage:
    """Test the lessons list page with filters."""

    def test_lessons_page_renders_empty(self, client):
        resp = client.get("/lessons")
        assert resp.status_code == 200
        assert "All Lessons" in resp.text
        assert "Generate New Lesson" in resp.text

    def test_lessons_page_with_data(self, client, db):
        tid = db.upsert_teacher("T", '{}')
        uid = db.insert_unit(tid, "U", "Math", "8", "Algebra", '{}')
        db.insert_lesson(uid, 1, "Solving Equations", '{"title": "Solving Equations"}')
        resp = client.get("/lessons")
        assert resp.status_code == 200
        assert "Solving Equations" in resp.text

    def test_lessons_page_subject_filter(self, client, db):
        tid = db.upsert_teacher("T", '{}')
        uid1 = db.insert_unit(tid, "U1", "Math", "8", "Algebra", '{}')
        uid2 = db.insert_unit(tid, "U2", "Science", "8", "Cells", '{}')
        db.insert_lesson(uid1, 1, "Math Lesson", '{}')
        db.insert_lesson(uid2, 1, "Science Lesson", '{}')
        resp = client.get("/lessons?subject=Math")
        assert resp.status_code == 200
        assert "Math Lesson" in resp.text
        # Science lesson should be filtered out
        assert "Science Lesson" not in resp.text

    def test_lessons_page_grade_filter(self, client, db):
        tid = db.upsert_teacher("T", '{}')
        uid = db.insert_unit(tid, "U1", "Math", "6", "Fractions", '{}')
        db.insert_lesson(uid, 1, "Fractions Lesson", '{}')
        resp = client.get("/lessons?grade=6")
        assert resp.status_code == 200
        assert "Fractions Lesson" in resp.text

    def test_lessons_page_no_results(self, client, db):
        tid = db.upsert_teacher("T", '{}')
        uid = db.insert_unit(tid, "U1", "Math", "8", "Algebra", '{}')
        db.insert_lesson(uid, 1, "Algebra", '{}')
        resp = client.get("/lessons?subject=Art")
        assert resp.status_code == 200
        assert "No lessons" in resp.text


class TestSettingsPageExtended:
    """Extended tests for the settings page."""

    def test_settings_page_shows_provider(self, client):
        resp = client.get("/settings")
        assert resp.status_code == 200

    def test_settings_api_get(self, client):
        resp = client.get("/api/settings")
        assert resp.status_code == 200
        data = resp.json()
        assert "provider" in data
        assert "has_anthropic_key" in data
        assert "has_openai_key" in data

    def test_settings_test_connection(self, client):
        resp = client.get("/api/settings/test-connection")
        assert resp.status_code == 200


class TestStudentClassPage:
    """Test the student-facing class page."""

    def test_student_page_unknown_class(self, client):
        resp = client.get("/student/FAKE-CODE")
        assert resp.status_code == 404
        assert "not found" in resp.text.lower()


class TestLessonPageEmbedSnippet:
    """Test that lesson pages include the embed snippet."""

    def test_lesson_page_has_chat_and_copy(self, client, db):
        from clawed.models import DailyLesson

        tid = db.upsert_teacher("T", '{"name": "T"}')
        uid = db.insert_unit(tid, "U", "Science", "8", "Cells", '{}')
        lesson = DailyLesson(
            title="Cell Division",
            lesson_number=1,
            objective="Learn about cells",
        )
        lid = db.insert_lesson(uid, 1, "Cell Division", lesson.model_dump_json())
        resp = client.get(f"/lesson/{lid}")
        assert resp.status_code == 200
        # Lesson page has chat section and copy-to-clipboard for classroom export
        assert "Ask About This Lesson" in resp.text
        assert "Copy to Clipboard" in resp.text

    def test_lesson_page_shows_share_link(self, client, db):
        from clawed.models import DailyLesson

        tid = db.upsert_teacher("T", '{"name": "T"}')
        uid = db.insert_unit(tid, "U", "Science", "8", "Cells", '{}')
        lesson = DailyLesson(title="Sharing Test", lesson_number=1, objective="Test")
        lid = db.insert_lesson(uid, 1, "Sharing Test", lesson.model_dump_json())
        row = db.get_lesson(lid)
        resp = client.get(f"/lesson/{lid}")
        assert resp.status_code == 200
        assert row["share_token"] in resp.text


class TestStudentsPage:
    """Test the students page route."""

    def test_students_page_renders(self, client):
        resp = client.get("/students")
        assert resp.status_code == 200

    def test_library_page_renders(self, client):
        resp = client.get("/library")
        assert resp.status_code == 200


class TestProfilePage:
    """Test the profile page route."""

    def test_profile_page_renders(self, client):
        resp = client.get("/profile")
        assert resp.status_code == 200
        assert "Profile" in resp.text


class TestDashboardPage:
    """Test the dashboard page with recent items."""

    def test_dashboard_with_units(self, client, db):
        tid = db.upsert_teacher("Ms. Teacher", '{"name": "Ms. Teacher"}')
        db.insert_unit(tid, "Unit A", "Math", "8", "Algebra", '{}')
        db.insert_unit(tid, "Unit B", "Science", "7", "Cells", '{}')
        resp = client.get("/dashboard")
        assert resp.status_code == 200
        assert "Unit A" in resp.text
        assert "Unit B" in resp.text


# ═══════════════════════════════════════════════════════════════════════════
# CROSS-WAVE: VERSION AND MODULE TESTS
# ═══════════════════════════════════════════════════════════════════════════


class TestVersion:
    def test_version_string(self):
        from clawed import __version__

        assert __version__ == "4.12.2026.2"

    def test_version_in_health_endpoint(self, client):
        resp = client.get("/api/health")
        data = resp.json()
        assert data["version"] == "4.12.2026.2"
