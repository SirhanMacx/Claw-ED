"""Tests for the background task queue."""

from __future__ import annotations

from pathlib import Path

import pytest

from clawed.task_queue import Task, TaskQueue, TaskStatus, TaskType


@pytest.fixture()
def queue(tmp_path: Path) -> TaskQueue:
    """Create a TaskQueue backed by a temporary SQLite database."""
    q = TaskQueue(db_path=tmp_path / "test_queue.db")
    yield q
    q.close()


# ── Submit & ID ───────────────────────────────────────────────────────


class TestSubmit:
    def test_submit_returns_task_id(self, queue: TaskQueue) -> None:
        task_id = queue.submit(TaskType.GENERATE_LESSON, {"topic": "WWI"})
        assert isinstance(task_id, str)
        assert len(task_id) == 12

    def test_submit_string_task_type(self, queue: TaskQueue) -> None:
        task_id = queue.submit("generate_unit", {"topic": "Fractions"})
        assert isinstance(task_id, str)

    def test_submit_creates_queued_task(self, queue: TaskQueue) -> None:
        task_id = queue.submit(TaskType.GENERATE_UNIT, {"topic": "Photosynthesis"})
        task = queue.get_status(task_id)
        assert task is not None
        assert task.status == TaskStatus.QUEUED
        assert task.task_type == TaskType.GENERATE_UNIT


# ── Status ────────────────────────────────────────────────────────────


class TestGetStatus:
    def test_get_status_returns_correct_status(self, queue: TaskQueue) -> None:
        task_id = queue.submit(TaskType.GENERATE_LESSON, {"topic": "Civil War"})
        task = queue.get_status(task_id)
        assert task is not None
        assert task.status == TaskStatus.QUEUED
        assert task.payload == {"topic": "Civil War"}

    def test_get_status_missing_returns_none(self, queue: TaskQueue) -> None:
        assert queue.get_status("nonexistent_id") is None

    def test_get_status_preserves_payload(self, queue: TaskQueue) -> None:
        payload = {"topic": "WWII", "grade": "11", "subject": "History"}
        task_id = queue.submit(TaskType.GENERATE_UNIT, payload)
        task = queue.get_status(task_id)
        assert task is not None
        assert task.payload == payload


# ── List tasks ────────────────────────────────────────────────────────


class TestListTasks:
    def test_list_tasks_empty(self, queue: TaskQueue) -> None:
        assert queue.list_tasks() == []

    def test_list_tasks_shows_recent(self, queue: TaskQueue) -> None:
        queue.submit(TaskType.GENERATE_LESSON, {"n": 1})
        queue.submit(TaskType.GENERATE_UNIT, {"n": 2})
        queue.submit(TaskType.GENERATE_WORKSHEET, {"n": 3})
        tasks = queue.list_tasks()
        assert len(tasks) == 3

    def test_list_tasks_respects_limit(self, queue: TaskQueue) -> None:
        for i in range(5):
            queue.submit(TaskType.GENERATE_ASSESSMENT, {"n": i})
        assert len(queue.list_tasks(limit=3)) == 3

    def test_list_tasks_newest_first(self, queue: TaskQueue) -> None:
        id1 = queue.submit(TaskType.GENERATE_LESSON, {"order": "first"})
        id2 = queue.submit(TaskType.GENERATE_LESSON, {"order": "second"})
        tasks = queue.list_tasks()
        assert tasks[0].id == id2
        assert tasks[1].id == id1


# ── Mark done / failed ────────────────────────────────────────────────


class TestMarkDoneAndFailed:
    def test_mark_done(self, queue: TaskQueue) -> None:
        task_id = queue.submit(TaskType.GENERATE_LESSON)
        queue.next_queued()
        queue.mark_done(task_id, {"title": "Lesson 1"})
        task = queue.get_status(task_id)
        assert task is not None
        assert task.status == TaskStatus.DONE
        assert task.result == {"title": "Lesson 1"}
        assert task.completed_at is not None

    def test_mark_failed(self, queue: TaskQueue) -> None:
        task_id = queue.submit(TaskType.GENERATE_UNIT)
        queue.next_queued()
        queue.mark_failed(task_id, "LLM timeout")
        task = queue.get_status(task_id)
        assert task is not None
        assert task.status == TaskStatus.FAILED
        assert task.error == "LLM timeout"
        assert task.completed_at is not None


# ── Next queued (worker pop) ──────────────────────────────────────────


class TestNextQueued:
    def test_next_queued_pops_oldest(self, queue: TaskQueue) -> None:
        id1 = queue.submit(TaskType.GENERATE_LESSON, {"n": 1})
        queue.submit(TaskType.GENERATE_LESSON, {"n": 2})
        task = queue.next_queued()
        assert task is not None
        assert task.id == id1
        assert task.status == TaskStatus.RUNNING

    def test_next_queued_returns_none_when_empty(self, queue: TaskQueue) -> None:
        assert queue.next_queued() is None

    def test_next_queued_skips_running(self, queue: TaskQueue) -> None:
        queue.submit(TaskType.GENERATE_LESSON, {"n": 1})  # id1 — consumed below
        id2 = queue.submit(TaskType.GENERATE_LESSON, {"n": 2})
        queue.next_queued()  # pops id1
        task = queue.next_queued()  # should pop id2
        assert task is not None
        assert task.id == id2


# ── Get result ────────────────────────────────────────────────────────


class TestGetResult:
    def test_get_result_returns_result(self, queue: TaskQueue) -> None:
        task_id = queue.submit(TaskType.GENERATE_LESSON)
        queue.next_queued()
        queue.mark_done(task_id, {"output": "Great lesson"})
        result = queue.get_result(task_id)
        assert result == {"output": "Great lesson"}

    def test_get_result_returns_none_for_queued(self, queue: TaskQueue) -> None:
        task_id = queue.submit(TaskType.GENERATE_LESSON)
        assert queue.get_result(task_id) is None

    def test_get_result_returns_none_for_missing(self, queue: TaskQueue) -> None:
        assert queue.get_result("does_not_exist") is None


# ── Task model ────────────────────────────────────────────────────────


class TestTaskModel:
    def test_task_defaults(self) -> None:
        task = Task(task_type=TaskType.GENERATE_LESSON)
        assert task.status == TaskStatus.QUEUED
        assert task.result is None
        assert task.error is None
        assert len(task.id) == 12

    def test_all_task_types_valid(self) -> None:
        for tt in TaskType:
            task = Task(task_type=tt)
            assert task.task_type == tt
