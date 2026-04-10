"""CLI commands for sub packet and parent communication generators."""

from __future__ import annotations

from typing import Optional

import typer
from rich.panel import Panel

from clawed._json_output import run_json_command
from clawed.commands._helpers import _safe_progress, console
from clawed.commands._helpers import run_async as _run_async

sub_app = typer.Typer()


def _sub_json(*, class_name, grade, subject, date, topic, context, teacher, school, period):
    """Run sub-packet generation and return structured result for JSON output."""
    from clawed.llm import LLMClient
    from clawed.models import AppConfig
    from clawed.sub_packet import (
        SubPacketRequest,
        generate_sub_packet,
        save_sub_packet,
    )

    cfg = AppConfig.load()
    teacher_name = teacher or cfg.teacher_profile.name or "Teacher"
    school_name = school or cfg.teacher_profile.school or ""

    request = SubPacketRequest(
        teacher_name=teacher_name,
        school=school_name,
        class_name=class_name,
        grade=grade,
        subject=subject,
        date=date,
        period_or_time=period or class_name,
        lesson_topic=topic or "",
        lesson_context=context or "",
    )

    llm = LLMClient(cfg)
    packet = _run_async(generate_sub_packet(request, llm))
    md_path = save_sub_packet(packet)

    return {
        "data": packet.model_dump() if hasattr(packet, "model_dump") else None,
        "files": [str(md_path)],
    }


@sub_app.command(name="sub")
def sub(
    class_name: str = typer.Option(..., "--class", "-c", help="Class name (e.g. 'Period 3 Global Studies')"),
    grade: str = typer.Option(..., "--grade", "-g", help="Grade level"),
    subject: str = typer.Option(..., "--subject", "-s", help="Subject"),
    date: str = typer.Option(..., "--date", "-d", help="Date (e.g. 'March 25, 2026')"),
    topic: Optional[str] = typer.Option(None, "--topic", "-t", help="Lesson topic"),
    context: Optional[str] = typer.Option(None, "--context", help="What unit are we in?"),
    teacher: Optional[str] = typer.Option(
        None, "--teacher", help="Teacher name (auto-detected from profile if omitted)"
    ),
    school: Optional[str] = typer.Option(None, "--school", help="School name (auto-detected from profile if omitted)"),
    period: str = typer.Option("", "--period", "-p", help="Period or time slot"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Generate a complete substitute teacher packet."""
    if json_output:
        run_json_command(
            "sub.sub",
            _sub_json,
            class_name=class_name,
            grade=grade,
            subject=subject,
            date=date,
            topic=topic,
            context=context,
            teacher=teacher,
            school=school,
            period=period,
        )
        return

    from clawed.llm import LLMClient
    from clawed.models import AppConfig
    from clawed.sub_packet import (
        SubPacketRequest,
        generate_sub_packet,
        save_sub_packet,
        sub_packet_to_markdown,
    )

    cfg = AppConfig.load()

    # Auto-detect teacher name and school from profile
    teacher_name = teacher or cfg.teacher_profile.name or "Teacher"
    school_name = school or cfg.teacher_profile.school or ""

    request = SubPacketRequest(
        teacher_name=teacher_name,
        school=school_name,
        class_name=class_name,
        grade=grade,
        subject=subject,
        date=date,
        period_or_time=period or class_name,
        lesson_topic=topic or "",
        lesson_context=context or "",
    )

    console.print(
        Panel(
            f"Generating sub packet for [bold]{class_name}[/bold] on {date}",
            title="[bold blue]Substitute Teacher Packet[/bold blue]",
            border_style="blue",
        )
    )

    with _safe_progress(console=console) as progress:
        task = progress.add_task("Generating sub packet...", total=None)
        llm = LLMClient(cfg)
        packet = _run_async(generate_sub_packet(request, llm))
        progress.update(task, description="Sub packet complete!")

    md_path = save_sub_packet(packet)
    console.print(f"[green]Saved:[/green] {md_path}")

    md = sub_packet_to_markdown(packet)
    console.print()
    console.print(Panel(md, title="Sub Packet Preview", border_style="blue"))


def _parent_comm_json(*, comm_type, student_desc, context, tone, notes):
    """Run parent-comm generation and return structured result for JSON output."""
    from clawed.llm import LLMClient
    from clawed.models import AppConfig
    from clawed.parent_comm import (
        CommType,
        ParentCommRequest,
        generate_parent_comm,
        parent_comm_to_text,
    )

    type_map = {
        "progress": CommType.PROGRESS_UPDATE,
        "behavior": CommType.BEHAVIOR_CONCERN,
        "positive": CommType.POSITIVE_NOTE,
        "unit": CommType.UPCOMING_UNIT,
        "permission": CommType.PERMISSION_REQUEST,
        "general": CommType.GENERAL_UPDATE,
    }

    resolved_type = type_map.get(comm_type.lower())
    if resolved_type is None:
        raise ValueError(f"Unknown type: {comm_type}. Choose from: {', '.join(type_map.keys())}")

    request = ParentCommRequest(
        comm_type=resolved_type,
        student_description=student_desc,
        class_context=context,
        tone=tone,
        additional_notes=notes or "",
    )

    cfg = AppConfig.load()
    llm = LLMClient(cfg)
    comm = _run_async(generate_parent_comm(request, llm))
    text = parent_comm_to_text(comm)

    return {
        "data": {
            "comm_type": resolved_type.value,
            "student_description": student_desc,
            "text": text,
        },
        "files": [],
    }


@sub_app.command(name="parent-comm")
def parent_comm(
    comm_type: str = typer.Option(
        ..., "--type", "-t", help="Type: progress, behavior, positive, unit, permission, general"
    ),
    student_desc: str = typer.Option(..., "--student-desc", "-s", help="Student description (no real names)"),
    context: str = typer.Option(..., "--context", "-c", help="Class context (e.g. 'Unit 4 WWI')"),
    tone: str = typer.Option("professional and warm", "--tone", help="Tone of the communication"),
    notes: Optional[str] = typer.Option(None, "--notes", "-n", help="Additional notes"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Generate a professional parent communication email."""
    if json_output:
        run_json_command(
            "sub.parent-comm",
            _parent_comm_json,
            comm_type=comm_type,
            student_desc=student_desc,
            context=context,
            tone=tone,
            notes=notes,
        )
        return

    from clawed.llm import LLMClient
    from clawed.models import AppConfig
    from clawed.parent_comm import (
        CommType,
        ParentCommRequest,
        generate_parent_comm,
        parent_comm_to_text,
    )

    type_map = {
        "progress": CommType.PROGRESS_UPDATE,
        "behavior": CommType.BEHAVIOR_CONCERN,
        "positive": CommType.POSITIVE_NOTE,
        "unit": CommType.UPCOMING_UNIT,
        "permission": CommType.PERMISSION_REQUEST,
        "general": CommType.GENERAL_UPDATE,
    }

    resolved_type = type_map.get(comm_type.lower())
    if resolved_type is None:
        console.print(f"[red]Unknown type:[/red] {comm_type}. Choose from: {', '.join(type_map.keys())}")
        raise typer.Exit(1)

    request = ParentCommRequest(
        comm_type=resolved_type,
        student_description=student_desc,
        class_context=context,
        tone=tone,
        additional_notes=notes or "",
    )

    console.print(
        Panel(
            f"Generating [bold]{resolved_type.value.replace('_', ' ').title()}[/bold] for: {student_desc}",
            title="[bold green]Parent Communication[/bold green]",
            border_style="green",
        )
    )

    cfg = AppConfig.load()
    with _safe_progress(console=console) as progress:
        task = progress.add_task("Writing parent communication...", total=None)
        llm = LLMClient(cfg)
        comm = _run_async(generate_parent_comm(request, llm))
        progress.update(task, description="Communication complete!")

    text = parent_comm_to_text(comm)
    console.print()
    console.print(Panel(text, title="Parent Communication", border_style="green"))
