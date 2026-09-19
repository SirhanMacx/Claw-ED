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
import time
import uuid
from contextvars import ContextVar
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
    INTERRUPTED = "interrupted"
    CANCEL_REQUESTED = "cancel_requested"
    CANCELLED = "cancelled"


class TaskType(str, Enum):
    LESSON_BUNDLE = "lesson_bundle"
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
        self.worker_id = uuid.uuid4().hex
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
        columns = {row[1] for row in conn.execute("PRAGMA table_info(tasks)")}
        for name, kind in (("worker_id", "TEXT"), ("heartbeat", "REAL")):
            if name not in columns:
                conn.execute(f"ALTER TABLE tasks ADD COLUMN {name} {kind}")
        conn.execute("""CREATE TABLE IF NOT EXISTS task_steps (
            task_id TEXT NOT NULL, name TEXT NOT NULL, fingerprint TEXT NOT NULL,
            result_json TEXT NOT NULL, completed_at TEXT NOT NULL,
            PRIMARY KEY(task_id, name, fingerprint))""")
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
        # One SQL statement claims the row across all worker processes.
        row = conn.execute(
            "UPDATE tasks SET status = 'running', worker_id = ?, heartbeat = ? "
            "WHERE id = (SELECT id FROM tasks WHERE status = 'queued' ORDER BY created_at LIMIT 1) "
            "AND status = 'queued' RETURNING *", (self.worker_id, time.time()),
        ).fetchone()
        conn.commit()
        return self._row_to_task(row) if row else None

    def cancel(self, task_id: str) -> bool:
        conn = self._get_conn()
        cursor = conn.execute(
            "UPDATE tasks SET status = CASE WHEN status = 'running' THEN 'cancel_requested' ELSE 'cancelled' END "
            "WHERE id = ? AND status IN ('queued', 'running', 'interrupted', 'failed')", (task_id,),
        )
        conn.commit()
        return bool(cursor.rowcount)

    def resume(self, task_id: str) -> bool:
        conn = self._get_conn()
        cursor = conn.execute(
            "UPDATE tasks SET status = 'queued', error = NULL, completed_at = NULL, worker_id = NULL "
            "WHERE id = ? AND status IN ('failed', 'interrupted', 'cancelled')", (task_id,),
        )
        conn.commit()
        return bool(cursor.rowcount)

    def recover_interrupted(self, stale_seconds: float = 300) -> int:
        conn = self._get_conn()
        cursor = conn.execute(
            "UPDATE tasks SET status = CASE WHEN status = 'cancel_requested' THEN 'cancelled' ELSE 'interrupted' END "
            "WHERE status IN ('running','cancel_requested') AND (heartbeat IS NULL OR heartbeat < ?)",
            (time.time() - max(60, stale_seconds),),
        )
        conn.commit()
        return cursor.rowcount

    def heartbeat(self, task_id: str) -> bool:
        conn = self._get_conn()
        cursor = conn.execute(
            "UPDATE tasks SET heartbeat = ? WHERE id = ? AND worker_id = ? AND status = 'running'",
            (time.time(), task_id, self.worker_id),
        )
        conn.commit()
        return bool(cursor.rowcount)

    def checkpoint(self, task_id: str, name: str, fingerprint: str, result: dict[str, Any]) -> None:
        conn = self._get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO task_steps VALUES (?, ?, ?, ?, ?)",
            (task_id, name, fingerprint, json.dumps(result, ensure_ascii=False), datetime.now(UTC).isoformat()),
        )
        conn.commit()

    def cached_step(self, task_id: str, name: str, fingerprint: str) -> dict[str, Any] | None:
        row = self._get_conn().execute(
            "SELECT result_json FROM task_steps WHERE task_id = ? AND name = ? AND fingerprint = ?",
            (task_id, name, fingerprint),
        ).fetchone()
        return dict(json.loads(row[0])) if row else None

    def steps(self, task_id: str) -> list[dict[str, Any]]:
        return [dict(row) for row in self._get_conn().execute(
            "SELECT name, fingerprint, completed_at FROM task_steps WHERE task_id = ? ORDER BY completed_at",
            (task_id,),
        )]

    def mark_stopped(self, task_id: str) -> None:
        conn = self._get_conn()
        conn.execute(
            "UPDATE tasks SET status = CASE WHEN status = 'cancel_requested' THEN 'cancelled' ELSE 'interrupted' END "
            "WHERE id = ? AND worker_id = ? AND status IN ('running','cancel_requested')",
            (task_id, self.worker_id),
        )
        conn.commit()

    def mark_done(self, task_id: str, result: dict[str, Any]) -> None:
        """Mark a task as successfully completed with its result."""
        now = datetime.now(UTC).isoformat()
        conn = self._get_conn()
        cursor = conn.execute(
            "UPDATE tasks SET status = 'done', result_json = ?, completed_at = ? "
            "WHERE id = ? AND status = 'running' AND worker_id = ?",
            (json.dumps(result), now, task_id, self.worker_id),
        )
        conn.commit()
        if not cursor.rowcount:
            # Cancellation can arrive after generation finishes but before this
            # commit. A completed coroutine must still acknowledge that request.
            self.mark_stopped(task_id)

    def mark_failed(self, task_id: str, error: str, result: dict[str, Any] | None = None) -> None:
        """Mark a task as failed with an error message."""
        now = datetime.now(UTC).isoformat()
        conn = self._get_conn()
        cursor = conn.execute(
            "UPDATE tasks SET status = 'failed', error = ?, result_json = ?, completed_at = ? "
            "WHERE id = ? AND status = 'running' AND worker_id = ?",
            (error, json.dumps(result) if result else None, now, task_id, self.worker_id),
        )
        conn.commit()
        if not cursor.rowcount:
            self.mark_stopped(task_id)

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


current_task: ContextVar[tuple[TaskQueue, str] | None] = ContextVar("clawed_current_task", default=None)


# ── Background worker ─────────────────────────────────────────────────


async def _execute_task(task: Task) -> dict[str, Any]:
    """Route a task to the appropriate generator and return the result."""
    from clawed.commands._helpers import load_persona_or_exit
    from clawed.models import AppConfig

    payload = task.payload
    config = AppConfig.load()

    if task.task_type == TaskType.LESSON_BUNDLE:
        from clawed.agent_core.context import AgentContext
        from clawed.agent_core.core import Gateway
        from clawed.agent_core.identity import get_teacher_id
        from clawed.agent_core.tools.generate_lesson_bundle import GenerateLessonBundleTool
        config = config.model_copy(update={"output_dir": str(Path(config.output_dir).expanduser() / task.id)})
        profile = Gateway._load_teacher_profile() or {}
        context = AgentContext(teacher_id=get_teacher_id(), config=config, teacher_profile=profile,
                               persona=Gateway._load_persona(profile), session_history=[], improvement_context="")
        result = await GenerateLessonBundleTool().execute(payload, context)
        return {"text": result.text, "files": [str(path) for path in result.files], **result.data}

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

    return {"error": f"Unknown task type: {task.task_type}"}  # type: ignore[unreachable]


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

        token = current_task.set((queue, task.id))
        execution = asyncio.create_task(_execute_task(task))
        try:
            while not execution.done():
                await asyncio.wait({execution}, timeout=min(poll_interval, 2.0))
                if not queue.heartbeat(task.id):
                    execution.cancel()
                    break
            try:
                result = await execution
            except asyncio.CancelledError:
                queue.mark_stopped(task.id)
                worker_task = asyncio.current_task()
                if worker_task and worker_task.cancelling():
                    raise
            else:
                if result.get("status") in ("failed", "partial", "draft") or result.get("error"):
                    queue.mark_failed(task.id, str(result.get("error") or result.get("text") or result), result)
                else:
                    queue.mark_done(task.id, result)
        except asyncio.CancelledError:
            execution.cancel()
            try:
                await execution
            except asyncio.CancelledError:
                pass
            queue.mark_stopped(task.id)
            raise
        except Exception as exc:
            queue.mark_failed(task.id, str(exc))
        finally:
            current_task.reset(token)

        if once:
            return
