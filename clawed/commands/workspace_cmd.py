"""CLI commands for the teacher workspace."""

from __future__ import annotations

import typer
from rich.panel import Panel
from rich.table import Table

from clawed.commands._helpers import console

workspace_app = typer.Typer(help="Teacher workspace — identity, memory, notes, and student profiles.")


@workspace_app.command("init")
def workspace_init() -> None:
    """Initialize the workspace. Only creates missing files — never overwrites your edits."""
    from clawed.workspace import init_workspace

    ws_path = init_workspace()
    console.print(
        Panel(
            f"[bold green]Workspace ready![/bold green]\n\n"
            f"  Location: [cyan]{ws_path}[/cyan]\n\n"
            f"All files are yours to edit freely:\n"
            f"  - identity.md  (who you are)\n"
            f"  - soul.md      (teaching philosophy)\n"
            f"  - memory.md    (long-term memories)\n"
            f"  - heartbeat.md (scheduled task checks)\n"
            f"  - notes/       (daily teaching notes)\n"
            f"  - students/    (per-student profiles)\n\n"
            f"[dim]Re-running init will NOT overwrite existing files.\n"
            f"Use 'eduagent workspace regenerate' to rebuild from persona.[/dim]",
            title="[bold]Teacher Workspace[/bold]",
            border_style="green",
        )
    )


@workspace_app.command("regenerate")
def workspace_regenerate(
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
) -> None:
    """Regenerate identity.md and soul.md from persona.json (overwrites existing)."""
    from clawed.models import AppConfig, TeacherPersona
    from clawed.workspace import (
        IDENTITY_PATH,
        SOUL_PATH,
        WORKSPACE_DIR,
        generate_identity,
        generate_soul,
    )

    if not force:
        confirm = typer.confirm(
            "This will OVERWRITE identity.md and soul.md with fresh versions "
            "generated from your persona. Any manual edits will be lost. Continue?"
        )
        if not confirm:
            console.print("[yellow]Cancelled.[/yellow]")
            raise typer.Exit()

    cfg = AppConfig.load()

    # persona.json is the canonical source of truth for regeneration.
    # Try multiple known locations.
    persona = None
    try:
        from clawed.commands._helpers import persona_path
        from clawed.persona import load_persona

        pp = persona_path()
        if pp.exists():
            persona = load_persona(pp)
            console.print(f"[dim]Loaded persona from {pp}[/dim]")
    except (FileNotFoundError, OSError):
        pass

    if persona is None:
        # Check the data dir directly
        import os
        from pathlib import Path as _Path
        data_dir = _Path(os.environ.get("EDUAGENT_DATA_DIR", str(_Path.home() / ".eduagent")))
        alt_path = data_dir / "persona.json"
        if alt_path.exists():
            try:
                from clawed.persona import load_persona
                persona = load_persona(alt_path)
                console.print(f"[dim]Loaded persona from {alt_path}[/dim]")
            except ImportError:
                pass

    if persona is None:
        persona = TeacherPersona()
        console.print("[dim]No persona.json found — using defaults.[/dim]")

    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

    # Overwrite (not append) — write_text replaces the entire file
    IDENTITY_PATH.write_text(generate_identity(persona, cfg), encoding="utf-8")
    SOUL_PATH.write_text(generate_soul(persona, cfg), encoding="utf-8")
    console.print("[green]identity.md and soul.md regenerated from persona.[/green]")


@workspace_app.command("edit")
def workspace_edit(
    file: str = typer.Argument(
        ...,
        help="File to edit: identity, soul, memory, heartbeat",
    ),
) -> None:
    """Open a workspace file in your default editor."""
    import os
    import subprocess

    from clawed.workspace import (
        HEARTBEAT_PATH,
        IDENTITY_PATH,
        MEMORY_PATH,
        SOUL_PATH,
        _ensure_workspace,
    )

    _ensure_workspace()

    file_map = {
        "identity": IDENTITY_PATH,
        "soul": SOUL_PATH,
        "memory": MEMORY_PATH,
        "heartbeat": HEARTBEAT_PATH,
    }

    path = file_map.get(file.lower())
    if path is None:
        console.print(
            f"[red]Unknown file '{file}'. Choose from: "
            f"{', '.join(file_map.keys())}[/red]"
        )
        raise typer.Exit(1)

    editor = os.environ.get("EDITOR", os.environ.get("VISUAL", "nano"))
    console.print(f"[dim]Opening {path} in {editor}...[/dim]")
    subprocess.run([editor, str(path)])


@workspace_app.command("show")
def workspace_show() -> None:
    """Display identity, soul, and today's notes."""
    from clawed.workspace import (
        IDENTITY_PATH,
        SOUL_PATH,
        _ensure_workspace,
        get_daily_notes,
    )

    _ensure_workspace()

    if IDENTITY_PATH.exists():
        console.print(
            Panel(
                IDENTITY_PATH.read_text(encoding="utf-8"),
                title="[bold]Identity[/bold]",
                border_style="blue",
            )
        )
    else:
        console.print("[dim]No identity.md found. Run 'clawed workspace init'.[/dim]")

    if SOUL_PATH.exists():
        console.print(
            Panel(
                SOUL_PATH.read_text(encoding="utf-8"),
                title="[bold]Teaching Soul[/bold]",
                border_style="cyan",
            )
        )

    notes = get_daily_notes()
    if notes:
        console.print(
            Panel(
                notes,
                title="[bold]Today's Notes[/bold]",
                border_style="green",
            )
        )
    else:
        console.print("[dim]No notes for today yet.[/dim]")


@workspace_app.command("note")
def workspace_note(
    text: str = typer.Argument(..., help="Note text to append"),
    category: str = typer.Option("general", "--category", "-c", help="Note category"),
) -> None:
    """Add a note to today's daily notes file."""
    from clawed.workspace import _ensure_workspace, append_daily_note

    _ensure_workspace()
    append_daily_note(text, category=category)
    console.print(f"[green]Note added to today's file.[/green] [{category}]")


@workspace_app.command("memory")
def workspace_memory() -> None:
    """Show the long-term memory file."""
    from clawed.workspace import MEMORY_PATH, _ensure_workspace

    _ensure_workspace()

    if MEMORY_PATH.exists():
        console.print(
            Panel(
                MEMORY_PATH.read_text(encoding="utf-8"),
                title="[bold]Teaching Memory[/bold]",
                border_style="yellow",
            )
        )
    else:
        console.print("[dim]No memory.md found. Run 'clawed workspace init'.[/dim]")


@workspace_app.command("students")
def workspace_students(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """List all student profiles in the workspace."""
    from clawed.workspace import STUDENTS_DIR, _ensure_workspace, list_student_profiles

    _ensure_workspace()

    profiles = list_student_profiles()

    if json_output:
        from clawed._json_output import run_json_command
        def _students_json():
            return {"data": {"profiles": profiles or []}, "files": []}
        run_json_command("workspace.students", _students_json)
        return
    if not profiles:
        console.print(
            "[dim]No student profiles yet. They are created automatically"
            " from student bot interactions.[/dim]"
        )
        return

    table = Table(title="Student Profiles")
    table.add_column("#", style="dim", justify="right")
    table.add_column("Student Name", style="bold")
    table.add_column("File", style="cyan")

    for i, name in enumerate(profiles, 1):
        from clawed import _safe_filename

        filename = _safe_filename(name) + ".md"
        table.add_row(str(i), name, str(STUDENTS_DIR / filename))

    console.print(table)


@workspace_app.command("context")
def workspace_context() -> None:
    """Show what gets injected into LLM context."""
    from clawed.workspace import _ensure_workspace, load_context

    _ensure_workspace()

    ctx = load_context()
    if ctx:
        console.print(
            Panel(
                ctx,
                title="[bold]LLM Context Injection[/bold]",
                border_style="magenta",
            )
        )
    else:
        console.print("[dim]No workspace context available. Run 'clawed workspace init'.[/dim]")
