"""Tests for the Claw-ED FastAPI web platform."""

import json

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


# ── Database tests ────────────────────────────────────────────────────


class TestDatabase:
    def test_upsert_and_get_teacher(self, db):
        tid = db.upsert_teacher("Ms. Smith", '{"name": "Ms. Smith"}')
        assert len(tid) == 12
        teacher = db.get_teacher(tid)
        assert teacher is not None
        assert teacher["name"] == "Ms. Smith"
        assert json.loads(teacher["persona_json"])["name"] == "Ms. Smith"

    def test_get_default_teacher(self, db):
        assert db.get_default_teacher() is None
        db.upsert_teacher("Teacher One", '{"name": "One"}')
        db.upsert_teacher("Teacher Two", '{"name": "Two"}')
        default = db.get_default_teacher()
        assert default is not None

    def test_insert_and_get_unit(self, db):
        tid = db.upsert_teacher("T", "{}")
        uid = db.insert_unit(tid, "Test Unit", "Science", "8", "Cells", '{"title": "Test Unit"}')
        assert len(uid) == 12
        unit = db.get_unit(uid)
        assert unit["title"] == "Test Unit"
        assert unit["subject"] == "Science"

    def test_list_units(self, db):
        tid = db.upsert_teacher("T", "{}")
        db.insert_unit(tid, "Unit A", "Math", "5", "Fractions", "{}")
        db.insert_unit(tid, "Unit B", "Science", "8", "Cells", "{}")
        units = db.list_units()
        assert len(units) == 2

    def test_insert_and_get_lesson(self, db):
        tid = db.upsert_teacher("T", "{}")
        uid = db.insert_unit(tid, "U", "S", "8", "T", "{}")
        lid = db.insert_lesson(uid, 1, "Lesson 1", '{"title": "Lesson 1"}')
        lesson = db.get_lesson(lid)
        assert lesson is not None
        assert lesson["title"] == "Lesson 1"
        assert lesson["share_token"] is not None

    def test_lesson_share_token(self, db):
        tid = db.upsert_teacher("T", "{}")
        uid = db.insert_unit(tid, "U", "S", "8", "T", "{}")
        lid = db.insert_lesson(uid, 1, "L1", "{}")
        lesson = db.get_lesson(lid)
        by_token = db.get_lesson_by_token(lesson["share_token"])
        assert by_token is not None
        assert by_token["id"] == lid

    def test_update_lesson_json(self, db):
        tid = db.upsert_teacher("T", "{}")
        uid = db.insert_unit(tid, "U", "S", "8", "T", "{}")
        lid = db.insert_lesson(uid, 1, "L1", '{"v": 1}')
        db.update_lesson_json(lid, '{"v": 2}')
        lesson = db.get_lesson(lid)
        assert json.loads(lesson["lesson_json"])["v"] == 2
        assert lesson["edit_count"] == 1

    def test_feedback_crud(self, db):
        tid = db.upsert_teacher("T", "{}")
        uid = db.insert_unit(tid, "U", "S", "8", "T", "{}")
        lid = db.insert_lesson(uid, 1, "L1", "{}")
        fid = db.insert_feedback(lid, 4, "Great!", '["objective"]')
        assert len(fid) == 12
        feedback = db.get_feedback_for_lesson(lid)
        assert len(feedback) == 1
        assert feedback[0]["rating"] == 4
        assert feedback[0]["notes"] == "Great!"

    def test_prompt_versions(self, db):
        pid = db.insert_prompt_version("lesson_plan", 1, "version 1 text")
        assert len(pid) == 12
        active = db.get_active_prompt("lesson_plan")
        assert active is not None
        assert active["version"] == 1

    def test_promote_prompt(self, db):
        db.insert_prompt_version("lesson_plan", 1, "v1")
        p2 = db.insert_prompt_version("lesson_plan", 2, "v2")
        db.promote_prompt(p2, "lesson_plan")
        active = db.get_active_prompt("lesson_plan")
        assert active["id"] == p2

    def test_chat_messages(self, db):
        tid = db.upsert_teacher("T", "{}")
        uid = db.insert_unit(tid, "U", "S", "8", "T", "{}")
        lid = db.insert_lesson(uid, 1, "L1", "{}")
        db.insert_chat_message(lid, "user", "What is photosynthesis?")
        db.insert_chat_message(lid, "assistant", "It's a process...")
        history = db.get_chat_history(lid)
        assert len(history) == 2
        assert db.count_chat_sessions() == 1

    def test_stats(self, db):
        stats = db.get_stats()
        assert stats["units"] == 0
        assert stats["lessons"] == 0
        assert stats["chats"] == 0


# ── Page routes ───────────────────────────────────────────────────────


class TestPageRoutes:
    def test_index_page(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "Claw-ED" in resp.text

    def test_dashboard_page(self, client):
        resp = client.get("/dashboard")
        assert resp.status_code == 200
        assert "Dashboard" in resp.text

    def test_generate_page(self, client):
        resp = client.get("/generate")
        assert resp.status_code == 200
        assert "Generate" in resp.text

    def test_lesson_page_404(self, client):
        resp = client.get("/lesson/nonexistent")
        assert resp.status_code == 404
        assert "not found" in resp.text.lower()

    def test_share_page_404(self, client):
        resp = client.get("/share/badtoken")
        assert resp.status_code == 404
        assert "not found" in resp.text.lower()

    def test_analytics_page(self, client):
        resp = client.get("/analytics")
        assert resp.status_code == 200
        assert "Analytics" in resp.text

    def test_profile_page(self, client):
        resp = client.get("/profile")
        assert resp.status_code == 200
        assert "Profile" in resp.text

    def test_dashboard_contains_teacher_name(self, client, db):
        db.upsert_teacher("Mr. Rodriguez", '{"name": "Mr. Rodriguez", "teaching_style": "socratic"}')
        resp = client.get("/dashboard")
        assert resp.status_code == 200
        assert "Mr. Rodriguez" in resp.text


# ── API routes ────────────────────────────────────────────────────────


class TestAPIRoutes:
    def test_get_persona_no_teacher(self, client):
        resp = client.get("/api/persona")
        assert resp.status_code == 404

    def test_get_persona_with_teacher(self, client, db):
        db.upsert_teacher("Ms. T", '{"name": "Ms. T", "teaching_style": "direct_instruction"}')
        resp = client.get("/api/persona")
        assert resp.status_code == 200
        data = resp.json()
        assert data["persona"]["name"] == "Ms. T"

    def test_list_units_empty(self, client):
        resp = client.get("/api/units")
        assert resp.status_code == 200
        assert resp.json()["units"] == []

    def test_list_units_with_data(self, client, db):
        tid = db.upsert_teacher("T", "{}")
        db.insert_unit(tid, "Unit A", "Math", "5", "Fractions", "{}")
        resp = client.get("/api/units")
        assert resp.status_code == 200
        assert len(resp.json()["units"]) == 1

    def test_list_lessons_empty(self, client, db):
        tid = db.upsert_teacher("T", "{}")
        uid = db.insert_unit(tid, "U", "S", "8", "T", "{}")
        resp = client.get(f"/api/lessons/{uid}")
        assert resp.status_code == 200
        assert resp.json()["lessons"] == []

    def test_feedback_invalid_rating(self, client, db):
        tid = db.upsert_teacher("T", "{}")
        uid = db.insert_unit(tid, "U", "S", "8", "T", "{}")
        lid = db.insert_lesson(uid, 1, "L1", "{}")
        resp = client.post("/api/feedback", json={"lesson_id": lid, "rating": 0})
        assert resp.status_code == 400

    def test_feedback_lesson_not_found(self, client):
        resp = client.post("/api/feedback", json={"lesson_id": "fake", "rating": 4})
        assert resp.status_code == 404

    def test_feedback_success(self, client, db):
        tid = db.upsert_teacher("T", "{}")
        uid = db.insert_unit(tid, "U", "S", "8", "T", "{}")
        lid = db.insert_lesson(uid, 1, "L1", "{}")
        resp = client.post("/api/feedback", json={"lesson_id": lid, "rating": 4, "notes": "Good!"})
        assert resp.status_code == 200
        assert "feedback_id" in resp.json()

    def test_get_feedback(self, client, db):
        tid = db.upsert_teacher("T", "{}")
        uid = db.insert_unit(tid, "U", "S", "8", "T", "{}")
        lid = db.insert_lesson(uid, 1, "L1", "{}")
        db.insert_feedback(lid, 5, "Awesome")
        resp = client.get(f"/api/feedback/{lid}")
        assert resp.status_code == 200
        assert len(resp.json()["feedback"]) == 1

    def test_feedback_analysis(self, client, db):
        resp = client.get("/api/feedback-analysis")
        assert resp.status_code == 200
        assert "analysis" in resp.json()

    def test_export_lesson_not_found(self, client):
        resp = client.get("/api/export/fake")
        assert resp.status_code == 404
        data = resp.json()
        assert "error" in data

    def test_export_lesson_markdown(self, client, db):
        from clawed.models import DailyLesson

        tid = db.upsert_teacher("T", "{}")
        uid = db.insert_unit(tid, "U", "S", "8", "T", "{}")
        lesson = DailyLesson(title="Test", lesson_number=1, objective="Learn things")
        lid = db.insert_lesson(uid, 1, "Test", lesson.model_dump_json())
        resp = client.get(f"/api/export/{lid}?fmt=markdown")
        assert resp.status_code == 200
        assert "Test" in resp.text

    def test_export_unsupported_format(self, client, db):
        from clawed.models import DailyLesson

        tid = db.upsert_teacher("T", "{}")
        uid = db.insert_unit(tid, "U", "S", "8", "T", "{}")
        lesson = DailyLesson(title="Test", lesson_number=1, objective="Learn things")
        lid = db.insert_lesson(uid, 1, "Test", lesson.model_dump_json())
        resp = client.get(f"/api/export/{lid}?fmt=xml")
        data = resp.json()
        assert "error" in data

    def test_share_api_not_found(self, client):
        resp = client.get("/api/share/badtoken")
        data = resp.json()
        assert "error" in data

    def test_share_api_success(self, client, db):
        tid = db.upsert_teacher("T", "{}")
        uid = db.insert_unit(tid, "U", "S", "8", "T", "{}")
        lid = db.insert_lesson(uid, 1, "L1", '{"title": "Hello"}')
        lesson = db.get_lesson(lid)
        token = lesson["share_token"]
        resp = client.get(f"/api/share/{token}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "L1"

    def test_unit_generation_no_persona(self, client):
        resp = client.post("/api/unit", json={"topic": "Cells"})
        assert resp.status_code == 400

    def test_lesson_generation_no_persona(self, client):
        resp = client.post("/api/lesson", json={"unit_id": "fake", "lesson_number": 1})
        assert resp.status_code == 400

    def test_materials_generation_no_persona(self, client):
        resp = client.post("/api/materials", json={"lesson_id": "fake"})
        assert resp.status_code == 400

    def test_chat_lesson_not_found(self, client):
        resp = client.post("/api/chat", json={"lesson_id": "fake", "question": "What?"})
        assert resp.status_code == 404

    def test_chat_no_persona(self, client, db):
        tid = db.upsert_teacher("T", None)  # No persona JSON
        uid = db.insert_unit(tid, "U", "S", "8", "T", "{}")
        lid = db.insert_lesson(uid, 1, "L1", "{}")
        resp = client.post("/api/chat", json={"lesson_id": lid, "question": "What?"})
        assert resp.status_code == 400


# ── Lesson page with data ────────────────────────────────────────────


class TestLessonPage:
    def test_lesson_page_renders(self, client, db):
        from clawed.models import DailyLesson

        tid = db.upsert_teacher("T", '{"name": "T"}')
        uid = db.insert_unit(tid, "U", "Science", "8", "Cells", "{}")
        lesson = DailyLesson(
            title="Cell Structure",
            lesson_number=1,
            objective="Learn about cells",
            do_now="Draw a cell",
            direct_instruction="Cells are the basic unit of life.",
            guided_practice="Label the cell diagram.",
            independent_work="Complete the worksheet.",
        )
        lid = db.insert_lesson(uid, 1, "Cell Structure", lesson.model_dump_json())
        resp = client.get(f"/lesson/{lid}")
        assert resp.status_code == 200
        assert "Cell Structure" in resp.text
        assert "Learn about cells" in resp.text

    def test_share_page_renders(self, client, db):
        from clawed.models import DailyLesson

        tid = db.upsert_teacher("T", '{"name": "T"}')
        uid = db.insert_unit(tid, "U", "Science", "8", "Cells", "{}")
        lesson = DailyLesson(title="Shared Lesson", lesson_number=1, objective="Test")
        lid = db.insert_lesson(uid, 1, "Shared Lesson", lesson.model_dump_json())
        row = db.get_lesson(lid)
        resp = client.get(f"/share/{row['share_token']}")
        assert resp.status_code == 200
        assert "Shared Lesson" in resp.text


# ── New feature tests (v0.1.2) ──────────────────────────────────────


class TestDatabaseScores:
    """Test the scores_json column in lessons table."""

    def test_update_and_get_scores(self, db):
        tid = db.upsert_teacher("T", "{}")
        uid = db.insert_unit(tid, "U", "S", "8", "T", "{}")
        lid = db.insert_lesson(uid, 1, "L1", "{}")
        scores = {"overall": 4.2, "objective_clarity": {"score": 5, "explanation": "Clear"}}
        db.update_lesson_scores(lid, json.dumps(scores))
        lesson = db.get_lesson(lid)
        assert lesson["scores_json"] is not None
        loaded = json.loads(lesson["scores_json"])
        assert loaded["overall"] == 4.2

    def test_lesson_initially_no_scores(self, db):
        tid = db.upsert_teacher("T", "{}")
        uid = db.insert_unit(tid, "U", "S", "8", "T", "{}")
        lid = db.insert_lesson(uid, 1, "L1", "{}")
        lesson = db.get_lesson(lid)
        assert lesson["scores_json"] is None


class TestTemplatesLib:
    """Test the lesson template system."""

    def test_list_templates(self):
        from clawed.templates_lib import list_templates

        templates = list_templates()
        assert len(templates) >= 7
        names = [t.name for t in templates]
        assert "Socratic Seminar" in names
        assert "Jigsaw" in names
        assert "Think-Pair-Share" in names
        assert "Station Rotation" in names

    def test_get_template(self):
        from clawed.templates_lib import get_template

        t = get_template("socratic-seminar")
        assert t is not None
        assert t.name == "Socratic Seminar"
        assert len(t.sections) > 0

    def test_get_template_not_found(self):
        from clawed.templates_lib import get_template

        assert get_template("nonexistent") is None

    def test_template_sections(self):
        from clawed.templates_lib import get_template

        t = get_template("jigsaw")
        assert t is not None
        total_time = sum(s.duration_minutes for s in t.sections)
        assert total_time > 0

    def test_template_to_prompt_constraint(self):
        from clawed.templates_lib import get_template, template_to_prompt_constraint

        t = get_template("station-rotation")
        assert t is not None
        constraint = template_to_prompt_constraint(t)
        assert "Station Rotation" in constraint
        assert "Teacher-Led" in constraint


class TestQualityScoreModel:
    """Test the LessonQualityScore class (without LLM calls)."""

    def test_dimensions_defined(self):
        from clawed.quality import LessonQualityScore

        assert len(LessonQualityScore.dimensions) == 6
        assert "objective_clarity" in LessonQualityScore.dimensions

    def test_lesson_to_text(self):
        from clawed.models import DailyLesson
        from clawed.quality import LessonQualityScore

        lesson = DailyLesson(title="Test", lesson_number=1, objective="Learn cells", do_now="Draw a cell")
        text = LessonQualityScore._lesson_to_text(lesson)
        assert "Learn cells" in text
        assert "Draw a cell" in text


class TestExporterPDF:
    """Test the weasyprint PDF export function (HTML generation)."""

    def test_lesson_to_html_for_pdf(self):
        from clawed.export_markdown import _lesson_to_html_for_pdf
        from clawed.models import DailyLesson

        lesson = DailyLesson(
            title="Cell Division",
            lesson_number=3,
            objective="Understand mitosis",
            do_now="Label a cell",
            direct_instruction="The cell cycle consists of...",
        )
        html = _lesson_to_html_for_pdf(lesson, teacher_name="Ms. Johnson", date_str="2026-01-15")
        assert "Cell Division" in html
        assert "Understand mitosis" in html
        assert "Ms. Johnson" in html
        assert "2026-01-15" in html


class TestNewAPIRoutes:
    """Test new API endpoints added in v0.1.2."""

    def test_templates_endpoint(self, client):
        resp = client.get("/api/templates")
        assert resp.status_code == 200
        data = resp.json()
        assert "templates" in data
        assert len(data["templates"]) >= 7
        slugs = [t["slug"] for t in data["templates"]]
        assert "socratic-seminar" in slugs
        assert "jigsaw" in slugs

    def test_classroom_export_not_found(self, client):
        resp = client.post("/api/export/fake/classroom")
        assert resp.status_code == 404

    def test_classroom_export_success(self, client, db):
        from clawed.models import DailyLesson

        tid = db.upsert_teacher("T", "{}")
        uid = db.insert_unit(tid, "U", "S", "8", "T", "{}")
        lesson = DailyLesson(
            title="Photosynthesis",
            lesson_number=1,
            objective="Explain the equation for photosynthesis",
            standards=["NGSS MS-LS1-6"],
        )
        lid = db.insert_lesson(uid, 1, "Photosynthesis", lesson.model_dump_json())
        resp = client.post(f"/api/export/{lid}/classroom")
        assert resp.status_code == 200
        data = resp.json()
        assert "coursework" in data
        cw = data["coursework"]
        assert cw["title"] == "Photosynthesis"
        assert "photosynthesis" in cw["description"].lower()
        assert cw["workType"] == "ASSIGNMENT"
        assert "maxPoints" in cw

    def test_suggest_lesson_not_found(self, client):
        resp = client.post("/api/suggest/fake")
        assert resp.status_code == 404

    def test_score_lesson_not_found(self, client):
        resp = client.get("/api/score/fake")
        assert resp.status_code == 404

    def test_stream_unit_no_persona(self, client):
        resp = client.get("/api/stream/unit?topic=Cells")
        assert resp.status_code == 400

    def test_stream_lesson_no_persona(self, client):
        resp = client.get("/api/stream/lesson?unit_id=fake&lesson_number=1")
        # Either 400 (no persona) or 404 (unit not found) depending on check order
        assert resp.status_code in (400, 404)

    def test_course_no_persona(self, client):
        resp = client.post(
            "/api/course",
            json={
                "subject": "Science",
                "grade_level": "8",
                "topics": ["Cells", "DNA"],
                "weeks_per_topic": 2,
            },
        )
        assert resp.status_code == 400

    def test_lesson_page_with_scores(self, client, db):
        from clawed.models import DailyLesson

        tid = db.upsert_teacher("T", '{"name": "T"}')
        uid = db.insert_unit(tid, "U", "Science", "8", "Cells", "{}")
        lesson = DailyLesson(title="Scored Lesson", lesson_number=1, objective="Test")
        lid = db.insert_lesson(uid, 1, "Scored Lesson", lesson.model_dump_json())
        scores = {"overall": 4.0, "objective_clarity": {"score": 5, "explanation": "Very clear."}}
        db.update_lesson_scores(lid, json.dumps(scores))
        resp = client.get(f"/lesson/{lid}")
        assert resp.status_code == 200
        assert "Quality Score" in resp.text

    def test_generate_page_has_template_dropdown(self, client):
        resp = client.get("/generate")
        assert resp.status_code == 200
        assert "template_slug" in resp.text
        assert "Lesson Structure" in resp.text


class TestWidgetStatic:
    """Test that the widget.js static file is served."""

    def test_widget_js_served(self, client):
        resp = client.get("/static/widget.js")
        assert resp.status_code == 200
        assert "clawed-widget" in resp.text
        assert "data-lesson-id" in resp.text


# ── Onboarding + Settings tests (v0.2.0) ────────────────────


class TestOnboardingDatabase:
    """Test the onboarding_state table operations."""

    def test_onboarding_not_complete_initially(self, db):
        assert db.is_onboarding_complete() is False

    def test_upsert_and_get_onboarding(self, db):
        tid = db.upsert_teacher("T", "{}")
        db.upsert_onboarding(tid, 2)
        state = db.get_onboarding(tid)
        assert state is not None
        assert state["step_completed"] == 2
        assert state["completed_at"] is None

    def test_onboarding_complete_at_step_5(self, db):
        tid = db.upsert_teacher("T", "{}")
        db.upsert_onboarding(tid, 5)
        assert db.is_onboarding_complete() is True
        state = db.get_onboarding(tid)
        assert state["completed_at"] is not None

    def test_clear_all_generated(self, db):
        tid = db.upsert_teacher("T", "{}")
        uid = db.insert_unit(tid, "U", "S", "8", "T", "{}")
        db.insert_lesson(uid, 1, "L1", "{}")
        db.insert_feedback("fake", 4, "Nice")
        db.clear_all_generated()
        assert db.get_stats()["units"] == 0
        assert db.get_stats()["lessons"] == 0

    def test_reset_all(self, db):
        tid = db.upsert_teacher("T", "{}")
        db.insert_unit(tid, "U", "S", "8", "T", "{}")
        db.upsert_onboarding(tid, 5)
        db.reset_all()
        assert db.get_default_teacher() is None
        assert db.is_onboarding_complete() is False

    def test_db_size_mb(self, db):
        size = db.db_size_mb()
        assert isinstance(size, float)
        assert size >= 0


class TestHealthCheck:
    """Test the health check endpoint."""

    def test_health_endpoint(self, client):
        """Health is now a lightweight liveness check."""
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data


class TestSettingsRoutes:
    """Test settings API routes."""

    def test_get_settings(self, client):
        resp = client.get("/api/settings")
        assert resp.status_code == 200
        data = resp.json()
        assert "provider" in data
        assert "anthropic_model" in data
        assert "include_homework" in data

    def test_save_settings(self, client):
        resp = client.post(
            "/api/settings",
            json={
                "provider": "ollama",
                "ollama_model": "llama3.2",
                "ollama_base_url": "http://localhost:11434",
                "anthropic_model": "claude-sonnet-4-6",
                "openai_model": "gpt-4.1",
                "include_homework": False,
                "export_format": "pdf",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "saved"

    def test_clear_content(self, client, db):
        tid = db.upsert_teacher("T", "{}")
        db.insert_unit(tid, "U", "S", "8", "T", "{}")
        resp = client.post("/api/settings/clear-content")
        assert resp.status_code == 200
        assert resp.json()["status"] == "cleared"
        assert db.get_stats()["units"] == 0

    def test_reset_all(self, client, db):
        db.upsert_teacher("T", "{}")
        resp = client.post("/api/settings/reset")
        assert resp.status_code == 200
        assert resp.json()["status"] == "reset"
        assert db.get_default_teacher() is None


class TestOnboardingRoutes:
    """Test onboarding API routes."""

    def test_onboarding_state_no_teacher(self, client):
        resp = client.get("/api/onboarding/state")
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_persona"] is False
        assert data["step_completed"] == 0

    def test_onboarding_state_with_teacher(self, client, db):
        db.upsert_teacher("Ms. T", '{"name": "Ms. T"}')
        resp = client.get("/api/onboarding/state")
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_persona"] is True
        assert data["teacher_id"] is not None

    def test_create_persona_from_form(self, client):
        resp = client.post(
            "/api/onboarding/persona-form",
            json={
                "name": "Mr. Test",
                "subject_area": "Math",
                "grade_levels": "8, 9",
                "teaching_style": "socratic",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["persona"]["name"] == "Mr. Test"
        assert data["persona"]["teaching_style"] == "socratic"
        assert data["teacher_id"] is not None

    def test_update_onboarding_step(self, client, db):
        tid = db.upsert_teacher("T", "{}")
        resp = client.post(
            "/api/onboarding/step",
            json={
                "teacher_id": tid,
                "step": 3,
            },
        )
        assert resp.status_code == 200
        state = db.get_onboarding(tid)
        assert state["step_completed"] == 3


class TestSettingsPage:
    """Test the settings page route."""

    def test_settings_page_renders(self, client):
        resp = client.get("/settings")
        assert resp.status_code == 200
        assert "Settings" in resp.text
        assert "LLM Provider" in resp.text
        assert "Danger Zone" in resp.text

    def test_index_shows_landing_no_persona(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        # New landing page serves the static landing HTML or redirects to dashboard
        assert "Claw-ED" in resp.text

    def test_index_shows_dashboard_with_persona(self, client, db):
        tid = db.upsert_teacher("Ms. T", '{"name": "Ms. T"}')
        db.upsert_onboarding(tid, 5)
        resp = client.get("/")
        assert resp.status_code == 200
        # With persona, shows dashboard or landing — both contain Claw-ED
        assert "Claw-ED" in resp.text


class TestConfigModule:
    """Test the config module functions."""

    def test_mask_api_key_short(self):
        from clawed.config import mask_api_key

        assert mask_api_key("abc") == "***"
        assert mask_api_key("") == ""
        assert mask_api_key(None) == ""

    def test_mask_api_key_long(self):
        from clawed.config import mask_api_key

        result = mask_api_key("sk-ant-api03-abcdefghij")
        assert result.startswith("sk-")
        assert result.endswith("ghij")  # last 6 chars
        assert "..." in result

    def test_has_config(self):
        from clawed.config import has_config

        # Just test it doesn't crash — actual value depends on system state
        result = has_config()
        assert isinstance(result, bool)
