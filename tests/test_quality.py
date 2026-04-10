"""Tests for quality tracker (Phase 4: Self-Improvement)."""

from __future__ import annotations

import pytest

from clawed.agent_core import quality


@pytest.fixture(autouse=True)
def _isolate_quality(tmp_path, monkeypatch):
    monkeypatch.setenv("EDUAGENT_DATA_DIR", str(tmp_path))
    quality.reset_db()
    yield
    quality.reset_db()


class TestRecordGeneration:
    def test_record_and_retrieve_stats(self):
        gen_id = quality.record_generation(
            "t1",
            "lesson",
            topic="WW2",
            subject="History",
            grade="10",
            scores={"voice_match": 0.8, "standards": 0.9},
        )
        assert gen_id > 0
        stats = quality.get_stats("t1")
        assert stats["total_generations"] == 1

    def test_multiple_generations(self):
        for i in range(5):
            quality.record_generation("t1", "lesson", topic=f"Topic {i}")
        stats = quality.get_stats("t1")
        assert stats["total_generations"] == 5


class TestRating:
    def test_record_rating(self):
        gen_id = quality.record_generation("t1", "lesson", topic="Cells")
        quality.record_rating(gen_id, 4, feedback="Good but needs more scaffolding")
        stats = quality.get_stats("t1")
        assert stats["rated"] == 1
        assert stats["avg_rating"] == 4.0

    def test_multiple_ratings(self):
        id1 = quality.record_generation("t1", "lesson")
        id2 = quality.record_generation("t1", "lesson")
        quality.record_rating(id1, 5)
        quality.record_rating(id2, 3)
        stats = quality.get_stats("t1")
        assert stats["avg_rating"] == 4.0


class TestEdits:
    def test_record_edit(self):
        gen_id = quality.record_generation("t1", "lesson")
        quality.record_edit(gen_id, "Changed Do Now from recall to analysis")
        stats = quality.get_stats("t1")
        assert stats["edited"] == 1
        assert stats["edit_rate"] == 1.0

    def test_get_edit_patterns(self):
        for i in range(3):
            gen_id = quality.record_generation("t1", "lesson")
            quality.record_edit(gen_id, "Added more scaffolding")
        patterns = quality.get_edit_patterns("t1")
        assert len(patterns) == 3
        assert all(p == "Added more scaffolding" for p in patterns)


class TestRollingAverage:
    def test_empty_returns_empty(self):
        assert quality.get_rolling_average("t1") == {}

    def test_average_calculation(self):
        quality.record_generation("t1", "lesson", scores={"voice": 0.8})
        quality.record_generation("t1", "lesson", scores={"voice": 0.6})
        avg = quality.get_rolling_average("t1")
        assert abs(avg["voice"] - 0.7) < 0.01

    def test_filter_by_type(self):
        quality.record_generation("t1", "lesson", scores={"voice": 0.9})
        quality.record_generation("t1", "quiz", scores={"voice": 0.5})
        lesson_avg = quality.get_rolling_average("t1", "lesson")
        assert abs(lesson_avg["voice"] - 0.9) < 0.01


class TestPatterns:
    def test_record_and_get_pattern(self):
        quality.record_pattern("t1", "edit", "Teacher always adds more scaffolding")
        quality.record_pattern("t1", "edit", "Teacher always adds more scaffolding")
        patterns = quality.get_patterns("t1", min_occurrences=2)
        assert len(patterns) == 1
        assert patterns[0]["occurrences"] == 2

    def test_pattern_below_threshold(self):
        quality.record_pattern("t1", "edit", "One-off edit")
        patterns = quality.get_patterns("t1", min_occurrences=2)
        assert len(patterns) == 0

    def test_different_patterns(self):
        for _ in range(3):
            quality.record_pattern("t1", "edit", "Adds scaffolding")
            quality.record_pattern("t1", "style", "Prefers TEA format")
        patterns = quality.get_patterns("t1", min_occurrences=2)
        assert len(patterns) == 2


class TestIsolation:
    def test_teachers_isolated(self):
        quality.record_generation("t1", "lesson")
        quality.record_generation("t2", "lesson")
        assert quality.get_stats("t1")["total_generations"] == 1
        assert quality.get_stats("t2")["total_generations"] == 1
