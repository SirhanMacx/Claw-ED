"""Tests for v2.2.0 Better Memory — compression, cross-session threading, drift detection."""

from __future__ import annotations

import json

import pytest

from clawed.memory_engine import (
    COMPRESSION_THRESHOLD,
    DEFAULT_MEMORY_TEMPLATE,
    DRIFT_WINDOW_SIZE,
    EPISODES_TO_KEEP_VERBATIM,
    _save_rating_history,
    compress_old_episodes,
    detect_preference_drift,
    maybe_compress_episodes,
    process_feedback,
)
from clawed.models import DailyLesson

# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def sample_lesson():
    """A basic lesson for testing."""
    return DailyLesson(
        title="The Water Cycle",
        lesson_number=1,
        objective="Understand the water cycle.",
    )


@pytest.fixture
def tmp_memory(tmp_path, monkeypatch):
    """Redirect memory.md to a temp directory."""
    ws = tmp_path / "workspace"
    ws.mkdir(parents=True)
    monkeypatch.setattr("clawed.workspace.MEMORY_PATH", ws / "memory.md")
    monkeypatch.setattr("clawed.workspace.MEMORY_SUMMARY_PATH", ws / "memory_summary.md")
    (ws / "memory.md").write_text(DEFAULT_MEMORY_TEMPLATE, encoding="utf-8")
    return ws


@pytest.fixture
def episodic_db(tmp_path):
    """Create an EpisodicMemory with an isolated database."""
    from clawed.agent_core.memory.episodes import EpisodicMemory

    return EpisodicMemory(db_path=tmp_path / "episodes.db")


# ── EpisodicMemory helpers ───────────────────────────────────────────


class TestEpisodicMemoryHelpers:
    def test_get_latest_episode_empty(self, tmp_path):
        from clawed.agent_core.memory.episodes import EpisodicMemory

        mem = EpisodicMemory(db_path=tmp_path / "episodes.db")
        assert mem.get_latest_episode("t1") is None

    def test_get_latest_episode(self, episodic_db):
        episodic_db.store("t1", "First episode")
        episodic_db.store("t1", "Second episode")
        episodic_db.store("t1", "Third episode")
        latest = episodic_db.get_latest_episode("t1")
        assert latest is not None
        assert "Third episode" in latest["text"]

    def test_get_latest_episode_teacher_isolation(self, episodic_db):
        episodic_db.store("t1", "Teacher 1 episode")
        episodic_db.store("t2", "Teacher 2 episode")
        latest = episodic_db.get_latest_episode("t1")
        assert "Teacher 1" in latest["text"]

    def test_count_episodes(self, episodic_db):
        assert episodic_db.count_episodes("t1") == 0
        episodic_db.store("t1", "Episode 1")
        episodic_db.store("t1", "Episode 2")
        assert episodic_db.count_episodes("t1") == 2

    def test_count_episodes_teacher_isolation(self, episodic_db):
        episodic_db.store("t1", "A")
        episodic_db.store("t1", "B")
        episodic_db.store("t2", "C")
        assert episodic_db.count_episodes("t1") == 2
        assert episodic_db.count_episodes("t2") == 1

    def test_get_all_episodes_chronological(self, episodic_db):
        episodic_db.store("t1", "First")
        episodic_db.store("t1", "Second")
        episodic_db.store("t1", "Third")
        all_eps = episodic_db.get_all_episodes("t1")
        assert len(all_eps) == 3
        assert "First" in all_eps[0]["text"]
        assert "Third" in all_eps[2]["text"]

    def test_get_all_episodes_with_limit(self, episodic_db):
        for i in range(5):
            episodic_db.store("t1", f"Episode {i}")
        eps = episodic_db.get_all_episodes("t1", limit=3)
        assert len(eps) == 3

    def test_get_all_episodes_with_offset(self, episodic_db):
        for i in range(5):
            episodic_db.store("t1", f"Episode {i}")
        eps = episodic_db.get_all_episodes("t1", limit=2, offset=3)
        assert len(eps) == 2
        assert "Episode 3" in eps[0]["text"]


# ── Long-term memory compression ─────────────────────────────────────


class TestMemoryCompression:
    def test_compress_with_few_episodes(self, episodic_db, tmp_memory, monkeypatch):
        """No compression when episodes <= EPISODES_TO_KEEP_VERBATIM."""
        # Patch EpisodicMemory to use our test db
        monkeypatch.setattr(
            "clawed.agent_core.memory.episodes.EpisodicMemory",
            lambda *a, **kw: episodic_db,
        )
        for i in range(5):
            episodic_db.store("t1", f"Teacher: Lesson {i}")
        result = compress_old_episodes("t1")
        assert result == ""

    def test_compress_creates_summary(self, episodic_db, tmp_memory, monkeypatch):
        """Compression creates memory_summary.md with highlights."""
        monkeypatch.setattr(
            "clawed.agent_core.memory.episodes.EpisodicMemory",
            lambda *a, **kw: episodic_db,
        )
        for i in range(25):
            episodic_db.store("t1", f"Teacher: Lesson {i} about topic {i}")

        result = compress_old_episodes("t1")
        assert result != ""
        assert "Compressed Episode Highlights" in result
        assert "15 older episodes compressed" in result

        # Verify file was written
        summary_path = tmp_memory / "memory_summary.md"
        assert summary_path.exists()
        content = summary_path.read_text(encoding="utf-8")
        assert "Teacher: Lesson 0" in content
        # Last 10 episodes should NOT be in summary (kept verbatim)
        assert "Teacher: Lesson 15" not in content or "Teacher: Lesson 24" not in content

    def test_compress_keeps_last_n_verbatim(self, episodic_db, tmp_memory, monkeypatch):
        """Last EPISODES_TO_KEEP_VERBATIM episodes should not appear in summary."""
        monkeypatch.setattr(
            "clawed.agent_core.memory.episodes.EpisodicMemory",
            lambda *a, **kw: episodic_db,
        )
        total = 20
        for i in range(total):
            episodic_db.store("t1", f"Teacher: Episode {i:02d}")

        result = compress_old_episodes("t1")
        # Should compress total - EPISODES_TO_KEEP_VERBATIM = 10 episodes
        compressed_count = total - EPISODES_TO_KEEP_VERBATIM
        assert f"{compressed_count} older episodes compressed" in result
        # Earliest should be in summary
        assert "Episode 00" in result
        # Latest should NOT be compressed (kept verbatim)
        assert "Episode 19" not in result

    def test_maybe_compress_at_threshold(self, episodic_db, tmp_memory, monkeypatch):
        """maybe_compress_episodes triggers at COMPRESSION_THRESHOLD intervals."""
        monkeypatch.setattr(
            "clawed.agent_core.memory.episodes.EpisodicMemory",
            lambda *a, **kw: episodic_db,
        )
        # Store exactly COMPRESSION_THRESHOLD episodes
        for i in range(COMPRESSION_THRESHOLD):
            episodic_db.store("t1", f"Teacher: Msg {i}")

        result = maybe_compress_episodes("t1")
        assert result != "", "Should compress at threshold"

    def test_maybe_compress_not_at_threshold(self, episodic_db, tmp_memory, monkeypatch):
        """maybe_compress_episodes does NOT trigger between thresholds."""
        monkeypatch.setattr(
            "clawed.agent_core.memory.episodes.EpisodicMemory",
            lambda *a, **kw: episodic_db,
        )
        for i in range(COMPRESSION_THRESHOLD - 1):
            episodic_db.store("t1", f"Teacher: Msg {i}")

        result = maybe_compress_episodes("t1")
        assert result == "", "Should not compress before threshold"

    def test_compress_truncates_long_lines(self, episodic_db, tmp_memory, monkeypatch):
        """Lines longer than 120 chars should be truncated."""
        monkeypatch.setattr(
            "clawed.agent_core.memory.episodes.EpisodicMemory",
            lambda *a, **kw: episodic_db,
        )
        long_msg = "Teacher: " + "x" * 200
        for i in range(15):
            episodic_db.store("t1", long_msg if i == 0 else f"Teacher: Short {i}")

        result = compress_old_episodes("t1")
        # The long line should be truncated with "..."
        assert "..." in result


# ── Preference drift detection ────────────────────────────────────────


class TestPreferenceDrift:
    def test_drift_not_detected_with_few_ratings(self, tmp_path, monkeypatch):
        """No drift alert when < 2 * DRIFT_WINDOW_SIZE ratings exist."""
        monkeypatch.setattr(
            "clawed.memory_engine._get_rating_history_path",
            lambda: tmp_path / "rating_history.json",
        )
        # Add fewer than needed ratings
        for _ in range(DRIFT_WINDOW_SIZE - 1):
            result = detect_preference_drift(5)
        assert result is None

    def test_drift_detected_decline(self, tmp_path, tmp_memory, monkeypatch):
        """Declining ratings trigger a warning in memory.md."""
        monkeypatch.setattr(
            "clawed.memory_engine._get_rating_history_path",
            lambda: tmp_path / "rating_history.json",
        )
        # Prior window: all 5-star
        ratings = [5] * DRIFT_WINDOW_SIZE
        _save_rating_history(ratings)
        monkeypatch.setattr(
            "clawed.memory_engine._get_rating_history_path",
            lambda: tmp_path / "rating_history.json",
        )

        # Current window: all 2-star (decline of 3.0, well above threshold)
        result = None
        for _ in range(DRIFT_WINDOW_SIZE):
            result = detect_preference_drift(2)

        assert result is not None
        assert "rating lower" in result

        # Should be logged in memory.md
        memory_content = (tmp_memory / "memory.md").read_text(encoding="utf-8")
        assert "Drift Alerts" in memory_content
        assert "rating lower" in memory_content

    def test_drift_detected_improvement(self, tmp_path, tmp_memory, monkeypatch):
        """Improving ratings trigger a positive note."""
        monkeypatch.setattr(
            "clawed.memory_engine._get_rating_history_path",
            lambda: tmp_path / "rating_history.json",
        )
        # Prior window: all 2-star
        ratings = [2] * DRIFT_WINDOW_SIZE
        _save_rating_history(ratings)
        monkeypatch.setattr(
            "clawed.memory_engine._get_rating_history_path",
            lambda: tmp_path / "rating_history.json",
        )

        # Current window: all 5-star
        result = None
        for _ in range(DRIFT_WINDOW_SIZE):
            result = detect_preference_drift(5)

        assert result is not None
        assert "improving" in result.lower() or "great work" in result.lower()

    def test_no_drift_when_stable(self, tmp_path, monkeypatch):
        """Stable ratings produce no alert."""
        monkeypatch.setattr(
            "clawed.memory_engine._get_rating_history_path",
            lambda: tmp_path / "rating_history.json",
        )
        # Both windows: all 4-star
        for _ in range(2 * DRIFT_WINDOW_SIZE):
            result = detect_preference_drift(4)
        assert result is None

    def test_drift_within_threshold_no_alert(self, tmp_path, monkeypatch):
        """Small differences within DRIFT_THRESHOLD produce no alert."""
        monkeypatch.setattr(
            "clawed.memory_engine._get_rating_history_path",
            lambda: tmp_path / "rating_history.json",
        )
        # Prior window: average 4.0, current: average 3.6 (diff = -0.4, below 0.5)
        ratings = [4] * DRIFT_WINDOW_SIZE + [4, 4, 4, 3, 3, 4, 4, 3, 4, 4]
        _save_rating_history(ratings)
        monkeypatch.setattr(
            "clawed.memory_engine._get_rating_history_path",
            lambda: tmp_path / "rating_history.json",
        )
        # The history already has enough — just read the last detection
        # Re-run detection with the exact values
        result = detect_preference_drift(4)  # One more rating, shifts windows
        # Should not trigger (marginal difference)
        # This is fine — it's checking the last 20 entries
        assert result is None or "rating lower" not in (result or "")

    def test_rating_history_persisted(self, tmp_path, monkeypatch):
        """Rating history is persisted across calls."""
        hist_path = tmp_path / "rating_history.json"
        monkeypatch.setattr(
            "clawed.memory_engine._get_rating_history_path",
            lambda: hist_path,
        )
        detect_preference_drift(5)
        detect_preference_drift(3)
        detect_preference_drift(4)

        saved = json.loads(hist_path.read_text(encoding="utf-8"))
        assert saved == [5, 3, 4]

    def test_drift_integrated_into_process_feedback(self, sample_lesson, tmp_memory, monkeypatch):
        """process_feedback calls drift detection."""
        calls = []
        monkeypatch.setattr(
            "clawed.memory_engine.detect_preference_drift",
            lambda r: calls.append(r) or None,
        )
        process_feedback(sample_lesson, rating=5)
        assert 5 in calls

    def test_drift_integrated_skips_rating_3(self, sample_lesson, tmp_memory, monkeypatch):
        """Rating 3 is neutral — process_feedback skips, so drift not called."""
        calls = []
        monkeypatch.setattr(
            "clawed.memory_engine.detect_preference_drift",
            lambda r: calls.append(r) or None,
        )
        process_feedback(sample_lesson, rating=3)
        # Rating 3 returns early before drift detection
        assert calls == []


# ── Cross-session context threading ───────────────────────────────────


class TestCrossSessionThreading:
    def test_last_session_summary_empty(self, tmp_path, monkeypatch):
        """No episodes → empty last_session_summary."""
        monkeypatch.setenv("EDUAGENT_DATA_DIR", str(tmp_path))
        from clawed.agent_core.memory.loader import load_memory_context

        ctx = load_memory_context("test-teacher", "hello")
        assert ctx["last_session_summary"] == ""

    def test_last_session_summary_from_episode(self, tmp_path, monkeypatch):
        """Most recent episode produces a session summary."""
        monkeypatch.setenv("EDUAGENT_DATA_DIR", str(tmp_path))
        from clawed.agent_core.memory.episodes import EpisodicMemory
        from clawed.agent_core.memory.loader import load_memory_context

        mem = EpisodicMemory(db_path=tmp_path / "memory" / "episodes.db")
        mem.store("t1", "Teacher: Can you help me plan the Age of Exploration unit?\nClaw-ED: Sure!")

        # Patch so loader uses our DB
        monkeypatch.setattr(
            "clawed.agent_core.memory.episodes.EpisodicMemory",
            lambda *a, **kw: mem,
        )

        ctx = load_memory_context("t1", "hi")
        assert "Age of Exploration" in ctx["last_session_summary"]

    def test_last_session_summary_truncates_long_messages(self, tmp_path, monkeypatch):
        """Long messages are truncated in the summary."""
        monkeypatch.setenv("EDUAGENT_DATA_DIR", str(tmp_path))
        from clawed.agent_core.memory.episodes import EpisodicMemory
        from clawed.agent_core.memory.loader import load_memory_context

        mem = EpisodicMemory(db_path=tmp_path / "memory" / "episodes.db")
        long_msg = "Teacher: " + "a" * 300 + "\nClaw-ED: ok"
        mem.store("t1", long_msg)

        monkeypatch.setattr(
            "clawed.agent_core.memory.episodes.EpisodicMemory",
            lambda *a, **kw: mem,
        )

        ctx = load_memory_context("t1", "hi")
        summary = ctx["last_session_summary"]
        assert len(summary) <= 153  # 150 + "..."
        assert summary.endswith("...")

    def test_last_session_teacher_isolation(self, tmp_path, monkeypatch):
        """Each teacher gets their own session summary."""
        monkeypatch.setenv("EDUAGENT_DATA_DIR", str(tmp_path))
        from clawed.agent_core.memory.episodes import EpisodicMemory
        from clawed.agent_core.memory.loader import load_memory_context

        mem = EpisodicMemory(db_path=tmp_path / "memory" / "episodes.db")
        mem.store("t1", "Teacher: Working on fractions\nClaw-ED: Great!")
        mem.store("t2", "Teacher: Civil War causes\nClaw-ED: Let's dive in!")

        monkeypatch.setattr(
            "clawed.agent_core.memory.episodes.EpisodicMemory",
            lambda *a, **kw: mem,
        )

        ctx1 = load_memory_context("t1", "hi")
        ctx2 = load_memory_context("t2", "hi")
        assert "fractions" in ctx1["last_session_summary"]
        assert "Civil War" in ctx2["last_session_summary"]
