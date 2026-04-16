"""CLI commands for the background task queue."""

from __future__ import annotations

from typing import Any

import typer

from clawed.commands._helpers import console, run_async
from clawed.task_queue import TaskQueue, TaskStatus, TaskType, run_worker

queue_app = typer.Typer(help="Background task queue for long-running generation jobs.")


@queue_app.command()
def submit(
    task_type: str = typer.Argument(..., help="Task type: lesson, unit, worksheet, assessment"),
    topic: str = typer.Option("", "--topic", "-t", help="Topic for generation"),
    grade: str = typer.Option("", "--grade", "-g", help="Grade level"),
    subject: str = typer.Option("", "--subject", "-s", help="Subject area"),
    unit_path: str | None = typer.Option(None, "--unit-path", help="Path to unit plan JSON (for lesson tasks)"),
    lesson_number: int = typer.Option(1, "--lesson-number", "-n", help="Lesson number (for lesson tasks)"),
) -> None:
    """Submit a generation task to the background queue."""
    type_map = {
        "lesson": TaskType.GENERATE_LESSON,
        "unit": TaskType.GENERATE_UNIT,
        "worksheet": TaskType.GENERATE_WORKSHEET,
        "assessment": TaskType.GENERATE_ASSESSMENT,
    }
    resolved = type_map.get(task_type.lower())
    if resolved is None:
        console.print(f"[red]Unknown task type:[/red] {task_type}")
        console.print(f"  Valid types: {', '.join(type_map)}")
        raise typer.Exit(1)

    payload: dict[str, Any] = {"topic": topic, "grade": grade, "subject": subject}
    if unit_path:
        payload["unit_path"] = unit_path
    if resolved == TaskType.GENERATE_LESSON:
        payload["lesson_number"] = lesson_number

    q = TaskQueue()
    task_id = q.submit(resolved, payload)
    q.close()
    console.print(f"[green]Task submitted![/green]  id={task_id}  type={resolved.value}")
    console.print("Run [bold]clawed queue worker[/bold] to process the queue.")


@queue_app.command()
def status(
    task_id: str = typer.Argument(..., help="Task ID to check"),
) -> None:
    """Check the status of a queued task."""
    q = TaskQueue()
    task = q.get_status(task_id)
    q.close()
    if task is None:
        console.print(f"[red]Task not found:[/red] {task_id}")
        raise typer.Exit(1)

    color = {
        TaskStatus.QUEUED: "yellow",
        TaskStatus.RUNNING: "blue",
        TaskStatus.DONE: "green",
        TaskStatus.FAILED: "red",
    }.get(task.status, "white")

    console.print(f"Task [bold]{task.id}[/bold]")
    console.print(f"  Type:    {task.task_type.value}")
    console.print(f"  Status:  [{color}]{task.status.value}[/{color}]")
    console.print(f"  Created: {task.created_at}")
    if task.completed_at:
        console.print(f"  Done:    {task.completed_at}")
    if task.error:
        console.print(f"  Error:   [red]{task.error}[/red]")
    if task.result:
        console.print(f"  Result:  {task.result}")


@queue_app.command(name="list")
def list_tasks(
    limit: int = typer.Option(20, "--limit", "-n", help="Max tasks to show"),
) -> None:
    """List recent tasks in the queue."""
    q = TaskQueue()
    tasks = q.list_tasks(limit=limit)
    q.close()

    if not tasks:
        console.print("[dim]No tasks in queue.[/dim]")
        return

    for t in tasks:
        color = {
            TaskStatus.QUEUED: "yellow",
            TaskStatus.RUNNING: "blue",
            TaskStatus.DONE: "green",
            TaskStatus.FAILED: "red",
        }.get(t.status, "white")
        console.print(f"  {t.id}  [{color}]{t.status.value:7s}[/{color}]  {t.task_type.value}  {t.created_at}")


@queue_app.command()
def worker(
    poll_interval: float = typer.Option(2.0, "--interval", "-i", help="Seconds between queue checks"),
) -> None:
    """Start the background queue worker (runs until interrupted)."""
    console.print("[bold]Starting task queue worker...[/bold]  (Ctrl+C to stop)")
    q = TaskQueue()
    try:
        run_async(run_worker(q, poll_interval=poll_interval))
    except KeyboardInterrupt:
        console.print("\n[yellow]Worker stopped.[/yellow]")
    finally:
        q.close()
