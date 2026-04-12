"""Game generation command — create interactive HTML learning games."""

from __future__ import annotations

from pathlib import Path

import typer

from clawed._json_output import run_json_command
from clawed.commands._helpers import (
    _safe_progress,
    check_api_key_or_exit,
    console,
    load_persona_or_exit,
)
from clawed.commands._helpers import output_dir as _output_dir
from clawed.commands._helpers import (
    run_async as _run_async,
)

game_app = typer.Typer(help="Create interactive HTML learning games from lesson content.")


def _game_create_json(*, topic, grade, subject, style, students):
    """Run game creation and return structured result for JSON output."""
    from clawed.compile_game import compile_game
    from clawed.lesson import generate_master_content
    from clawed.models import LessonBrief, UnitPlan

    persona = load_persona_or_exit()

    unit_plan = UnitPlan(
        title=f"{topic} Lesson",
        subject=subject,
        grade_level=grade,
        topic=topic,
        duration_weeks=1,
        overview=f"A lesson on {topic} for grade {grade} {subject}.",
        essential_questions=[f"What are the key concepts of {topic}?"],
        daily_lessons=[
            LessonBrief(
                lesson_number=1,
                topic=topic,
                description=f"Explore {topic}.",
                lesson_type="direct_instruction",
            )
        ],
    )

    master = _run_async(
        generate_master_content(lesson_number=1, unit=unit_plan, persona=persona)
    )

    out_dir = _output_dir()
    game_path = _run_async(
        compile_game(
            master=master, persona=persona, output_dir=out_dir,
            student_preferences=students, game_style=style,
        )
    )

    return {
        "data": {"title": topic, "mechanic": style or "auto"},
        "files": [str(game_path)] if game_path else [],
    }


@game_app.command("create")
def create(
    topic: str = typer.Argument(
        ..., help="Lesson topic (e.g. 'The Missouri Compromise')"
    ),
    grade: str = typer.Option("8", "--grade", "-g", help="Grade level"),
    subject: str | None = typer.Option(
        None, "--subject", "-s", help="Subject area (reads from your profile if not set)"
    ),
    style: str = typer.Option(
        "",
        "--style",
        help="Game style hint (e.g. 'Among Us impostor', 'Minecraft building', "
        "'Jeopardy', 'escape room'). Leave empty for AI to decide.",
    ),
    students: str = typer.Option(
        "",
        "--students",
        help="What your students are into (e.g. 'they love Fortnite', "
        "'competitive, love team challenges')",
    ),
    from_lesson: str | None = typer.Option(
        None,
        "--from-lesson",
        "-l",
        help="Generate game from existing lesson JSON file",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Generate an interactive HTML learning game.

    \b
    From a topic (generates lesson first, then game):
        clawed game create "The Renaissance" -g 9 -s "Global History"

    With student preferences:
        clawed game create "Photosynthesis" -g 6 --students "they love Minecraft"

    With style hint:
        clawed game create "Civil War" -g 8 --style "escape room"

    From an existing lesson:
        clawed game create "topic" --from-lesson output/lesson_01.json
    """
    # Resolve subject from teacher profile if not provided
    if subject is None:
        from clawed.commands._helpers import get_default_subject
        subject = get_default_subject()

    if json_output:
        run_json_command(
            "game.create", _game_create_json,
            topic=topic, grade=grade, subject=subject, style=style, students=students,
        )
        return

    check_api_key_or_exit()

    from clawed.compile_game import compile_game

    persona = load_persona_or_exit()

    if from_lesson:
        # Load existing MasterContent from lesson JSON

        from clawed.master_content import MasterContent

        lesson_path = Path(from_lesson)
        if not lesson_path.exists():
            console.print(f"[red]File not found:[/red] {from_lesson}")
            raise typer.Exit(1)
        master = MasterContent.model_validate_json(
            lesson_path.read_text(encoding="utf-8")
        )
    else:
        # Generate a lesson first, then make the game
        from clawed.lesson import generate_master_content
        from clawed.models import LessonBrief, UnitPlan

        unit_plan = UnitPlan(
            title=f"{topic} Lesson",
            subject=subject,
            grade_level=grade,
            topic=topic,
            duration_weeks=1,
            overview=f"A lesson on {topic} for grade {grade} {subject}.",
            essential_questions=[
                f"What are the key concepts of {topic}?"
            ],
            daily_lessons=[
                LessonBrief(
                    lesson_number=1,
                    topic=topic,
                    description=f"Explore {topic}.",
                    lesson_type="direct_instruction",
                )
            ],
        )

        with _safe_progress(console=console) as progress:
            task = progress.add_task(
                "Generating lesson content...", total=None
            )
            master = _run_async(
                generate_master_content(
                    lesson_number=1,
                    unit=unit_plan,
                    persona=persona,
                )
            )
            progress.update(task, description="Lesson content ready!")

    # Warn about model capability for games
    from clawed.models import AppConfig as _GameConfig
    _game_cfg = _GameConfig.load()
    _game_model = getattr(_game_cfg, 'ollama_model', '') if _game_cfg.provider.value == 'ollama' else ''
    if _game_model and any(s in _game_model.lower() for s in ['haiku', 'flash', 'mini', 'small']):
        console.print("[yellow]Note: Interactive games work best with code-capable models.[/yellow]")

    # Generate the game
    out_dir = _output_dir()
    with _safe_progress(console=console) as progress:
        task = progress.add_task(
            "Designing your game (every game is unique)...", total=None
        )
        game_path = _run_async(
            compile_game(
                master=master,
                persona=persona,
                output_dir=out_dir,
                student_preferences=students,
                game_style=style,
            )
        )
        progress.update(task, description="Game ready!")

    console.print(f"\n[green]Game created:[/green] {game_path}")
    console.print(
        f"[dim]Open in browser: [bold]open {game_path}[/bold][/dim]"
    )

    # Auto-open in browser
    try:
        import subprocess

        subprocess.Popen(
            ["open", str(game_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


@game_app.command("gallery")
def gallery():
    """Open the local game gallery — all games you've generated."""
    out_dir = _output_dir()
    games = sorted(out_dir.glob("game_*.html"))

    if not games:
        console.print(
            "[yellow]No games generated yet.[/yellow] "
            "Run [bold]clawed game create \"Topic\"[/bold] to make one."
        )
        raise typer.Exit(0)

    console.print(f"\n[bold]Your Games ({len(games)}):[/bold]\n")
    for i, g in enumerate(games, 1):
        name = g.stem.replace("game_", "").replace("_", " ").title()
        size = g.stat().st_size / 1024
        console.print(f"  {i}. {name} ({size:.0f} KB)")

    console.print(
        f"\n[dim]Games are in: {out_dir}[/dim]"
    )
    console.print(
        "[dim]Open any game: [bold]open path/to/game.html[/bold][/dim]"
    )
