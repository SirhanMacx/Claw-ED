"""Tests for the analytics module, rating flow, and stats API."""

from __future__ import annotations

import sqlite3
from unittest.mock import patch

import pytest

from clawed.analytics import (
    average_rating_by_subject,
    get_teacher_stats,
    lessons_needing_improvement,
    most_effective_topics,
    rate_lesson,
    usage_streak,
)


@pytest.fixture
def analytics_db(tmp_path):
    """Set up a temporary state DB for analytics tests."""
    db_path = tmp_path / "clawed.db"

    with patch("clawed.state._db_path", return_value=db_path):
        from clawed.state import init_db

        init_db()

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

        # Seed a teacher session
        conn.execute(
            "INSERT INTO teacher_sessions (teacher_id, name) VALUES (?, ?)",
            ("t1", "Test Teacher"),
        )

        # Seed a unit
        conn.execute(
            """INSERT INTO generated_units (id, teacher_id, title, subject, grade_level, topic, unit_json)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            ("u1", "t1", "Cells Unit", "Science", "8", "Cells", '{"title": "Cells Unit"}'),
        )

        # Seed lessons with varying ratings
        lessons = [
            ("l1", "u1", "t1", 1, "Intro to Cells", '{"subject": "Science", "title": "Intro to Cells"}', 5),
            ("l2", "u1", "t1", 2, "Cell Division", '{"subject": "Science", "title": "Cell Division"}', 4),
            ("l3", "u1", "t1", 3, "DNA Basics", '{"subject": "Science", "title": "DNA Basics"}', 2),
            ("l4", None, "t1", 1, "Math Fractions", '{"subject": "Math", "title": "Math Fractions"}', 3),
            ("l5", None, "t1", 1, "Unrated Lesson", '{"title": "Unrated"}', None),
        ]
        for lid, uid, tid, num, title, ljson, rating in lessons:
            conn.execute(
                "INSERT INTO generated_lessons"
                " (id, unit_id, teacher_id, lesson_number, title, lesson_json, rating, share_token)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (lid, uid, tid, num, title, ljson, rating, f"tok_{lid}"),
            )

        # Seed feedback
        conn.execute(
            "INSERT INTO feedback (id, lesson_id, teacher_id, rating, notes) VALUES (?, ?, ?, ?, ?)",
            ("f1", "l3", "t1", 2, "Too basic"),
        )

        conn.commit()
        conn.close()

        yield db_path


# ── Analytics functions ──────────────────────────────────────────


class TestAverageRatingBySubject:
    def test_returns_ratings_by_subject(self, analytics_db):
        with patch("clawed.state._db_path", return_value=analytics_db):
            result = average_rating_by_subject("t1")
            assert "Science" in result
            # Science lessons: 5 + 4 + 2 = 11, avg = 3.67
            assert 3.5 <= result["Science"] <= 3.7
            assert "Math" in result
            assert result["Math"] == 3.0

    def test_empty_for_unknown_teacher(self, analytics_db):
        with patch("clawed.state._db_path", return_value=analytics_db):
            result = average_rating_by_subject("unknown")
            assert result == {}


class TestMostEffectiveTopics:
    def test_returns_sorted_by_rating(self, analytics_db):
        with patch("clawed.state._db_path", return_value=analytics_db):
            result = most_effective_topics("t1")
            assert len(result) >= 1
            # "Intro to Cells" rated 5 should be first
            assert result[0]["topic"] == "Intro to Cells"
            assert result[0]["avg_rating"] == 5.0

    def test_limit_works(self, analytics_db):
        with patch("clawed.state._db_path", return_value=analytics_db):
            result = most_effective_topics("t1", limit=2)
            assert len(result) == 2


class TestLessonsNeedingImprovement:
    def test_finds_low_rated(self, analytics_db):
        with patch("clawed.state._db_path", return_value=analytics_db):
            result = lessons_needing_improvement("t1", threshold=3)
            assert len(result) == 1
            assert result[0]["lesson_id"] == "l3"
            assert result[0]["rating"] == 2

    def test_none_when_all_good(self, analytics_db):
        with patch("clawed.state._db_path", return_value=analytics_db):
            result = lessons_needing_improvement("t1", threshold=1)
            assert len(result) == 0


class TestUsageStreak:
    def test_returns_int(self, analytics_db):
        with patch("clawed.state._db_path", return_value=analytics_db):
            result = usage_streak("t1")
            assert isinstance(result, int)
            assert result >= 0

    def test_zero_for_unknown(self, analytics_db):
        with patch("clawed.state._db_path", return_value=analytics_db):
            result = usage_streak("nobody")
            assert result == 0


class TestGetTeacherStats:
    def test_comprehensive_stats(self, analytics_db):
        with patch("clawed.state._db_path", return_value=analytics_db):
            result = get_teacher_stats("t1")
            assert result["total_lessons"] == 5
            assert result["rated_lessons"] == 4
            assert result["total_units"] == 1
            assert 3.0 <= result["overall_avg_rating"] <= 4.0
            assert isinstance(result["rating_distribution"], dict)
            assert isinstance(result["by_subject"], dict)
            assert isinstance(result["top_topics"], list)
            assert isinstance(result["needs_improvement"], list)
            assert isinstance(result["streak"], int)

    def test_empty_for_new_teacher(self, analytics_db):
        with patch("clawed.state._db_path", return_value=analytics_db):
            result = get_teacher_stats("brand-new")
            assert result["total_lessons"] == 0
            assert result["rated_lessons"] == 0
            assert result["overall_avg_rating"] == 0.0


# ── Rating function ──────────────────────────────────────────────


class TestRateLesson:
    def test_rate_existing_lesson(self, analytics_db):
        with patch("clawed.state._db_path", return_value=analytics_db):
            success = rate_lesson("t1", "l5", 4)
            assert success is True

            # Verify the rating was saved
            conn = sqlite3.connect(str(analytics_db))
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT rating FROM generated_lessons WHERE id = ?", ("l5",)).fetchone()
            assert row["rating"] == 4

            # Verify feedback was inserted
            fb = conn.execute("SELECT * FROM feedback WHERE lesson_id = ? AND rating = 4", ("l5",)).fetchone()
            assert fb is not None
            conn.close()

    def test_rate_nonexistent_lesson(self, analytics_db):
        with patch("clawed.state._db_path", return_value=analytics_db):
            success = rate_lesson("t1", "nonexistent", 3)
            assert success is False

    def test_rating_clamps_to_range(self, analytics_db):
        with patch("clawed.state._db_path", return_value=analytics_db):
            success = rate_lesson("t1", "l5", 10)
            assert success is True

            conn = sqlite3.connect(str(analytics_db))
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT rating FROM generated_lessons WHERE id = ?", ("l5",)).fetchone()
            assert row["rating"] == 5  # Clamped to max
            conn.close()

    def test_low_rating_queues_improvement(self, analytics_db):
        with patch("clawed.state._db_path", return_value=analytics_db):
            with patch("clawed.improver.queue_low_rated_for_improvement") as mock_queue:
                rate_lesson("t1", "l5", 2)
                mock_queue.assert_called_once_with(2, "l5", "t1")


# ── Improver integration ─────────────────────────────────────────


class TestQueueLowRated:
    def test_queues_below_threshold(self):
        from clawed.improver import queue_low_rated_for_improvement

        assert queue_low_rated_for_improvement(2, "l1", "t1") is True

    def test_skips_good_ratings(self):
        from clawed.improver import queue_low_rated_for_improvement

        assert queue_low_rated_for_improvement(3, "l1", "t1") is False
        assert queue_low_rated_for_improvement(5, "l1", "t1") is False


# ── Openclaw plugin integration ──────────────────────────────────


class TestGetLastLessonId:
    def test_returns_and_clears(self, analytics_db):
        with patch("clawed.state._db_path", return_value=analytics_db):
            from clawed.state import TeacherSession

            session = TeacherSession.load("t1")
            session.config["last_lesson_id"] = "l1"
            session.save()

            from clawed.openclaw_plugin import get_last_lesson_id

            result = get_last_lesson_id("t1")
            assert result == "l1"

            # Should be cleared after reading
            result2 = get_last_lesson_id("t1")
            assert result2 is None


# ── Web API stats endpoint ───────────────────────────────────────


class TestStatsAPI:
    @pytest.fixture
    def web_db(self, tmp_path):
        from clawed.database import Database

        return Database(tmp_path / "test.db")

    @pytest.fixture
    def client(self, web_db):
        from fastapi.testclient import TestClient

        import clawed.api.deps as deps
        from clawed.api.server import create_app

        old_db = deps._db
        deps._db = web_db
        test_app = create_app()
        yield TestClient(test_app)
        deps._db = old_db

    def test_stats_page_renders(self, client):
        resp = client.get("/stats")
        assert resp.status_code == 200
        assert "My Stats" in resp.text

    def test_stats_api_endpoint(self, client, analytics_db):
        with patch("clawed.state._db_path", return_value=analytics_db):
            resp = client.get("/api/stats?teacher_id=t1")
            assert resp.status_code == 200
            data = resp.json()
            assert "total_lessons" in data
            assert "rated_lessons" in data
            assert "overall_avg_rating" in data
            assert "rating_distribution" in data

    def test_stats_api_unknown_teacher(self, client, analytics_db):
        with patch("clawed.state._db_path", return_value=analytics_db):
            resp = client.get("/api/stats?teacher_id=nobody")
            assert resp.status_code == 200
            data = resp.json()
            assert data["total_lessons"] == 0
