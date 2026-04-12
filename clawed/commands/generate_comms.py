"""Sub-packet & parent-note commands — split from generate.py for maintainability."""

from __future__ import annotations

import typer
from rich.panel import Panel

from clawed._json_output import run_json_command
from clawed.commands._helpers import (
    _safe_progress,
    check_api_key_or_exit,
    console,
    friendly_error,
)
from clawed.commands._helpers import output_dir as _output_dir
from clawed.commands._helpers import run_async as _run_async
from clawed.commands.generate import generate_app
from clawed.models import AppConfig

# ── Sub-Packet command ──────────────────────────────────────────────────


def _sub_packet_json(*, date, class_name, grade, subject, topic):
    """Run sub-packet generation and return structured result for JSON output."""
    from datetime import datetime, timedelta

    from clawed.llm import LLMClient
    from clawed.sub_packet import (
        SubPacketRequest,
        generate_sub_packet,
        save_sub_packet,
    )

    resolved_date = date.strip().lower()
    if resolved_date == "tomorrow":
        resolved_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    elif resolved_date == "today":
        resolved_date = datetime.now().strftime("%Y-%m-%d")

    cfg = AppConfig.load()
    teacher_name = cfg.teacher_profile.name or "Teacher"
    school_name = cfg.teacher_profile.school or ""

    request = SubPacketRequest(
        teacher_name=teacher_name,
        school=school_name,
        class_name=class_name,
        grade=grade,
        subject=subject,
        date=resolved_date,
        period_or_time=class_name,
        lesson_topic=topic or "",
    )

    llm = LLMClient(cfg)
    packet = _run_async(generate_sub_packet(request, llm))
    md_path = save_sub_packet(packet, _output_dir())

    return {
        "data": packet.model_dump() if hasattr(packet, "model_dump") else None,
        "files": [str(md_path)],
    }


@generate_app.command(name="sub-packet")
def sub_packet(
    date: str = typer.Option(
        ...,
        "--date",
        "-d",
        help="Date for the sub packet (e.g. '2026-03-24' or 'tomorrow')",
    ),
    class_name: str = typer.Option(
        "My Class", "--class", "-c", help="Class name"
    ),
    grade: str = typer.Option("8", "--grade", "-g", help="Grade level"),
    subject: str | None = typer.Option(
        None, "--subject", "-s", help="Subject (reads from your profile if not set)"
    ),
    topic: str | None = typer.Option(
        None, "--topic", "-t", help="Lesson topic"
    ),
    fmt: str = typer.Option(
        "text", "--format", "-f", help="Output format: text, json"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Generate a complete substitute teacher packet."""
    # Resolve subject from teacher profile if not provided
    if subject is None:
        from clawed.commands._helpers import get_default_subject
        subject = get_default_subject()

    if json_output:
        run_json_command(
            "gen.sub-packet",
            _sub_packet_json,
            date=date,
            class_name=class_name,
            grade=grade,
            subject=subject,
            topic=topic,
        )
        return

    check_api_key_or_exit()

    from datetime import datetime, timedelta

    from clawed.llm import LLMClient
    from clawed.sub_packet import (
        SubPacketRequest,
        generate_sub_packet,
        save_sub_packet,
        sub_packet_to_markdown,
    )

    resolved_date = date.strip().lower()
    if resolved_date == "tomorrow":
        resolved_date = (datetime.now() + timedelta(days=1)).strftime(
            "%Y-%m-%d"
        )
    elif resolved_date == "today":
        resolved_date = datetime.now().strftime("%Y-%m-%d")

    cfg = AppConfig.load()
    teacher_name = cfg.teacher_profile.name or "Teacher"
    school_name = cfg.teacher_profile.school or ""

    request = SubPacketRequest(
        teacher_name=teacher_name,
        school=school_name,
        class_name=class_name,
        grade=grade,
        subject=subject,
        date=resolved_date,
        period_or_time=class_name,
        lesson_topic=topic or "",
    )

    console.print(
        Panel(
            f"Generating sub packet for [bold]{resolved_date}[/bold]",
            title="[bold blue]Substitute Teacher Packet[/bold blue]",
            border_style="blue",
        )
    )

    with _safe_progress(console=console) as progress:
        task = progress.add_task("Generating sub packet...", total=None)
        llm = LLMClient(cfg)
        try:
            packet = _run_async(generate_sub_packet(request, llm))
        except (RuntimeError, ValueError) as e:
            console.print(f"[red]{friendly_error(e)}[/red]")
            raise typer.Exit(1)
        progress.update(task, description="Sub packet complete!")

    md_path = save_sub_packet(packet, _output_dir())
    console.print(f"[green]Saved:[/green] {md_path}")

    if fmt == "text":
        text = sub_packet_to_markdown(packet)
        console.print()
        console.print(
            Panel(text, title="Sub Packet Preview", border_style="blue")
        )
    else:
        console.print(
            Panel(
                f"[bold]Teacher:[/bold] {packet.teacher_name}\n"
                f"[bold]Date:[/bold] {packet.date}\n"
                f"[bold]Class:[/bold] {packet.class_name}\n"
                f"[bold]Instructions:[/bold] {len(packet.lesson_instructions)}\n"
                f"[bold]Materials:[/bold]"
                f" {len(packet.materials_needed)} items",
                title="Sub Packet Summary",
            )
        )


# ── Parent Note command ─────────────────────────────────────────────────


def _parent_note_json(*, student, topic, strengths, growth, teacher_id):
    """Run parent-note generation and return structured result for JSON output."""
    from clawed.parent_comm import (
        generate_progress_update,
        save_progress_update,
    )
    from clawed.state import TeacherSession as _TeacherSession

    session = _TeacherSession.load(teacher_id)
    persona = session.persona

    strength_list = (
        [s.strip() for s in strengths.split(",")] if strengths else []
    )
    growth_list = (
        [g.strip() for g in growth.split(",")] if growth else []
    )

    update = _run_async(
        generate_progress_update(
            student_name=student,
            strengths=strength_list,
            areas_to_grow=growth_list,
            teacher_persona=persona,
            topic=topic,
        )
    )

    out_dir = _output_dir()
    json_path = save_progress_update(update, out_dir)

    return {
        "data": update.model_dump() if hasattr(update, "model_dump") else None,
        "files": [str(json_path)],
    }


@generate_app.command(name="parent-note")
def parent_note(
    student: str = typer.Option(
        ..., "--student", "-s", help="Student's name"
    ),
    topic: str = typer.Option(
        "general progress",
        "--topic",
        "-t",
        help="Note context (e.g. 'midterm', 'behavior')",
    ),
    strengths: str | None = typer.Option(
        None, "--strengths", help="Comma-separated strengths"
    ),
    growth: str | None = typer.Option(
        None, "--growth", help="Comma-separated growth areas"
    ),
    teacher_id: str = typer.Option(
        "local-teacher", "--id", help="Teacher session ID"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Generate a parent progress update in the teacher's voice."""
    if json_output:
        run_json_command(
            "gen.parent-note",
            _parent_note_json,
            student=student,
            topic=topic,
            strengths=strengths,
            growth=growth,
            teacher_id=teacher_id,
        )
        return

    check_api_key_or_exit()

    from clawed.parent_comm import (
        format_progress_update_text,
        generate_progress_update,
        save_progress_update,
    )
    from clawed.state import TeacherSession as _TeacherSession

    session = _TeacherSession.load(teacher_id)
    persona = session.persona

    strength_list = (
        [s.strip() for s in strengths.split(",")] if strengths else []
    )
    growth_list = (
        [g.strip() for g in growth.split(",")] if growth else []
    )

    console.print(
        Panel(
            f"Generating progress update for"
            f" [bold]{student}[/bold]\nTopic: {topic}",
            title="[bold green]Parent Communication[/bold green]",
            border_style="green",
        )
    )

    with _safe_progress(console=console) as progress:
        task = progress.add_task(
            "Writing progress update...", total=None
        )
        try:
            update = _run_async(
                generate_progress_update(
                    student_name=student,
                    strengths=strength_list,
                    areas_to_grow=growth_list,
                    teacher_persona=persona,
                    topic=topic,
                )
            )
        except (RuntimeError, ValueError) as e:
            console.print(f"[red]{friendly_error(e)}[/red]")
            raise typer.Exit(1)
        progress.update(task, description="Progress update complete!")

    out_dir = _output_dir()
    json_path = save_progress_update(update, out_dir)
    console.print(f"[green]Saved:[/green] {json_path}")

    text = format_progress_update_text(update)
    console.print()
    console.print(
        Panel(
            text,
            title=f"Progress Update — {student}",
            border_style="green",
        )
    )
