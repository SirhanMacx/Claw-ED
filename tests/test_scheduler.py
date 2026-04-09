"""Tests for the Claw-ED scheduler module."""

from __future__ import annotations

import json

import pytest

from clawed.scheduler import (
    DEFAULT_TASKS,
    EduScheduler,
    _parse_cron_expr,
    disable_task,
    enable_task,
    load_schedule_config,
    run_task,
    save_schedule_config,
    set_task_schedule,
)


@pytest.fixture
def tmp_schedule(tmp_path, monkeypatch):
    """Redirect schedule config to a temp directory."""
    config_path = tmp_path / "schedule.json"
    monkeypatch.setattr("clawed.scheduler.SCHEDULE_CONFIG_PATH", config_path)
    return config_path


@pytest.fixture
def tmp_workspace_for_scheduler(tmp_path, monkeypatch):
    """Also redirect workspace paths for tasks that write daily notes."""
    ws = tmp_path / "workspace"
    monkeypatch.setattr("clawed.workspace.WORKSPACE_DIR", ws)
    monkeypatch.setattr("clawed.workspace.IDENTITY_PATH", ws / "identity.md")
    monkeypatch.setattr("clawed.workspace.SOUL_PATH", ws / "soul.md")
    monkeypatch.setattr("clawed.workspace.MEMORY_PATH", ws / "memory.md")
    monkeypatch.setattr("clawed.workspace.HEARTBEAT_PATH", ws / "heartbeat.md")
    monkeypatch.setattr("clawed.workspace.NOTES_DIR", ws / "notes")
    monkeypatch.setattr("clawed.workspace.STUDENTS_DIR", ws / "students")
    return ws


# ── Default task definitions ──────────────────────────────────────────


class TestDefaultTasks:
    def test_has_all_expected_tasks(self):
        expected = {
            "morning-prep", "weekly-plan", "feedback-digest",
            "memory-compress", "student-digest",
            "gap-detection", "curriculum-watch", "self-distill",
        }
        assert set(DEFAULT_TASKS.keys()) == expected

    def test_each_task_has_required_fields(self):
        for name, task in DEFAULT_TASKS.items():
            assert "description" in task, f"{name} missing description"
            assert "cron" in task, f"{name} missing cron"
            assert "enabled" in task, f"{name} missing enabled"

    def test_morning_prep_defaults(self):
        task = DEFAULT_TASKS["morning-prep"]
        assert task["cron"]["hour"] == "6"
        # Core tasks are enabled by default (v4.9.2026.5+)
        assert task["enabled"] is True

    def test_core_tasks_enabled_by_default(self):
        """Core tasks (morning-prep, weekly-plan, gap-detection, curriculum-watch,
        self-distill) are enabled by default. Others start disabled."""
        core = {"morning-prep", "weekly-plan", "gap-detection",
                "curriculum-watch", "self-distill"}
        for name, task in DEFAULT_TASKS.items():
            if name in core:
                assert task["enabled"] is True, f"{name} should be enabled"
            else:
                assert task["enabled"] is False, f"{name} should start disabled"


# ── Config loading and saving ─────────────────────────────────────────


class TestScheduleConfig:
    def test_load_returns_defaults_when_no_file(self, tmp_schedule):
        config = load_schedule_config()
        assert "morning-prep" in config
        assert "weekly-plan" in config
        assert "feedback-digest" in config

    def test_save_and_load_round_trip(self, tmp_schedule):
        config = load_schedule_config()
        config["morning-prep"]["cron"]["hour"] = "7"
        save_schedule_config(config)

        loaded = load_schedule_config()
        assert loaded["morning-prep"]["cron"]["hour"] == "7"

    def test_save_creates_parent_dirs(self, tmp_path, monkeypatch):
        nested = tmp_path / "deep" / "nested" / "schedule.json"
        monkeypatch.setattr("clawed.scheduler.SCHEDULE_CONFIG_PATH", nested)
        config = load_schedule_config()
        save_schedule_config(config)
        assert nested.exists()

    def test_load_merges_saved_with_defaults(self, tmp_schedule):
        # Save only a partial override
        tmp_schedule.write_text(json.dumps({
            "morning-prep": {"cron": {"hour": "8", "minute": "30"}}
        }))
        config = load_schedule_config()
        # Should have the override
        assert config["morning-prep"]["cron"]["hour"] == "8"
        assert config["morning-prep"]["cron"]["minute"] == "30"
        # Should still have other defaults
        assert "weekly-plan" in config
        assert "feedback-digest" in config

    def test_load_handles_corrupted_file(self, tmp_schedule):
        tmp_schedule.write_text("not json at all {{{")
        # Should not raise -- falls back to defaults
        config = load_schedule_config()
        assert "morning-prep" in config


# ── Enable / disable ─────────────────────────────────────────────────


class TestEnableDisable:
    def test_enable_task(self, tmp_schedule):
        disable_task("morning-prep")
        config = load_schedule_config()
        assert config["morning-prep"]["enabled"] is False

        enable_task("morning-prep")
        config = load_schedule_config()
        assert config["morning-prep"]["enabled"] is True

    def test_disable_task(self, tmp_schedule):
        enable_task("morning-prep")
        disable_task("morning-prep")
        config = load_schedule_config()
        assert config["morning-prep"]["enabled"] is False

    def test_enable_unknown_task(self, tmp_schedule):
        assert enable_task("nonexistent") is False

    def test_disable_unknown_task(self, tmp_schedule):
        assert disable_task("nonexistent") is False


# ── Set task schedule ─────────────────────────────────────────────────


class TestSetTaskSchedule:
    def test_set_time(self, tmp_schedule):
        assert set_task_schedule("morning-prep", "7:30") is True
        config = load_schedule_config()
        assert config["morning-prep"]["cron"]["hour"] == "7"
        assert config["morning-prep"]["cron"]["minute"] == "30"

    def test_set_day_and_time(self, tmp_schedule):
        assert set_task_schedule("weekly-plan", "sat 18:00") is True
        config = load_schedule_config()
        assert config["weekly-plan"]["cron"]["day_of_week"] == "sat"
        assert config["weekly-plan"]["cron"]["hour"] == "18"

    def test_set_key_value(self, tmp_schedule):
        assert set_task_schedule("feedback-digest", "hour=21 minute=15") is True
        config = load_schedule_config()
        assert config["feedback-digest"]["cron"]["hour"] == "21"
        assert config["feedback-digest"]["cron"]["minute"] == "15"

    def test_set_unknown_task(self, tmp_schedule):
        assert set_task_schedule("nonexistent", "6:00") is False


# ── Parse cron expression ─────────────────────────────────────────────


class TestParseCronExpr:
    def test_simple_time(self):
        result = _parse_cron_expr("6:00")
        assert result == {"hour": "6", "minute": "0"}

    def test_time_with_minutes(self):
        result = _parse_cron_expr("14:30")
        assert result == {"hour": "14", "minute": "30"}

    def test_day_and_time(self):
        result = _parse_cron_expr("sun 19:00")
        assert result == {"day_of_week": "sun", "hour": "19", "minute": "0"}

    def test_key_value_format(self):
        result = _parse_cron_expr("hour=6 minute=0")
        assert result == {"hour": "6", "minute": "0"}

    def test_hour_only(self):
        result = _parse_cron_expr("6")
        assert result == {"hour": "6", "minute": "0"}


# ── Manual run ─────────────────────────────────────────────────────────


class TestRunTask:
    @pytest.mark.asyncio
    async def test_run_known_task(self, tmp_schedule, tmp_workspace_for_scheduler):
        result = await run_task("feedback-digest")
        assert "Feedback digest" in result

    @pytest.mark.asyncio
    async def test_run_unknown_task_raises(self, tmp_schedule):
        with pytest.raises(ValueError, match="Unknown task"):
            await run_task("does-not-exist")

    @pytest.mark.asyncio
    async def test_run_logs_to_daily_notes(self, tmp_schedule, tmp_workspace_for_scheduler):
        await run_task("morning-prep")
        from clawed.workspace import get_daily_notes
        notes = get_daily_notes()
        assert "morning-prep" in notes.lower() or "Morning prep" in notes


# ── EduScheduler class ────────────────────────────────────────────────


class TestEduScheduler:
    def test_creation(self, tmp_schedule):
        scheduler = EduScheduler()
        assert scheduler._scheduler is None
        assert "morning-prep" in scheduler._config

    def test_get_jobs_info(self, tmp_schedule):
        scheduler = EduScheduler()
        jobs = scheduler.get_jobs_info()
        assert len(jobs) >= 5
        names = {j["name"] for j in jobs}
        assert "morning-prep" in names
        assert "weekly-plan" in names

    def test_running_property_false_before_start(self, tmp_schedule):
        scheduler = EduScheduler()
        assert scheduler.running is False

    def test_register_jobs_creates_scheduler(self, tmp_schedule):
        scheduler = EduScheduler()
        scheduler.register_jobs()
        assert scheduler._scheduler is not None

    def test_jobs_info_includes_enabled_status(self, tmp_schedule):
        scheduler = EduScheduler()
        jobs = scheduler.get_jobs_info()
        for job in jobs:
            assert "enabled" in job
            assert "description" in job
            assert "cron" in job
