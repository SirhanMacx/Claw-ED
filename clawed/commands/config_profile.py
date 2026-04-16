"""Teacher profile, standards, templates, skills, school, class, and waitlist commands."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer
from rich.panel import Panel
from rich.table import Table

from clawed._json_output import run_json_command
from clawed.commands._helpers import console, load_persona_or_exit
from clawed.commands.config import (
    class_app,
    persona_app,
    school_app,
    skills_app,
    standards_app,
    templates_app,
)

# ── Persona commands ─────────────────────────────────────────────────────


@persona_app.command("show")
def persona_show(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Display the current teacher persona."""
    if json_output:
        def _persona_show_json() -> dict[str, Any]:
            from clawed.commands._helpers import output_dir
            from clawed.persona import load_persona
            pp = output_dir() / "persona.json"
            if not pp.exists():
                return {
                    "data": {"persona": None}, "files": [],
                    "warnings": ["No persona found. Run clawed ingest first."],
                }
            persona = load_persona(pp)
            return {
                "data": {"persona": persona.model_dump() if hasattr(persona, "model_dump") else persona.dict()},
                "files": [str(pp)],
            }
        run_json_command("config.persona.show", _persona_show_json)
        return

    persona = load_persona_or_exit()
    console.print(
        Panel(persona.to_prompt_context(), title="Teacher Persona")
    )


# ── Standards commands ───────────────────────────────────────────────────


@standards_app.command("list")
def standards_list(
    grade: str = typer.Option(
        ..., "--grade", "-g", help="Grade level (e.g., K, 5, 8, 9-12)"
    ),
    subject: str = typer.Option(
        ..., "--subject", "-s", help="Subject (math, ela, science, history)"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """List education standards for a grade and subject."""
    if json_output:
        def _standards_json() -> dict[str, Any]:
            from clawed.standards import get_standards as _get_stds
            results = _get_stds(subject, grade)
            return {
                "data": {
                    "standards": [
                        {"code": code, "description": description, "band": band}
                        for code, description, band in results
                    ] if results else []
                },
                "files": [],
            }
        run_json_command("config.standards.list", _standards_json)
        return

    from clawed.standards import get_standards, resolve_subject

    canonical = resolve_subject(subject)
    if canonical is None:
        # Fallback: try SkillLibrary alias resolution
        try:
            from clawed.skills.library import SkillLibrary
            lib = SkillLibrary()
            skill = lib.get(subject)
            if skill:
                canonical = resolve_subject(skill.subject)
        except ImportError:
            pass
    if canonical is None:
        console.print(
            f"[red]Unknown subject: {subject}[/red]. "
            "Supported: math, ela/english, science, history/social studies"
        )
        raise typer.Exit(1)

    results = get_standards(subject, grade)
    if not results:
        console.print(
            f"[yellow]No standards found for grade {grade} {subject}.[/yellow]"
        )
        raise typer.Exit(0)

    framework = {
        "math": "CCSS Mathematics",
        "ela": "CCSS ELA/Literacy",
        "science": "NGSS",
        "history": "C3 Framework",
    }[canonical]

    table = Table(title=f"{framework} — Grade {grade}")
    table.add_column("Standard Code", style="bold cyan", no_wrap=True)
    table.add_column("Description")
    table.add_column("Grade Band", style="dim", justify="center")

    for code, desc, band in results:
        table.add_row(code, desc, band)

    console.print(table)
    console.print(f"\n[dim]{len(results)} standard(s) found.[/dim]")


# ── Templates commands ───────────────────────────────────────────────


@templates_app.command("list")
def templates_list() -> None:
    """List all available lesson structure templates."""
    from clawed.templates_lib import list_templates

    all_templates = list_templates()

    table = Table(title="Lesson Structure Templates")
    table.add_column("Name", style="bold")
    table.add_column("Slug", style="cyan")
    table.add_column("Description")
    table.add_column("Best For", style="dim")
    for t in all_templates:
        desc = (
            t.description[:80] + "..."
            if len(t.description) > 80
            else t.description
        )
        best_for = t.best_for[:60] if t.best_for else ""
        table.add_row(t.name, t.slug, desc, best_for)
    console.print(table)


# ── Skills commands ─────────────────────────────────────────────────


@skills_app.command("list")
def skills_list() -> None:
    """List all available subject pedagogy skills."""
    from clawed.skills import SkillLibrary

    lib = SkillLibrary()
    all_skills = lib.list_skills()

    table = Table(title="Subject Pedagogy Skills")
    table.add_column("Subject", style="bold")
    table.add_column("Display Name", style="cyan")
    table.add_column("Description")
    table.add_column("Aliases", style="dim")
    table.add_column("Source", style="dim")
    for s in all_skills:
        aliases = ", ".join(s.aliases[:4])
        if len(s.aliases) > 4:
            aliases += f" (+{len(s.aliases) - 4})"
        desc = (
            s.description[:80] + "..."
            if len(s.description) > 80
            else s.description
        )
        source = "[yellow]custom[/yellow]" if lib.is_custom(s.subject) else "built-in"
        table.add_row(s.subject, s.display_name, desc, aliases, source)
    console.print(table)


@skills_app.command("show")
def skills_show(
    subject: str = typer.Argument(
        help="Subject name or alias (e.g., 'math', 'biology', 'ela')."
    ),
) -> None:
    """Show detailed pedagogy skill for a subject."""
    from clawed.skills import SkillLibrary

    lib = SkillLibrary()
    skill = lib.get(subject)
    if skill is None:
        console.print(f"[red]No skill found for '{subject}'.[/red]")
        console.print(f"Available: {', '.join(lib.subjects())}")
        raise typer.Exit(1)

    console.print(
        Panel(
            skill.to_system_context(),
            title=f"[bold]{skill.display_name}[/bold] Pedagogy Skill",
            border_style="cyan",
        )
    )

    if skill.example_strategies:
        table = Table(title="Example Strategies")
        table.add_column("Strategy", style="bold")
        table.add_column("Description")
        for name, desc in skill.example_strategies.items():
            table.add_row(name, desc)
        console.print(table)


@skills_app.command("create")
def skills_create(
    subject: str = typer.Argument(
        help="Subject name for the new skill (e.g., 'ap_psychology')."
    ),
) -> None:
    """Generate a template YAML skill file in ~/.eduagent/skills/.

    Edit the generated file to customize the pedagogy for your subject,
    then it will be automatically loaded next time Claw-ED starts.
    """
    from clawed.skills.library import generate_skill_template

    filepath = generate_skill_template(subject)
    console.print(
        Panel(
            f"[bold green]Template created![/bold green]\n\n"
            f"  File: [cyan]{filepath}[/cyan]\n\n"
            f"Edit this file to customize the pedagogy for {subject}.\n"
            f"It will be loaded automatically next time you run Claw-ED.\n\n"
            f"Run [bold]clawed skills list[/bold] to verify it loaded.",
            title="[bold]New Custom Skill[/bold]",
            border_style="green",
        )
    )


# ── School commands ─────────────────────────────────────────────────


@school_app.command("setup")
def school_setup(
    name: str = typer.Option(..., "--name", help="School name"),
    state: str = typer.Option(
        "", "--state", help="State abbreviation (e.g., NY, CA)"
    ),
    district: str = typer.Option("", "--district", help="School district"),
    grade_levels: str = typer.Option(
        "",
        "--grades",
        help="Comma-separated grade levels (e.g., '6,7,8')",
    ),
) -> None:
    """Create a new school deployment for multi-teacher sharing."""
    from clawed.database import Database
    from clawed.school import setup_school

    db = Database()
    grades = (
        [g.strip() for g in grade_levels.split(",") if g.strip()]
        if grade_levels
        else []
    )
    school_id = setup_school(
        db, name=name, state=state, district=district, grade_levels=grades
    )
    db.close()

    console.print(
        Panel(
            f"[bold green]School created![/bold green]\n\n"
            f"  Name:      {name}\n"
            f"  State:     {state or '—'}\n"
            f"  District:  {district or '—'}\n"
            f"  Grades:    {', '.join(grades) or '—'}\n"
            f"  School ID: [cyan]{school_id}[/cyan]\n\n"
            f"Share this ID with teachers:"
            f" [bold]clawed school join"
            f" --school-id {school_id}[/bold]",
            title="[bold]School Setup[/bold]",
            border_style="green",
        )
    )


@school_app.command("join")
def school_join(
    school_id: str = typer.Option(
        ..., "--school-id", help="School ID to join"
    ),
    teacher_id: str = typer.Option(
        "local-teacher", "--teacher-id", help="Teacher ID"
    ),
    department: str = typer.Option(
        "",
        "--department",
        help="Department (e.g., 'Science', 'Math')",
    ),
    role: str = typer.Option(
        "teacher", "--role", help="Role: teacher or admin"
    ),
) -> None:
    """Join a school as a teacher or admin."""
    from clawed.database import Database
    from clawed.school import add_teacher

    db = Database()
    school = db.get_school(school_id)
    if not school:
        console.print(f"[red]School '{school_id}' not found.[/red]")
        db.close()
        raise typer.Exit(1)

    add_teacher(
        db, school_id, teacher_id, role=role, department=department
    )
    db.close()

    console.print(
        f"[green]Joined [bold]{school['name']}[/bold] as {role}.[/green]"
    )
    if department:
        console.print(f"  Department: {department}")


@school_app.command("roster")
def school_roster(
    school_id: str = typer.Option(
        ..., "--school-id", help="School ID"
    ),
) -> None:
    """Show all teachers in a school."""
    from clawed.database import Database
    from clawed.school import list_teachers

    db = Database()
    school = db.get_school(school_id)
    if not school:
        console.print(f"[red]School '{school_id}' not found.[/red]")
        db.close()
        raise typer.Exit(1)

    teachers = list_teachers(db, school_id)
    db.close()

    table = Table(title=f"Roster — {school['name']}")
    table.add_column("Teacher ID", style="cyan")
    table.add_column("Name", style="bold")
    table.add_column("Role")
    table.add_column("Department")
    for t in teachers:
        table.add_row(
            t["teacher_id"],
            t.get("teacher_name") or "—",
            t["role"],
            t.get("department") or "—",
        )
    console.print(table)


@school_app.command("share")
def school_share(
    school_id: str = typer.Option(
        ..., "--school-id", help="School ID"
    ),
    teacher_id: str = typer.Option(
        "local-teacher", "--teacher-id", help="Your teacher ID"
    ),
    unit_id: str = typer.Option(
        None, "--unit-id", help="Unit ID to share"
    ),
    lesson_id: str = typer.Option(
        None, "--lesson-id", help="Lesson ID to share"
    ),
    department: str = typer.Option(
        "",
        "--department",
        help="Share with a specific department",
    ),
) -> None:
    """Share a unit or lesson with your school's curriculum library."""
    from clawed.database import Database
    from clawed.school import share_lesson, share_unit

    if not unit_id and not lesson_id:
        console.print(
            "[red]Provide --unit-id or --lesson-id to share.[/red]"
        )
        raise typer.Exit(1)

    db = Database()
    if unit_id:
        sid = share_unit(
            db, school_id, teacher_id, unit_id, department=department
        )
        label = "Unit"
    else:
        sid = share_lesson(
            db,
            school_id,
            teacher_id,
            lesson_id,
            department=department,
        )
        label = "Lesson"
    db.close()

    if sid:
        dept_msg = (
            f" with department '{department}'"
            if department
            else " with the whole school"
        )
        console.print(
            f"[green]{label} shared{dept_msg}.[/green]"
            f"  Shared ID: [cyan]{sid}[/cyan]"
        )
    else:
        console.print(f"[red]{label} not found.[/red]")
        raise typer.Exit(1)


@school_app.command("library")
def school_library(
    school_id: str = typer.Option(
        ..., "--school-id", help="School ID"
    ),
    department: str = typer.Option(
        "", "--department", help="Filter by department"
    ),
) -> None:
    """Browse your school's shared curriculum library."""
    from clawed.database import Database
    from clawed.school import get_shared_library

    db = Database()
    school = db.get_school(school_id)
    if not school:
        console.print(f"[red]School '{school_id}' not found.[/red]")
        db.close()
        raise typer.Exit(1)

    items = get_shared_library(db, school_id, department=department)
    db.close()

    title = f"Shared Library — {school['name']}"
    if department:
        title += f" ({department})"
    table = Table(title=title)
    table.add_column("Type", style="bold")
    table.add_column("Title")
    table.add_column("Subject")
    table.add_column("Grade")
    table.add_column("Shared By")
    table.add_column("Rating", justify="right")
    for item in items:
        rating_str = (
            str(item["rating"]) if item.get("rating") else "—"
        )
        table.add_row(
            item["content_type"],
            item["title"],
            item.get("subject") or "—",
            item.get("grade_level") or "—",
            item.get("teacher_name") or "—",
            rating_str,
        )
    console.print(table)
    if not items:
        console.print(
            "[dim]No shared content yet."
            " Use 'clawed school share' to contribute![/dim]"
        )


# ── Class commands ──────────────────────────────────────────────────────


@class_app.command("create")
def class_create(
    name: str = typer.Option(..., "--name", help="Class name (e.g. 'Period 3 Global Studies')"),
    topic: str = typer.Option("", "--topic", help="Current topic (e.g. 'Unit 4: WWI')"),
    lessons: str = typer.Option("", "--lessons", help="Comma-separated lesson IDs to restrict access"),
    units: str = typer.Option("", "--units", help="Comma-separated unit IDs to restrict access"),
    expires: str = typer.Option("", "--expires", help="Expiration date (YYYY-MM-DD)"),
    teacher_id: str = typer.Option("local-teacher", "--teacher", "-t", help="Teacher ID"),
) -> None:
    """Create a class code for students to join."""
    from clawed.student_bot import StudentBot

    allowed_ids = []
    if lessons:
        allowed_ids.extend([lid.strip() for lid in lessons.split(",") if lid.strip()])
    if units:
        allowed_ids.extend([uid.strip() for uid in units.split(",") if uid.strip()])

    bot = StudentBot()
    code = bot.create_class(
        teacher_id=teacher_id,
        name=name,
        topic=topic,
        allowed_lesson_ids=allowed_ids or None,
        expires_at=expires or None,
    )

    console.print(
        Panel(
            f"[bold green]Class created![/bold green]\n\n"
            f"  Code:    [bold cyan]{code}[/bold cyan]\n"
            f"  Name:    {name}\n"
            f"  Topic:   {topic or '—'}\n"
            f"  Expires: {expires or 'Never'}\n\n"
            f"Share this code with students.\n"
            f"They join with: [bold]/join {code}[/bold] in Telegram\n"
            f"Or: [bold]clawed student-chat --class-code {code}[/bold]",
            title="[bold]New Class Code[/bold]",
            border_style="green",
        )
    )


@class_app.command("revoke")
def class_revoke(
    code: str = typer.Option(..., "--code", help="Class code"),
    student: str = typer.Option(..., "--student", help="Student ID to revoke"),
) -> None:
    """Revoke a student's access to a class."""
    from clawed.student_bot import StudentBot

    bot = StudentBot()
    removed = bot.revoke_student(code, student)
    if removed:
        console.print(f"[green]Student '{student}' removed from {code}.[/green]")
    else:
        console.print(f"[yellow]Student '{student}' not found in {code}.[/yellow]")


@class_app.command("stats")
def class_stats(
    code: str = typer.Option(..., "--code", help="Class code"),
) -> None:
    """Show student activity stats for a class code."""
    from clawed.student_bot import StudentBot

    bot = StudentBot()
    info = bot.get_class(code)
    if not info:
        console.print(f"[red]Class code '{code}' not found.[/red]")
        raise typer.Exit(1)

    stats = bot.get_class_stats(code)

    table = Table(title=f"Class Stats — {info.name or code}")
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")
    table.add_row("Registered Students", str(stats["registered_students"]))
    table.add_row("Active Students", str(stats["active_students"]))
    table.add_row("Total Questions", str(stats["total_questions"]))
    table.add_row("Topic", info.topic or "—")
    table.add_row("Hint Mode", "ON" if info.hint_mode else "OFF")
    table.add_row("Expires", info.expires_at or "Never")
    console.print(table)


@class_app.command("report")
def class_report(
    code: str = typer.Option(..., "--code", help="Class code"),
    week: str = typer.Option("", "--week", help="ISO week (e.g. 2026-W12). Default: current week"),
) -> None:
    """Pull a weekly progress report for a class."""
    from clawed.commands._helpers import run_async as _run_async
    from clawed.student_bot import StudentBot

    bot = StudentBot()
    info = bot.get_class(code)
    if not info:
        console.print(f"[red]Class code '{code}' not found.[/red]")
        raise typer.Exit(1)

    report = _run_async(bot.get_weekly_report(code, week))

    console.print(
        Panel(
            f"[bold]{info.name or code}[/bold] — Week {report['week']}\n\n"
            f"Students: {report['student_count']}  |  "
            f"Questions: {report['total_questions']}",
            title="[bold]Weekly Report[/bold]",
            border_style="blue",
        )
    )

    if report["student_activity"]:
        t = Table(title="Questions per Student (anonymized)")
        t.add_column("Student #", style="dim")
        t.add_column("Questions", justify="right")
        for s in report["student_activity"][:20]:
            t.add_row(f"Student {s['student_number']}", str(s["question_count"]))
        console.print(t)

    if report["common_topics"]:
        t2 = Table(title="Most Common Topics")
        t2.add_column("Topic", style="bold")
        t2.add_column("Mentions", justify="right")
        for topic in report["common_topics"]:
            t2.add_row(topic["topic"], str(topic["count"]))
        console.print(t2)

    if not report["total_questions"]:
        console.print("[dim]No student activity yet for this period.[/dim]")


@class_app.command("qr")
def class_qr(
    code: str = typer.Option(..., "--code", help="Class code"),
    output: str = typer.Option("qr.png", "--output", "-o", help="Output file path"),
) -> None:
    """Generate a QR code image for a class code."""
    from clawed.student_bot import StudentBot

    bot = StudentBot()
    info = bot.get_class(code)
    if not info:
        console.print(f"[red]Class code '{code}' not found.[/red]")
        raise typer.Exit(1)

    # Generate QR code as a simple text-based representation
    # (full QR image requires qrcode library which is optional)
    try:
        import qrcode

        qr = qrcode.make(f"https://t.me/clawed_bot?start={code}")
        with open(output, "wb") as fp:
            qr.save(fp)
        console.print(f"[green]QR code saved to {output}[/green]")
    except ImportError:
        # Fallback: save a text file with the link
        out_path = Path(output).with_suffix(".txt")
        out_path.write_text(
            f"Class: {info.name or code}\n"
            f"Code: {code}\n"
            f"Join link: https://t.me/clawed_bot?start={code}\n",
            encoding="utf-8",
        )
        console.print(f"[yellow]qrcode package not installed. Link saved to {out_path}[/yellow]")
        console.print("[dim]Install with: pip install qrcode[pil][/dim]")

