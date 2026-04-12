"""Regression tests: audit hardening must stay in place.

Pins down the security fixes from the April 2026 audit so they cannot
be silently reverted by a refactor. Each test class maps to a specific
audit finding (ED-1 through ED-10).

Relies on conftest.py autouse fixtures for EDUAGENT_DATA_DIR isolation
and EDUAGENT_LOCAL_AUTH_BYPASS=1 (so teacher-auth routes work in tests).
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from clawed.database import Database

# ── Fixtures ────────────────────────────────────────────────────────


@pytest.fixture()
def db(tmp_path):
    """Fresh database in a temp directory."""
    d = Database(tmp_path / "audit_test.db")
    yield d
    d.close()


@pytest.fixture()
def app(db):
    """FastAPI app wired to the test database."""
    import clawed.api.deps as deps
    from clawed.api.server import create_app

    old = deps._db
    deps._db = db
    a = create_app()
    yield a
    deps._db = old


@pytest.fixture()
def client(app):
    """Test client using the test app."""
    return TestClient(app)


# ── ED-1: classroom state never leaks poll_responses ─────────────────


class TestED1ClassroomStateScrubsPollResponses:
    """The student-facing /classroom/{code}/state endpoint must never
    return raw poll_responses (which contain student_ids and free-text
    answers). Only a count should be exposed.
    """

    def test_state_endpoint_omits_poll_responses(self, client: TestClient):
        """Create session, add poll responses, GET /state -> no poll_responses."""
        # Start a classroom session
        resp = client.post(
            "/api/classroom/start",
            params={"lesson_title": "Test Lesson", "total_slides": 5},
        )
        assert resp.status_code == 200
        code = resp.json()["class_code"]

        # Launch a poll
        client.post(
            f"/api/classroom/{code}/launch-poll",
            params={"question": "What year was the Declaration signed?"},
        )

        # Submit some poll responses (on student router, no auth needed)
        for i in range(3):
            client.post(
                f"/api/classroom/{code}/respond",
                params={"student_id": f"student_{i}", "response": f"answer_{i}"},
            )

        # GET the student-facing state
        state_resp = client.get(f"/api/classroom/{code}/state")
        assert state_resp.status_code == 200
        data = state_resp.json()

        # The critical assertion: poll_responses must NOT appear
        assert "poll_responses" not in data, (
            "ED-1 regression: poll_responses leaked in student state"
        )
        # But the count should be present
        assert data.get("poll_response_count") == 3

    def test_raw_responses_available_on_teacher_route(
        self, client: TestClient,
    ):
        """The teacher-only /classroom/{code}/responses route SHOULD
        return raw poll_responses (it's behind auth)."""
        resp = client.post(
            "/api/classroom/start",
            params={"lesson_title": "Auth Test", "total_slides": 1},
        )
        code = resp.json()["class_code"]
        client.post(
            f"/api/classroom/{code}/launch-poll",
            params={"question": "test"},
        )
        client.post(
            f"/api/classroom/{code}/respond",
            params={"student_id": "s1", "response": "a1"},
        )

        resp = client.get(f"/api/classroom/{code}/responses")
        assert resp.status_code == 200
        data = resp.json()
        assert "responses" in data
        assert len(data["responses"]) == 1


# ── ED-2: auth uses timing-safe comparison ──────────────────────────


class TestED2TimingSafeComparison:
    """The auth layer must use secrets.compare_digest (not ==) to
    prevent timing side-channel attacks on bearer tokens.
    """

    def test_compare_digest_used_in_deps(self):
        """Verify that clawed.api.deps.require_auth uses compare_digest."""
        import inspect

        from clawed.api.deps import require_auth

        source = inspect.getsource(require_auth)
        assert "compare_digest" in source, (
            "ED-2 regression: require_auth does not use compare_digest"
        )

    def test_wrong_token_returns_401(self, client: TestClient, monkeypatch):
        """Functional check: a wrong bearer token must be rejected."""
        # Disable the localhost bypass so auth is actually enforced
        monkeypatch.delenv("EDUAGENT_LOCAL_AUTH_BYPASS", raising=False)

        resp = client.get(
            "/api/feedback-analysis",
            headers={"Authorization": "Bearer totally-wrong-token"},
        )
        assert resp.status_code == 401


# ── ED-3: student chat requires share_token ──────────────────────────


class TestED3StudentChatRequiresShareToken:
    """POST /api/chat/student must require both lesson_id AND
    share_token. Without a valid share_token the endpoint must fail.
    """

    def _seed_lesson(self, db: Database) -> tuple[str, str]:
        """Insert a unit + lesson and return (lesson_id, share_token)."""
        tid = db.upsert_teacher("Test Teacher", "{}")
        uid = db.insert_unit(tid, "Unit", "History", "8", "Test", "{}")
        lid = db.insert_lesson(uid, 1, "Lesson 1", json.dumps({"title": "L1"}))
        row = db.get_lesson(lid)
        assert row is not None
        return lid, row["share_token"]

    def test_missing_share_token_rejected(self, client: TestClient, db: Database):
        """POST /api/chat/student with lesson_id but no share_token -> 422."""
        lid, _ = self._seed_lesson(db)
        resp = client.post(
            "/api/chat/student",
            json={
                "lesson_id": lid,
                "question": "What happened?",
                # share_token intentionally omitted
            },
        )
        # Pydantic should reject the missing required field
        assert resp.status_code == 422, (
            f"ED-3 regression: missing share_token not rejected, got {resp.status_code}"
        )

    def test_wrong_share_token_returns_403(
        self, client: TestClient, db: Database,
    ):
        """POST /api/chat/student with wrong share_token -> 403."""
        lid, _ = self._seed_lesson(db)
        resp = client.post(
            "/api/chat/student",
            json={
                "lesson_id": lid,
                "question": "What happened?",
                "share_token": "completely-wrong-token",
            },
        )
        assert resp.status_code == 403, (
            f"ED-3 regression: wrong share_token not rejected, got {resp.status_code}"
        )

    def test_correct_share_token_proceeds(
        self, client: TestClient, db: Database, monkeypatch,
    ):
        """POST /api/chat/student with correct share_token -> proceeds.

        The actual LLM call will fail in tests (no provider configured),
        but the status should NOT be 403 or 422 -- it should get past
        the auth check.
        """
        lid, token = self._seed_lesson(db)

        # Seed a teacher persona so the chat backend doesn't 400
        db.upsert_teacher("Test", json.dumps({
            "name": "Test",
            "subject_area": "History",
            "grade_levels": ["8"],
            "teaching_style": "direct",
        }))

        resp = client.post(
            "/api/chat/student",
            json={
                "lesson_id": lid,
                "question": "What happened in 1776?",
                "share_token": token,
            },
        )
        # Should NOT be 403 (auth failure) or 422 (validation).
        # It may be 500 (no LLM configured) or 200 -- both prove
        # the share_token check passed.
        assert resp.status_code not in (403, 422), (
            f"ED-3 regression: correct share_token rejected with {resp.status_code}"
        )


# ── ED-9: community rating validation ───────────────────────────────


class TestED9CommunityRatingValidation:
    """POST /api/community/{id}/rate must validate ratings 1.0-5.0."""

    def _seed_community_lesson(self, client: TestClient) -> int:
        """Share a lesson to get a community entry ID."""
        resp = client.post(
            "/api/community/share",
            json={
                "lesson_json": json.dumps({"title": "Shared Lesson"}),
                "subject": "Math",
                "grade_level": "7",
            },
        )
        assert resp.status_code == 200
        return resp.json()["id"]

    def test_rating_below_minimum_rejected(self, client: TestClient):
        """POST rating=0.5 -> 422 (below 1.0 minimum)."""
        lid = self._seed_community_lesson(client)
        resp = client.post(
            f"/api/community/{lid}/rate",
            json={"rating": 0.5},
        )
        assert resp.status_code == 422, (
            f"ED-9 regression: rating 0.5 not rejected, got {resp.status_code}"
        )

    def test_rating_above_maximum_rejected(self, client: TestClient):
        """POST rating=5.5 -> 422 (above 5.0 maximum)."""
        lid = self._seed_community_lesson(client)
        resp = client.post(
            f"/api/community/{lid}/rate",
            json={"rating": 5.5},
        )
        assert resp.status_code == 422, (
            f"ED-9 regression: rating 5.5 not rejected, got {resp.status_code}"
        )

    def test_valid_rating_accepted(self, client: TestClient):
        """POST rating=3.0 -> accepted."""
        lid = self._seed_community_lesson(client)
        resp = client.post(
            f"/api/community/{lid}/rate",
            json={"rating": 3.0},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "rating" in data


# ── ED-10: DB foreign keys enabled ──────────────────────────────────


class TestED10ForeignKeysEnabled:
    """Every Database connection must have PRAGMA foreign_keys = ON."""

    def test_foreign_keys_on_at_init(self, tmp_path):
        """Create a Database and verify PRAGMA foreign_keys returns 1."""
        d = Database(tmp_path / "fk_test.db")
        try:
            with d._connect() as conn:
                row = conn.execute("PRAGMA foreign_keys").fetchone()
                fk_value = row[0] if row else 0
                assert fk_value == 1, (
                    f"ED-10 regression: foreign_keys={fk_value}, expected 1"
                )
        finally:
            d.close()

    def test_foreign_keys_on_per_connection(self, tmp_path):
        """Each new connection also gets foreign_keys=ON."""
        d = Database(tmp_path / "fk_test2.db")
        try:
            # Open two separate connections and check both
            for _ in range(2):
                with d._connect() as conn:
                    row = conn.execute("PRAGMA foreign_keys").fetchone()
                    assert row[0] == 1
        finally:
            d.close()
