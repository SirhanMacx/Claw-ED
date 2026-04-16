"""Simulation generation command — create interactive HTML science simulations."""

from __future__ import annotations

from pathlib import Path
from typing import Any

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

simulation_app = typer.Typer(help="Create interactive HTML simulations for science exploration.")


def _simulation_create_json(*, topic: str, grade: str, subject: str, sim_type: str) -> dict[str, Any]:
    """Run simulation creation and return structured result for JSON output."""
    from clawed.compile_simulation import compile_simulation
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
    sim_path = _run_async(
        compile_simulation(
            master=master, persona=persona, output_dir=out_dir,
            simulation_type=sim_type,
        )
    )

    return {
        "data": {"title": topic, "type": sim_type or "auto"},
        "files": [str(sim_path)] if sim_path else [],
    }


@simulation_app.command("create")
def create(
    topic: str = typer.Argument(
        ..., help="Simulation topic (e.g. 'Pendulum Motion')"
    ),
    grade: str = typer.Option("8", "--grade", "-g", help="Grade level"),
    subject: str | None = typer.Option(
        None, "--subject", "-s", help="Subject area (reads from your profile if not set)"
    ),
    sim_type: str = typer.Option(
        "",
        "--type",
        help="Simulation type (e.g. 'physics', 'chemistry', 'math', "
        "'biology'). Leave empty for AI to decide.",
    ),
    from_lesson: str | None = typer.Option(
        None,
        "--from-lesson",
        "-l",
        help="Generate simulation from existing lesson JSON file",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Generate an interactive HTML science simulation.

    \b
    From a topic (generates lesson first, then simulation):
        clawed simulate create "Pendulum Motion" -g 9 -s "Physics"

    With simulation type:
        clawed simulate create "Chemical Equilibrium" -g 10 --type chemistry

    From an existing lesson:
        clawed simulate create "topic" --from-lesson output/lesson_01.json
    """
    # Resolve subject from teacher profile if not provided
    if subject is None:
        from clawed.commands._helpers import get_default_subject
        subject = get_default_subject()

    if json_output:
        run_json_command(
            "simulate.create", _simulation_create_json,
            topic=topic, grade=grade, subject=subject, sim_type=sim_type,
        )
        return

    check_api_key_or_exit()

    from clawed.compile_simulation import compile_simulation

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
        # Generate a lesson first, then make the simulation
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

    # Warn about model capability for simulations
    from clawed.models import AppConfig as _SimConfig
    _sim_cfg = _SimConfig.load()
    _sim_model = getattr(_sim_cfg, 'ollama_model', '') if _sim_cfg.provider.value == 'ollama' else ''
    if _sim_model and any(s in _sim_model.lower() for s in ['haiku', 'flash', 'mini', 'small']):
        console.print("[yellow]Note: Interactive simulations work best with code-capable models.[/yellow]")

    # Generate the simulation
    out_dir = _output_dir()
    with _safe_progress(console=console) as progress:
        task = progress.add_task(
            "Building your simulation (every simulation is unique)...", total=None
        )
        sim_path = _run_async(
            compile_simulation(
                master=master,
                persona=persona,
                output_dir=out_dir,
                simulation_type=sim_type,
            )
        )
        progress.update(task, description="Simulation ready!")

    console.print(f"\n[green]Simulation created:[/green] {sim_path}")
    console.print(
        f"[dim]Open in browser: [bold]open {sim_path}[/bold][/dim]"
    )

    # Auto-open in browser
    try:
        import subprocess

        subprocess.Popen(
            ["open", str(sim_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (FileNotFoundError, OSError):
        pass


@simulation_app.command("gallery")
def gallery() -> None:
    """Open the local simulation gallery — all simulations you've generated."""
    out_dir = _output_dir()
    sims = sorted(out_dir.glob("*_simulation.html"))

    if not sims:
        console.print(
            "[yellow]No simulations generated yet.[/yellow] "
            "Run [bold]clawed simulate create \"Topic\"[/bold] to make one."
        )
        raise typer.Exit(0)

    console.print(f"\n[bold]Your Simulations ({len(sims)}):[/bold]\n")
    for i, s in enumerate(sims, 1):
        name = s.stem.replace("_simulation", "").replace("_", " ").title()
        size = s.stat().st_size / 1024
        console.print(f"  {i}. {name} ({size:.0f} KB)")

    console.print(
        f"\n[dim]Simulations are in: {out_dir}[/dim]"
    )
    console.print(
        "[dim]Open any simulation: [bold]open path/to/simulation.html[/bold][/dim]"
    )
