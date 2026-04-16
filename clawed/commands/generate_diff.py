"""Differentiation / IEP commands — split from generate.py for maintainability."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.panel import Panel
from rich.table import Table

from clawed.commands._helpers import (
    _safe_progress,
    check_api_key_or_exit,
    console,
    friendly_error,
)
from clawed.commands._helpers import output_dir as _output_dir
from clawed.commands._helpers import run_async as _run_async
from clawed.commands.generate import generate_app
from clawed.io import safe_filename as _safe_filename

# ── Differentiation / IEP ────────────────────────────────────────────────


@generate_app.command()
def differentiate(
    lesson_file: str = typer.Option(
        ..., "--lesson-file", "-l", help="Path to lesson plan JSON"
    ),
    iep: str | None = typer.Option(
        None, "--iep", help="Path to IEP student profiles JSON"
    ),
    accommodations_504: str | None = typer.Option(
        None, "--504", help="Comma-separated 504 accommodations"
    ),
    tiered_topic: str | None = typer.Option(
        None, "--tiered-topic", help="Topic for tiered assignments"
    ),
    tiered_grade: str = typer.Option(
        "8", "--tiered-grade", help="Grade level for tiered assignments"
    ),
    tiers: int = typer.Option(
        3, "--tiers", help="Number of difficulty tiers"
    ),
) -> None:
    """Generate IEP modifications, 504 accommodations, and tiered assignments."""
    check_api_key_or_exit()

    from clawed.differentiation import (
        generate_504_accommodations,
        generate_iep_lesson_modifications,
        generate_tiered_assignments,
        load_iep_profiles,
        save_modified_lessons,
        save_tiered_assignments,
    )
    from clawed.lesson import load_lesson

    daily = load_lesson(Path(lesson_file))
    out_dir = _output_dir()
    ran_any = False

    # IEP modifications
    if iep:
        ran_any = True
        profiles = load_iep_profiles(Path(iep))
        console.print(
            Panel(
                f"Generating modified lessons for"
                f" [bold]{len(profiles)}[/bold] IEP students",
                title="IEP Modifications",
            )
        )

        with _safe_progress(console=console) as progress:
            task = progress.add_task(
                "Modifying lessons for IEP students...", total=None
            )
            try:
                modifications = _run_async(
                    generate_iep_lesson_modifications(daily, profiles)
                )
            except (RuntimeError, ValueError) as e:
                console.print(f"[red]{friendly_error(e)}[/red]")
                raise typer.Exit(1) from e
            progress.update(
                task,
                description=(
                    f"Generated {len(modifications)} modified lessons!"
                ),
            )

        paths = save_modified_lessons(modifications, out_dir)
        table = Table(title="IEP Modified Lessons")
        table.add_column("Student", style="bold")
        table.add_column("Modified Title")
        table.add_column("File", style="dim")
        for name, mod_lesson in modifications.items():
            path = next(
                (
                    p
                    for p in paths
                    if _safe_filename(name) in str(p)
                ),
                paths[0],
            )
            table.add_row(name, mod_lesson.title, str(path))
        console.print(table)

    # 504 accommodations
    if accommodations_504:
        ran_any = True
        acc_list = [a.strip() for a in accommodations_504.split(",")]
        console.print(
            Panel(
                f"Generating 504 accommodations: {', '.join(acc_list)}",
                title="504 Accommodations",
            )
        )

        with _safe_progress(console=console) as progress:
            task = progress.add_task(
                "Generating 504 accommodations...", total=None
            )
            try:
                notes = _run_async(
                    generate_504_accommodations(daily, acc_list)
                )
            except (RuntimeError, ValueError) as e:
                console.print(f"[red]{friendly_error(e)}[/red]")
                raise typer.Exit(1) from e
            progress.update(
                task, description="504 accommodations complete!"
            )

        console.print(
            Panel(
                "\n".join(f"  - {s}" for s in notes.struggling) or "  (none)",
                title="504 Accommodation Notes",
            )
        )

    # Tiered assignments
    if tiered_topic:
        ran_any = True
        console.print(
            Panel(
                f"Generating [bold]{tiers}-tier[/bold]"
                f" assignments for: {tiered_topic}",
                title="Tiered Assignments",
            )
        )

        with _safe_progress(console=console) as progress:
            task = progress.add_task(
                "Generating tiered assignments...", total=None
            )
            try:
                items = _run_async(
                    generate_tiered_assignments(
                        tiered_topic, tiered_grade, tiers
                    )
                )
            except (RuntimeError, ValueError) as e:
                console.print(f"[red]{friendly_error(e)}[/red]")
                raise typer.Exit(1) from e
            progress.update(
                task,
                description=f"Generated {len(items)} tiered items!",
            )

        path = save_tiered_assignments(items, out_dir, tiered_topic)
        table = Table(title="Tiered Assignment Summary")
        table.add_column("Tier", style="bold")
        table.add_column("Items", justify="right")
        for t in range(tiers):
            low = t * 100 + (1 if t == 0 else 0)
            high = (t + 1) * 100
            count = sum(1 for i in items if low <= i.item_number < high)
            labels = ["Approaching", "On-Level", "Advanced", f"Tier {t + 1}"]
            table.add_row(labels[min(t, len(labels) - 1)], str(count))
        console.print(table)
        console.print(f"[green]Saved:[/green] {path}")

    if not ran_any:
        console.print(
            "[yellow]Specify at least one option:[/yellow]"
            " --iep, --504, or --tiered-topic\n"
            "Example: clawed differentiate"
            " --lesson-file lesson.json --iep students.json"
        )
        raise typer.Exit(1)
