"""Network-free contract tests for the artifact-generation REST endpoints.

Covers the three POST endpoints the Create UI hits — differentiate, quiz,
and game (clawed/api/routes/generate.py) — asserting they fail *gracefully*
on bad input rather than 500-ing:

  * POST /api/differentiate/<bogus>  -> 404 (lesson not found, not 500)
  * POST /api/quiz  with invalid body -> 422 (pydantic validation)
  * POST /api/game  with no topic     -> 422 (pydantic validation)

Plus one optional happy-path: /api/quiz -> 200 with the LLM call stubbed out
(no real network) to prove the success contract and JSON shape.

Auth is bypassed for the localhost/testclient host, and the data dir is
redirected to a throwaway temp dir so the suite never touches the real
``~/.eduagent`` store or any worktree DB. Both env vars are set BEFORE the
app is imported, since import-time config reads them.
"""
from __future__ import annotations

import os
import tempfile

# ── Environment must be configured before importing the app ──────────────
# require_auth() honors this bypass for the in-process TestClient host.
os.environ["EDUAGENT_LOCAL_AUTH_BYPASS"] = "1"
# Force the null keyring backend so no OS keychain prompt / lookup happens.
os.environ["PYTHON_KEYRING_BACKEND"] = "keyring.backends.null.Keyring"
# Redirect all on-disk state (config + sqlite DB) to an isolated temp dir.
_TMP_DATA_DIR = tempfile.mkdtemp(prefix="clawed_test_artifacts_")
os.environ["EDUAGENT_DATA_DIR"] = _TMP_DATA_DIR

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import clawed.llm  # noqa: E402
from clawed.api.server import create_app  # noqa: E402
from clawed.models import Quiz  # noqa: E402


@pytest.fixture(scope="module")
def client() -> TestClient:
    """A TestClient over a freshly created app instance."""
    return TestClient(create_app())


# ── Graceful-failure contracts (no LLM, no network) ──────────────────────


def test_differentiate_unknown_lesson_returns_404(client: TestClient) -> None:
    """A bogus lesson id must 404 (lesson not found), never 500."""
    resp = client.post(
        "/api/differentiate/nonexistent-lesson-id",
        json={"profile": "ell"},
    )

    assert resp.status_code == 404
    body = resp.json()
    assert "error" in body
    # The handler returns a clean, user-facing message — not a stack trace.
    assert "not found" in body["error"].lower()


def test_differentiate_invalid_profile_returns_422(client: TestClient) -> None:
    """profile is a constrained Literal; an out-of-set value is a 422.

    This is validated before the lesson lookup, so it stays network-free even
    though the lesson id below would otherwise reach the DB.
    """
    resp = client.post(
        "/api/differentiate/nonexistent-lesson-id",
        json={"profile": "not-a-real-profile"},
    )

    assert resp.status_code == 422


def test_quiz_invalid_body_returns_422(client: TestClient) -> None:
    """An empty body is missing the required ``topic`` field -> 422."""
    resp = client.post("/api/quiz", json={})

    assert resp.status_code == 422


def test_quiz_blank_topic_returns_422(client: TestClient) -> None:
    """``topic`` has min_length=1, so an empty string is rejected -> 422."""
    resp = client.post("/api/quiz", json={"topic": ""})

    assert resp.status_code == 422


def test_game_missing_topic_returns_422(client: TestClient) -> None:
    """The game endpoint requires ``topic``; omitting it -> 422."""
    resp = client.post("/api/game", json={"grade_level": "8", "subject": "Math"})

    assert resp.status_code == 422


def test_game_blank_topic_returns_422(client: TestClient) -> None:
    """``topic`` has min_length=1 on the game request too -> 422."""
    resp = client.post("/api/game", json={"topic": ""})

    assert resp.status_code == 422


# ── Optional happy-path with the LLM stubbed (still no network) ───────────


def test_quiz_success_with_stubbed_llm(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With safe_generate_json stubbed, /api/quiz returns 200 + the expected shape.

    The real endpoint calls ``AssessmentGenerator.generate_quiz`` which delegates
    to ``LLMClient.safe_generate_json`` (returns a ``Quiz`` model). We replace
    that single coroutine with a canned ``Quiz`` so nothing touches the network,
    then assert the response contract the UI relies on.
    """

    async def _fake_safe_generate_json(self: object, *args: object, **kwargs: object) -> Quiz:
        return Quiz(
            topic="Photosynthesis",
            grade_level="7",
            questions=[],
            total_points=10,
            time_minutes=15,
        )

    monkeypatch.setattr(
        clawed.llm.LLMClient,
        "safe_generate_json",
        _fake_safe_generate_json,
        raising=True,
    )

    resp = client.post(
        "/api/quiz",
        json={
            "topic": "Photosynthesis",
            "grade_level": "7",
            "subject": "Science",
            "num_questions": 5,
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["topic"] == "Photosynthesis"
    assert body["subject"] == "Science"
    assert body["grade_level"] == "7"
    assert body["total_points"] == 10
    # The endpoint surfaces the question count and the full quiz payload.
    assert body["question_count"] == 0
    assert body["quiz"]["topic"] == "Photosynthesis"
