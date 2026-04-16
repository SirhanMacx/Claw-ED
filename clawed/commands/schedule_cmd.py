"""CLI commands for the Claw-ED scheduler."""

from __future__ import annotations

import asyncio

import typer
from rich.panel import Panel
from rich.table import Table

from clawed.commands._helpers import console, run_async

schedule_app = typer.Typer(help="Scheduled autonomous tasks — morning prep, feedback digest, etc.")


@schedule_app.command("list")
def schedule_list() -> None:
    """Show all scheduled tasks with status and schedule."""
    from clawed.scheduler import load_schedule_config

    config = load_schedule_config()

    table = Table(title="Claw-ED Scheduled Tasks")
    table.add_column("Task", style="bold")
    table.add_column("Status", justify="center")
    table.add_column("Schedule")
    table.add_column("Description")

    for name, task_cfg in config.items():
        enabled = task_cfg.get("enabled", False)
        status = "[green]enabled[/green]" if enabled else "[dim]disabled[/dim]"
        cron = task_cfg.get("cron", {})
        cron_str = _format_cron(cron)
        desc = task_cfg.get("description", "")
        # Truncate long descriptions
        if len(desc) > 60:
            desc = desc[:57] + "..."
        table.add_row(name, status, cron_str, desc)

    console.print(table)


@schedule_app.command("enable")
def schedule_enable(
    task: str = typer.Argument(..., help="Task name to enable"),
) -> None:
    """Enable a scheduled task."""
    from clawed.scheduler import enable_task

    if enable_task(task):
        console.print(f"[green]Task '{task}' enabled.[/green]")
    else:
        console.print(f"[red]Unknown task: '{task}'.[/red]")
        _show_available_tasks()
        raise typer.Exit(1)


@schedule_app.command("disable")
def schedule_disable(
    task: str = typer.Argument(..., help="Task name to disable"),
) -> None:
    """Disable a scheduled task."""
    from clawed.scheduler import disable_task

    if disable_task(task):
        console.print(f"[yellow]Task '{task}' disabled.[/yellow]")
    else:
        console.print(f"[red]Unknown task: '{task}'.[/red]")
        _show_available_tasks()
        raise typer.Exit(1)


@schedule_app.command("run")
def schedule_run(
    task: str = typer.Argument(..., help="Task name to run immediately"),
) -> None:
    """Run a scheduled task immediately (manual trigger)."""
    from clawed.scheduler import run_task

    console.print(f"[dim]Running '{task}'...[/dim]")
    try:
        result = run_async(run_task(task))
        console.print(
            Panel(
                result,
                title=f"[bold]{task}[/bold] Result",
                border_style="green",
            )
        )
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from e
    except Exception as e:
        console.print(f"[red]Task failed: {e}[/red]")
        raise typer.Exit(1) from e


@schedule_app.command("set")
def schedule_set(
    task: str = typer.Argument(..., help="Task name"),
    cron_expr: str = typer.Argument(..., help="Cron expression (e.g. '6:00', 'sun 19:00', 'hour=6 minute=0')"),
) -> None:
    """Change a task's schedule."""
    from clawed.scheduler import set_task_schedule

    if set_task_schedule(task, cron_expr):
        console.print(f"[green]Schedule for '{task}' updated to: {cron_expr}[/green]")
    else:
        console.print(f"[red]Unknown task: '{task}'.[/red]")
        _show_available_tasks()
        raise typer.Exit(1)


@schedule_app.command("start")
def schedule_start() -> None:
    """Start the scheduler daemon (foreground). Press Ctrl+C to stop."""
    from clawed.scheduler import EduScheduler

    scheduler = EduScheduler()
    jobs = [j for j in scheduler.get_jobs_info() if j["enabled"]]

    if not jobs:
        console.print("[yellow]No tasks enabled. Enable tasks with 'clawed schedule enable <task>'.[/yellow]")
        raise typer.Exit(0)

    console.print(
        Panel(
            f"Starting scheduler with [bold]{len(jobs)}[/bold] enabled task(s).\n"
            f"Press [bold]Ctrl+C[/bold] to stop.\n\n"
            + "\n".join(f"  - {j['name']} ({_format_cron(j['cron'])})" for j in jobs),
            title="[bold]Claw-ED Scheduler[/bold]",
            border_style="blue",
        )
    )

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        scheduler.start()
        loop.run_forever()
    except KeyboardInterrupt:
        scheduler.stop()
        console.print("\n[dim]Scheduler stopped.[/dim]")
    finally:
        loop.close()


# ── Helpers ────────────────────────────────────────────────────────────


def _format_cron(cron: dict[str, str]) -> str:
    """Format a cron dict into a human-readable string."""
    parts = []
    if "day_of_week" in cron:
        parts.append(cron["day_of_week"].capitalize())
    hour = cron.get("hour", "*")
    minute = cron.get("minute", "0")
    parts.append(f"{hour}:{minute.zfill(2) if minute != '*' else '00'}")
    return " ".join(parts)


def _show_available_tasks() -> None:
    """Print available task names."""
    from clawed.scheduler import load_schedule_config

    config = load_schedule_config()
    names = ", ".join(config.keys())
    console.print(f"[dim]Available tasks: {names}[/dim]")
