"""Lightweight background task queue — SQLite-backed, asyncio-driven.

Teachers can submit long-running generation jobs (e.g. "generate all 10 lessons
for my WWI unit tonight") and check back later for results.

No Redis, no Celery — just asyncio + SQLite.
"""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import uuid
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

# ── Status & task type enums ──────────────────────────────────────────

class TaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class TaskType(str, Enum):
    GENERATE_LESSON = "generate_lesson"
    GENERATE_UNIT = "generate_unit"
    GENERATE_WORKSHEET = "generate_worksheet"
    GENERATE_ASSESSMENT = "generate_assessment"


# ── Task model ────────────────────────────────────────────────────────

class Task(BaseModel):
    """A single queued generation task."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    task_type: TaskType
    payload: dict[str, Any] = Field(default_factory=dict)
    status: TaskStatus = TaskStatus.QUEUED
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    completed_at: str | None = None


# ── Database layer ────────────────────────────────────────────────────

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS tasks (
    id            TEXT PRIMARY KEY,
    task_type     TEXT NOT NULL,
    payload_json  TEXT NOT NULL DEFAULT '{}',
    status        TEXT NOT NULL DEFAULT 'queued',
    result_json   TEXT,
    error         TEXT,
    created_at    TEXT NOT NULL,
    completed_at  TEXT
);
"""


def _default_db_path() -> Path:
    """Return the default database path inside the data directory."""
    db_dir = Path(os.environ.get("EDUAGENT_DATA_DIR", str(Path.home() / ".eduagent")))
    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / "task_queue.db"


class TaskQueue:
    """SQLite-backed task queue with async-friendly interface."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self._db_path = str(db_path or _default_db_path())
        self._conn: sqlite3.Connection | None = None
        self._ensure_table()

    # ── Connection management ─────────────────────────────────────────

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self._db_path)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _ensure_table(self) -> None:
        conn = self._get_conn()
        conn.execute(_CREATE_TABLE)
        conn.commit()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # ── Core operations ───────────────────────────────────────────────

    def submit(self, task_type: TaskType | str, payload: dict[str, Any] | None = None) -> str:
        """Submit a new task to the queue. Returns the task ID."""
        task = Task(
            task_type=TaskType(task_type),
            payload=payload or {},
        )
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO tasks (id, task_type, payload_json, status, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (task.id, task.task_type.value, json.dumps(task.payload), task.status.value, task.created_at),
        )
        conn.commit()
        return task.id

    def get_status(self, task_id: str) -> Task | None:
        """Retrieve a task by ID, or None if not found."""
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            return None
        return self._row_to_task(row)

    def get_result(self, task_id: str) -> dict[str, Any] | None:
        """Return the result dict for a completed task, or None."""
        task = self.get_status(task_id)
        if task is None:
            return None
        return task.result

    def list_tasks(self, limit: int = 20) -> list[Task]:
        """List the most recent tasks, newest first."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [self._row_to_task(r) for r in rows]

    def next_queued(self) -> Task | None:
        """Pop the oldest queued task (mark it as running)."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM tasks WHERE status = 'queued' ORDER BY created_at ASC LIMIT 1",
        ).fetchone()
        if row is None:
            return None
        task = self._row_to_task(row)
        conn.execute("UPDATE tasks SET status = 'running' WHERE id = ?", (task.id,))
        conn.commit()
        task.status = TaskStatus.RUNNING
        return task

    def mark_done(self, task_id: str, result: dict[str, Any]) -> None:
        """Mark a task as successfully completed with its result."""
        now = datetime.now(UTC).isoformat()
        conn = self._get_conn()
        conn.execute(
            "UPDATE tasks SET status = 'done', result_json = ?, completed_at = ? WHERE id = ?",
            (json.dumps(result), now, task_id),
        )
        conn.commit()

    def mark_failed(self, task_id: str, error: str) -> None:
        """Mark a task as failed with an error message."""
        now = datetime.now(UTC).isoformat()
        conn = self._get_conn()
        conn.execute(
            "UPDATE tasks SET status = 'failed', error = ?, completed_at = ? WHERE id = ?",
            (error, now, task_id),
        )
        conn.commit()

    # ── Helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _row_to_task(row: sqlite3.Row) -> Task:
        result_json = row["result_json"]
        return Task(
            id=row["id"],
            task_type=TaskType(row["task_type"]),
            payload=json.loads(row["payload_json"]) if row["payload_json"] else {},
            status=TaskStatus(row["status"]),
            result=json.loads(result_json) if result_json else None,
            error=row["error"],
            created_at=row["created_at"],
            completed_at=row["completed_at"],
        )


# ── Background worker ─────────────────────────────────────────────────


async def _execute_task(task: Task) -> dict[str, Any]:
    """Route a task to the appropriate generator and return the result."""
    from clawed.commands._helpers import load_persona_or_exit
    from clawed.models import AppConfig

    payload = task.payload
    config = AppConfig.load()

    if task.task_type == TaskType.GENERATE_LESSON:
        from clawed.lesson import generate_lesson
        from clawed.planner import load_unit

        unit = load_unit(Path(payload["unit_path"]))
        persona = load_persona_or_exit()
        lesson = await generate_lesson(
            lesson_number=payload.get("lesson_number", 1),
            unit=unit,
            persona=persona,
            config=config,
        )
        return lesson.model_dump()

    if task.task_type == TaskType.GENERATE_UNIT:
        from clawed.paths import data_dir
        from clawed.persona import load_persona
        from clawed.planner import plan_unit, save_unit
        persona_path = Path(payload.get("persona_path", data_dir() / "persona.json"))
        persona = load_persona(persona_path)
        unit = await plan_unit(
            subject=payload["subject"],
            grade_level=str(payload["grade"]),
            topic=payload["topic"],
            duration_weeks=payload.get("duration_weeks", 2),
            persona=persona,
            config=config,
        )
        out = Path(payload.get("output_dir", "clawed_output"))
        path = save_unit(unit, out)
        return {"title": unit.title, "saved_to": str(path), **unit.model_dump()}

    if task.task_type == TaskType.GENERATE_WORKSHEET:
        # v4.11.2026: previously this branch returned a stub that
        # reported "completed" without generating anything. Now we
        # surface an honest "not implemented" error so the teacher
        # sees a real failure in the queue UI instead of a silent no-op.
        return {
            "status": "failed",
            "error": (
                "Worksheet generation via queue is not implemented. "
                "Use `clawed lesson` to generate a lesson and then "
                "export its worksheet materials directly."
            ),
        }

    if task.task_type == TaskType.GENERATE_ASSESSMENT:
        return {
            "status": "failed",
            "error": (
                "Assessment generation via queue is not implemented. "
                "Use `clawed lesson` and export its exit-ticket section "
                "instead."
            ),
        }

    return {"error": f"Unknown task type: {task.task_type}"}


async def run_worker(
    queue: TaskQueue,
    *,
    poll_interval: float = 2.0,
    once: bool = False,
) -> None:
    """Background worker loop — pops tasks from queue and executes them.

    Args:
        queue: The TaskQueue instance to poll.
        poll_interval: Seconds between queue checks when idle.
        once: If True, process one task then return (useful for testing).
    """
    while True:
        task = queue.next_queued()
        if task is None:
            if once:
                return
            await asyncio.sleep(poll_interval)
            continue

        try:
            result = await _execute_task(task)
            queue.mark_done(task.id, result)
        except Exception as exc:
            queue.mark_failed(task.id, str(exc))

        if once:
            return
