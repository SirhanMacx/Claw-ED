"""Tests for session compression."""
import json
import sqlite3

import pytest


@pytest.fixture()
def _session_db(tmp_path, monkeypatch):
    """Redirect sessions.db to tmp_path."""
    monkeypatch.setenv("EDUAGENT_DATA_DIR", str(tmp_path))
    # Reset module state so it picks up the new path
    import clawed.agent_core.memory.sessions as sess
    monkeypatch.setattr(sess, "_initialized", False)

    # Create sessions table
    db = tmp_path / "memory" / "sessions.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(db)) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_id TEXT NOT NULL,
                transport TEXT NOT NULL DEFAULT 'cli',
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TEXT NOT NULL
            )
        """)
    return db


def _insert_turns(db_path, teacher_id, count, prefix="Turn"):
    """Insert N test turns into sessions."""
    with sqlite3.connect(str(db_path)) as conn:
        for i in range(count):
            role = "user" if i % 2 == 0 else "assistant"
            content = f"{prefix} {i}: Make me a lesson on Topic {i // 2}"
            conn.execute(
                "INSERT INTO sessions (teacher_id, transport, role, content, timestamp) "
                "VALUES (?, 'cli', ?, ?, ?)",
                (teacher_id, role, content, f"2026-04-07T{10 + i // 60:02d}:{i % 60:02d}:00Z"),
            )


class TestExtractStructuredFields:
    def test_extracts_topics(self):
        from clawed.agent_core.memory.session_compress import extract_structured_fields
        turns = [
            {"role": "user", "content": "Make me a lesson on the American Revolution"},
            {"role": "assistant", "content": "Building your lesson now."},
        ]
        fields = extract_structured_fields(turns)
        assert len(fields["topics"]) >= 1

    def test_extracts_materials(self):
        from clawed.agent_core.memory.session_compress import extract_structured_fields
        turns = [
            {"role": "assistant", "content": "Generated: Revolution_slides.pptx"},
        ]
        fields = extract_structured_fields(turns)
        assert len(fields["materials_generated"]) >= 1

    def test_extracts_decisions(self):
        from clawed.agent_core.memory.session_compress import extract_structured_fields
        turns = [
            {"role": "user", "content": "I prefer shorter lessons with more visuals"},
        ]
        fields = extract_structured_fields(turns)
        assert len(fields["decisions"]) >= 1

    def test_handles_empty(self):
        from clawed.agent_core.memory.session_compress import extract_structured_fields
        fields = extract_structured_fields([])
        assert fields["topics"] == []
        assert fields["materials_generated"] == []


class TestHeuristicSummary:
    def test_produces_summary(self):
        from clawed.agent_core.memory.session_compress import (
            _heuristic_summary,
            extract_structured_fields,
        )
        turns = [
            {"role": "user", "content": "Make a lesson on Civil War"},
            {"role": "assistant", "content": "Generated: civil_war.pptx"},
        ]
        fields = extract_structured_fields(turns)
        summary = _heuristic_summary(turns, fields)
        assert "2 turns" in summary
        assert isinstance(summary, str)
        assert len(summary) > 10


class TestCompressOldSessions:
    def test_no_compression_below_threshold(self, _session_db):
        from clawed.agent_core.memory.session_compress import compress_old_sessions
        _insert_turns(_session_db, "t1", 30)
        result = compress_old_sessions("t1")
        assert result == 0

    def test_compresses_at_threshold(self, _session_db):
        from clawed.agent_core.memory.session_compress import compress_old_sessions
        _insert_turns(_session_db, "t1", 50)
        result = compress_old_sessions("t1")
        assert result == 20  # COMPRESS_BATCH

    def test_keeps_recent_turns(self, _session_db):
        from clawed.agent_core.memory.session_compress import compress_old_sessions
        _insert_turns(_session_db, "t1", 50)
        compress_old_sessions("t1")

        # Recent turns should still exist
        with sqlite3.connect(str(_session_db)) as conn:
            remaining = conn.execute(
                "SELECT COUNT(*) FROM sessions WHERE teacher_id = 't1'",
            ).fetchone()[0]
        assert remaining == 30  # 50 - 20 compressed

    def test_creates_summary_record(self, _session_db):
        from clawed.agent_core.memory.session_compress import compress_old_sessions
        _insert_turns(_session_db, "t1", 50)
        compress_old_sessions("t1")

        with sqlite3.connect(str(_session_db)) as conn:
            summaries = conn.execute(
                "SELECT * FROM session_summaries WHERE teacher_id = 't1'",
            ).fetchall()
        assert len(summaries) == 1

    def test_summary_has_turn_count(self, _session_db):
        from clawed.agent_core.memory.session_compress import compress_old_sessions
        _insert_turns(_session_db, "t1", 50)
        compress_old_sessions("t1")

        with sqlite3.connect(str(_session_db)) as conn:
            conn.row_factory = sqlite3.Row
            s = conn.execute(
                "SELECT * FROM session_summaries WHERE teacher_id = 't1'",
            ).fetchone()
        assert s["turn_count"] == 20
        assert json.loads(s["original_turn_ids"]) != []

    def test_deletes_compressed_turns(self, _session_db):
        from clawed.agent_core.memory.session_compress import compress_old_sessions
        _insert_turns(_session_db, "t1", 50)

        # Get IDs of oldest 20
        with sqlite3.connect(str(_session_db)) as conn:
            old_ids = [
                r[0] for r in conn.execute(
                    "SELECT id FROM sessions WHERE teacher_id = 't1' "
                    "ORDER BY timestamp ASC LIMIT 20",
                ).fetchall()
            ]

        compress_old_sessions("t1")

        with sqlite3.connect(str(_session_db)) as conn:
            for oid in old_ids:
                row = conn.execute(
                    "SELECT 1 FROM sessions WHERE id = ?", (oid,),
                ).fetchone()
                assert row is None, f"Turn {oid} should have been deleted"

    def test_teacher_isolation(self, _session_db):
        from clawed.agent_core.memory.session_compress import compress_old_sessions
        _insert_turns(_session_db, "t1", 50)
        _insert_turns(_session_db, "t2", 50)
        compress_old_sessions("t1")

        # t2 should be untouched
        with sqlite3.connect(str(_session_db)) as conn:
            t2_count = conn.execute(
                "SELECT COUNT(*) FROM sessions WHERE teacher_id = 't2'",
            ).fetchone()[0]
        assert t2_count == 50

    def test_idempotent(self, _session_db):
        from clawed.agent_core.memory.session_compress import compress_old_sessions
        _insert_turns(_session_db, "t1", 42)  # Just above threshold
        r1 = compress_old_sessions("t1")
        r2 = compress_old_sessions("t1")
        assert r1 == 20
        assert r2 == 0  # Nothing left to compress


class TestMaybeCompressSessions:
    def test_triggers(self, _session_db):
        from clawed.agent_core.memory.session_compress import maybe_compress_sessions
        _insert_turns(_session_db, "t1", 50)
        result = maybe_compress_sessions("t1")
        assert result == 20

    def test_no_trigger_below(self, _session_db):
        from clawed.agent_core.memory.session_compress import maybe_compress_sessions
        _insert_turns(_session_db, "t1", 30)
        result = maybe_compress_sessions("t1")
        assert result == 0


class TestGetFullSessionTimeline:
    def test_returns_timeline(self, _session_db):
        from clawed.agent_core.memory.session_compress import (
            compress_old_sessions,
            get_full_session_timeline,
        )
        _insert_turns(_session_db, "t1", 50)
        compress_old_sessions("t1")
        timeline = get_full_session_timeline("t1")
        assert len(timeline) > 0
        types = {t["type"] for t in timeline}
        assert "summary" in types
        assert "turn" in types

    def test_empty_for_new_teacher(self, _session_db):
        from clawed.agent_core.memory.session_compress import get_full_session_timeline
        timeline = get_full_session_timeline("new_teacher")
        assert timeline == []
