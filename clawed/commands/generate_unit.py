"""Unit-planning commands: unit, year-map, pacing, full, course."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer
from rich.panel import Panel
from rich.table import Table

from clawed._json_output import run_json_command
from clawed.commands._helpers import (
    _safe_progress,
    check_api_key_or_exit,
    console,
    friendly_error,
    load_persona_or_exit,
)
from clawed.commands._helpers import output_dir as _output_dir
from clawed.commands._helpers import run_async as _run_async
from clawed.commands.generate import generate_app

# ── Unit planning ────────────────────────────────────────────────────────


def _unit_json(
    *,
    topic: str,
    grade: str,
    subject: str,
    weeks: int,
    standards: str | None,
) -> dict[str, Any]:
    """Run unit planning and return structured result for JSON output."""
    from clawed.planner import plan_unit, save_unit

    persona = load_persona_or_exit()
    std_list = [s.strip() for s in standards.split(",")] if standards else None

    unit_plan = _run_async(
        plan_unit(
            subject=subject, grade_level=grade, topic=topic,
            duration_weeks=weeks, persona=persona, standards=std_list,
        )
    )

    out_dir = _output_dir()
    json_path = save_unit(unit_plan, out_dir)

    return {
        "data": {
            "title": unit_plan.title,
            "subject": unit_plan.subject,
            "grade": unit_plan.grade_level,
            "weeks": unit_plan.duration_weeks,
            "daily_lessons": len(unit_plan.daily_lessons),
        },
        "files": [str(json_path)],
    }


@generate_app.command()
def unit(
    topic: str = typer.Argument(..., help="Unit topic (e.g., 'Photosynthesis')"),
    grade: str = typer.Option("8", "--grade", "-g", help="Grade level"),
    subject: str | None = typer.Option(
        None, "--subject", "-s", help="Subject area (reads from profile if not set)"
    ),
    weeks: int = typer.Option(3, "--weeks", "-w", help="Duration in weeks"),
    standards: str | None = typer.Option(
        None, "--standards", help="Comma-separated standards"
    ),
    fmt: str = typer.Option(
        "markdown", "--format", "-f", help="Export format: markdown, pdf, docx"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Plan a complete curriculum unit."""
    if subject is None:
        from clawed.commands._helpers import get_default_subject
        subject = get_default_subject()
    if json_output:
        run_json_command(
            "gen.unit", _unit_json,
            topic=topic, grade=grade, subject=subject, weeks=weeks, standards=standards,
        )
        return

    check_api_key_or_exit()

    from clawed.exporter import export_unit
    from clawed.planner import plan_unit, save_unit

    persona = load_persona_or_exit()
    std_list = [s.strip() for s in standards.split(",")] if standards else None

    console.print(
        Panel(
            f"[bold]{topic}[/bold] | Grade {grade} {subject} | {weeks} weeks",
            title="Planning Unit",
        )
    )

    with _safe_progress(console=console) as progress:
        task = progress.add_task("Generating unit plan...", total=None)
        try:
            unit_plan = _run_async(
                plan_unit(
                    subject=subject,
                    grade_level=grade,
                    topic=topic,
                    duration_weeks=weeks,
                    persona=persona,
                    standards=std_list,
                )
            )
        except (RuntimeError, ValueError) as e:
            console.print(f"[red]{friendly_error(e)}[/red]")
            raise typer.Exit(1) from e
        progress.update(task, description="Unit plan complete!")

    out_dir = _output_dir()
    json_path = save_unit(unit_plan, out_dir)
    export_path = export_unit(unit_plan, out_dir, fmt=fmt)

    console.print(f"\n[green]Unit plan saved:[/green] {json_path}")
    console.print(f"[green]Exported:[/green] {export_path}")

    # Summary table
    table = Table(title=unit_plan.title)
    table.add_column("#", style="dim")
    table.add_column("Lesson", style="bold")
    table.add_column("Type")
    for brief in unit_plan.daily_lessons:
        table.add_row(str(brief.lesson_number), brief.topic, brief.lesson_type)
    console.print(table)


# ── Year map & pacing guide ──────────────────────────────────────────────


@generate_app.command(name="year-map")
def year_map(
    subject: str = typer.Argument(..., help="Subject area (e.g., 'Math')"),
    grade: str = typer.Option("8", "--grade", "-g", help="Grade level"),
    standards: str | None = typer.Option(
        None, "--standards", help="Comma-separated standards"
    ),
    weeks: int = typer.Option(
        36, "--weeks", "-w", help="Total instructional weeks"
    ),
    school_year: str = typer.Option(
        "", "--school-year", help="School year label (e.g., '2025-26')"
    ),
    fmt: str = typer.Option(
        "markdown", "--format", "-f", help="Export format: markdown, pdf, docx"
    ),
) -> None:
    """Generate a full-year curriculum map with unit sequence, big ideas, and assessment calendar."""
    check_api_key_or_exit()

    from clawed.curriculum_map import CurriculumMapper, save_year_map
    from clawed.exporter import export_year_map

    persona = load_persona_or_exit()
    std_list = [s.strip() for s in standards.split(",")] if standards else None

    console.print(
        Panel(
            f"[bold]{subject}[/bold] | Grade {grade} | {weeks} instructional weeks",
            title="Planning Year Map",
        )
    )

    with _safe_progress(console=console) as progress:
        task = progress.add_task(
            "Generating full-year curriculum map...", total=None
        )
        mapper = CurriculumMapper()
        try:
            result = _run_async(
                mapper.generate_year_map(
                    subject=subject,
                    grade_level=grade,
                    standards=std_list,
                    persona=persona,
                    school_year=school_year,
                    total_weeks=weeks,
                )
            )
        except (RuntimeError, ValueError) as e:
            console.print(f"[red]{friendly_error(e)}[/red]")
            raise typer.Exit(1) from e
        progress.update(task, description="Year map complete!")

    out_dir = _output_dir()
    json_path = save_year_map(result, out_dir)
    export_path = export_year_map(result, out_dir, fmt=fmt)

    console.print(f"\n[green]Year map saved:[/green] {json_path}")
    console.print(f"[green]Exported:[/green] {export_path}")

    # Summary table
    table = Table(
        title=f"Year Map — {result.subject}, Grade {result.grade_level}"
    )
    table.add_column("#", style="dim")
    table.add_column("Unit", style="bold")
    table.add_column("Weeks", justify="right")
    table.add_column("Essential Questions")
    for u in result.units:
        eq_preview = (
            u.essential_questions[0][:60] + "..."
            if u.essential_questions
            else "—"
        )
        table.add_row(
            str(u.unit_number), u.title, str(u.duration_weeks), eq_preview
        )
    console.print(table)

    if result.big_ideas:
        console.print("\n[bold]Big Ideas:[/bold]")
        for bi in result.big_ideas:
            units_str = ", ".join(str(n) for n in bi.connected_units)
            console.print(f"  * {bi.idea} [dim](Units {units_str})[/dim]")


@generate_app.command()
def pacing(
    year_map_file: str = typer.Option(
        ..., "--year-map", "-y", help="Path to year map JSON"
    ),
    start_date: str = typer.Option(
        ..., "--start-date", "-d", help="First instructional day (YYYY-MM-DD)"
    ),
    calendar_file: str | None = typer.Option(
        None, "--calendar", "-c", help="School calendar JSON file"
    ),
    fmt: str = typer.Option(
        "markdown", "--format", "-f", help="Export format: markdown, pdf, docx"
    ),
) -> None:
    """Generate a week-by-week pacing guide from a year map."""
    check_api_key_or_exit()

    from clawed.curriculum_map import (
        CurriculumMapper,
        load_year_map,
        save_pacing_guide,
    )
    from clawed.exporter import export_pacing_guide
    from clawed.models import SchoolCalendarEvent

    persona = load_persona_or_exit()
    ym = load_year_map(Path(year_map_file))

    # Load school calendar if provided
    school_cal: list[SchoolCalendarEvent] | None = None
    if calendar_file:
        cal_path = Path(calendar_file)
        if cal_path.exists():
            import json as _json

            cal_data = _json.loads(cal_path.read_text(encoding="utf-8"))
            school_cal = [
                SchoolCalendarEvent.model_validate(e) for e in cal_data
            ]

    console.print(
        Panel(
            f"[bold]{ym.subject}[/bold] Grade {ym.grade_level}"
            f" | Starting {start_date}",
            title="Generating Pacing Guide",
        )
    )

    with _safe_progress(console=console) as progress:
        task = progress.add_task(
            "Creating week-by-week pacing guide...", total=None
        )
        mapper = CurriculumMapper()
        try:
            guide = _run_async(
                mapper.generate_pacing_guide(
                    year_map=ym,
                    start_date=start_date,
                    school_calendar=school_cal,
                    persona=persona,
                )
            )
        except (RuntimeError, ValueError) as e:
            console.print(f"[red]{friendly_error(e)}[/red]")
            raise typer.Exit(1) from e
        progress.update(task, description="Pacing guide complete!")

    out_dir = _output_dir()
    json_path = save_pacing_guide(guide, out_dir)
    export_path = export_pacing_guide(guide, out_dir, fmt=fmt)

    console.print(f"\n[green]Pacing guide saved:[/green] {json_path}")
    console.print(f"[green]Exported:[/green] {export_path}")

    # Summary table
    table = Table(
        title=f"Pacing Guide — {guide.subject}, Grade {guide.grade_level}"
    )
    table.add_column("Week", style="dim", justify="right")
    table.add_column("Dates")
    table.add_column("Unit", style="bold")
    table.add_column("Topics")
    for w in guide.weeks[:10]:  # Show first 10 weeks
        topics = "; ".join(w.topics[:2]) if w.topics else "—"
        table.add_row(
            str(w.week_number),
            f"{w.start_date} – {w.end_date}",
            f"U{w.unit_number}: {w.unit_title}",
            topics,
        )
    console.print(table)
    if len(guide.weeks) > 10:
        console.print(
            f"[dim]  ... and {len(guide.weeks) - 10} more weeks"
            " (see exported file)[/dim]"
        )


# ── Full pipeline ────────────────────────────────────────────────────────


@generate_app.command()
def full(
    topic: str = typer.Argument(..., help="Unit topic"),
    grade: str = typer.Option("8", "--grade", "-g", help="Grade level"),
    subject: str = typer.Option(
        "Science", "--subject", "-s", help="Subject area"
    ),
    weeks: int = typer.Option(3, "--weeks", "-w", help="Duration in weeks"),
    standards: str | None = typer.Option(
        None, "--standards", help="Comma-separated standards"
    ),
    homework: bool = typer.Option(
        True, "--homework/--no-homework", help="Include homework"
    ),
    fmt: str = typer.Option("markdown", "--format", "-f", help="Export format"),
    max_lessons: int | None = typer.Option(
        None, "--max-lessons", help="Limit lessons generated"
    ),
) -> None:
    """End-to-end generation: unit plan + all lesson plans + all materials."""
    check_api_key_or_exit()

    from clawed.exporter import export_lesson, export_materials, export_unit
    from clawed.lesson import generate_lesson, save_lesson
    from clawed.materials import generate_all_materials, save_materials
    from clawed.planner import plan_unit, save_unit

    persona = load_persona_or_exit()
    std_list = [s.strip() for s in standards.split(",")] if standards else None
    out_dir = _output_dir()

    console.print(
        Panel(
            f"[bold]{topic}[/bold] | Grade {grade} {subject} | {weeks} weeks\n"
            f"Full pipeline: unit plan + lessons + materials",
            title="Claw-ED Full Generation",
        )
    )

    # Step 1: Unit plan
    with _safe_progress(console=console) as progress:
        task = progress.add_task("Step 1/3: Planning unit...", total=None)
        try:
            unit_plan = _run_async(
                plan_unit(
                    subject=subject,
                    grade_level=grade,
                    topic=topic,
                    duration_weeks=weeks,
                    persona=persona,
                    standards=std_list,
                )
            )
        except (RuntimeError, ValueError) as e:
            console.print(f"[red]{friendly_error(e)}[/red]")
            raise typer.Exit(1) from e
        progress.update(task, description="Unit plan complete!")

    save_unit(unit_plan, out_dir)
    export_unit(unit_plan, out_dir, fmt=fmt)
    console.print(
        f"[green]Unit plan:[/green] {unit_plan.title}"
        f" ({len(unit_plan.daily_lessons)} lessons)"
    )

    # Step 2: Lesson plans
    lesson_briefs = unit_plan.daily_lessons
    if max_lessons:
        lesson_briefs = lesson_briefs[:max_lessons]

    lessons: list[Any] = []
    with _safe_progress(console=console) as progress:
        task = progress.add_task(
            "Step 2/3: Generating lessons...", total=len(lesson_briefs)
        )
        for brief in lesson_briefs:
            progress.update(
                task,
                description=f"Lesson {brief.lesson_number}: {brief.topic}",
            )
            try:
                daily = _run_async(
                    generate_lesson(
                        lesson_number=brief.lesson_number,
                        unit=unit_plan,
                        persona=persona,
                        include_homework=homework,
                    )
                )
            except (RuntimeError, ValueError) as e:
                console.print(f"[red]{friendly_error(e)}[/red]")
                raise typer.Exit(1) from e
            save_lesson(daily, out_dir)
            export_lesson(daily, out_dir, fmt=fmt)
            lessons.append(daily)
            progress.advance(task)

    # Step 3: Materials for each lesson
    with _safe_progress(console=console) as progress:
        task = progress.add_task(
            "Step 3/3: Generating materials...", total=len(lessons)
        )
        for daily in lessons:
            progress.update(
                task,
                description=(
                    f"Materials for lesson {daily.lesson_number}"
                ),
            )
            try:
                mats = _run_async(generate_all_materials(daily, persona))
            except (RuntimeError, ValueError) as e:
                console.print(f"[red]{friendly_error(e)}[/red]")
                raise typer.Exit(1) from e
            save_materials(mats, out_dir)
            export_materials(mats, out_dir, fmt=fmt)
            progress.advance(task)

    # Final summary
    console.print(
        Panel(
            f"[green bold]Generation complete![/green bold]\n\n"
            f"[bold]Unit:[/bold] {unit_plan.title}\n"
            f"[bold]Lessons:[/bold] {len(lessons)}\n"
            f"[bold]Materials sets:[/bold] {len(lessons)}\n"
            f"[bold]Output:[/bold] {out_dir}",
            title="Done!",
        )
    )


# ── Course command ───────────────────────────────────────────────────


@generate_app.command()
def course(
    subject: str = typer.Option(
        ..., "--subject", "-s", help="Subject area"
    ),
    grade: str = typer.Option(
        ..., "--grade", "-g", help="Grade level"
    ),
    topics_file: str = typer.Option(
        ...,
        "--topics-file",
        "-t",
        help="Path to a text file with one topic per line",
    ),
    weeks_per_topic: int = typer.Option(
        2, "--weeks", "-w", help="Weeks per topic"
    ),
    fmt: str = typer.Option("markdown", "--format", "-f", help="Export format"),
) -> None:
    """Generate a full course — one unit per topic from a pacing guide."""
    check_api_key_or_exit()

    from clawed.exporter import export_unit
    from clawed.planner import plan_unit, save_unit

    persona = load_persona_or_exit()

    path = Path(topics_file).expanduser().resolve()
    if not path.exists():
        console.print(f"[red]File not found:[/red] {path}")
        raise typer.Exit(1)

    topics = [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not topics:
        console.print("[red]No topics found in file.[/red]")
        raise typer.Exit(1)

    console.print(
        Panel(
            f"[bold]{subject} — Grade {grade}[/bold]\n"
            f"{len(topics)} topics, {weeks_per_topic} weeks each",
            title="Course Generation",
        )
    )

    out_dir = _output_dir() / "course"
    units: list[Any] = []

    with _safe_progress(console=console) as progress:
        task = progress.add_task(
            "Generating course...", total=len(topics)
        )
        for i, topic in enumerate(topics, 1):
            progress.update(
                task, description=f"Unit {i}/{len(topics)}: {topic}"
            )
            try:
                unit_plan = _run_async(
                    plan_unit(
                        subject=subject,
                        grade_level=grade,
                        topic=topic,
                        duration_weeks=weeks_per_topic,
                        persona=persona,
                    )
                )
                save_unit(unit_plan, out_dir)
                export_unit(unit_plan, out_dir, fmt=fmt)
                units.append(unit_plan)
            except Exception as e:
                console.print(f"[red]Failed: {topic} — {e}[/red]")
            progress.advance(task)

    # Summary table
    table = Table(title="Course Map")
    table.add_column("#", style="dim")
    table.add_column("Unit", style="bold")
    table.add_column("Lessons", justify="center")
    for i, u in enumerate(units, 1):
        table.add_row(str(i), u.title, str(len(u.daily_lessons)))
    console.print(table)
    console.print(f"\n[green]Course saved:[/green] {out_dir}")
