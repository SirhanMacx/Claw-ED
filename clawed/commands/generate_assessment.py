"""Assessment & evaluation commands: materials, assess, rubric, score, improve, evaluate."""

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
from clawed.models import AppConfig

# ── Materials generation ─────────────────────────────────────────────────


def _materials_json(*, lesson_file: str) -> dict[str, Any]:
    """Run materials generation and return structured result for JSON output."""
    from clawed.lesson import load_lesson
    from clawed.materials import generate_all_materials, save_materials

    persona = load_persona_or_exit()
    daily = load_lesson(Path(lesson_file))
    mats = _run_async(generate_all_materials(daily, persona))
    out_dir = _output_dir()
    json_path = save_materials(mats, out_dir)

    return {
        "data": {
            "title": getattr(daily, "title", ""),
            "items": {
                "worksheet_items": len(mats.worksheet_items),
                "assessment_questions": len(mats.assessment_questions),
                "rubric_criteria": len(mats.rubric),
                "slides": len(mats.slide_outline),
            },
        },
        "files": [str(json_path)],
    }


@generate_app.command()
def materials(
    lesson_file: str = typer.Option(
        ..., "--lesson-file", "-l", help="Path to lesson plan JSON"
    ),
    fmt: str = typer.Option("markdown", "--format", "-f", help="Export format"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Generate all supporting materials for a lesson."""
    if json_output:
        run_json_command("gen.materials", _materials_json, lesson_file=lesson_file)
        return

    check_api_key_or_exit()

    from clawed.exporter import export_materials
    from clawed.lesson import load_lesson
    from clawed.materials import generate_all_materials, save_materials

    persona = load_persona_or_exit()
    daily = load_lesson(Path(lesson_file))

    with _safe_progress(console=console) as progress:
        task = progress.add_task("Generating worksheet...", total=4)
        try:
            mats = _run_async(generate_all_materials(daily, persona))
        except (RuntimeError, ValueError) as e:
            console.print(f"[red]{friendly_error(e)}[/red]")
            raise typer.Exit(1) from e
        progress.update(
            task, completed=4, description="All materials generated!"
        )

    out_dir = _output_dir()
    json_path = save_materials(mats, out_dir)
    export_path = export_materials(mats, out_dir, fmt=fmt)

    console.print(f"\n[green]Materials saved:[/green] {json_path}")
    console.print(f"[green]Exported:[/green] {export_path}")
    console.print(
        Panel(
            f"[bold]Worksheet:[/bold] {len(mats.worksheet_items)} items\n"
            f"[bold]Assessment:[/bold] {len(mats.assessment_questions)} questions\n"
            f"[bold]Rubric:[/bold] {len(mats.rubric)} criteria\n"
            f"[bold]Slides:[/bold] {len(mats.slide_outline)} slides\n"
            f"[bold]IEP Notes:[/bold] {len(mats.iep_notes)} accommodations",
            title="Materials Summary",
        )
    )


# ── Assessment intelligence ──────────────────────────────────────────────


@generate_app.command()
def assess(
    type: str = typer.Option(
        "quiz",
        "--type",
        "-t",
        help="Assessment type: formative, summative, dbq, quiz",
    ),
    topic: str = typer.Option("", "--topic", help="Topic for quiz or DBQ"),
    grade: str = typer.Option("8", "--grade", "-g", help="Grade level"),
    questions: int = typer.Option(
        10, "--questions", "-q", help="Number of questions (quiz only)"
    ),
    question_types: str = typer.Option(
        "mixed",
        "--question-types",
        help="Question types: mixed, multiple_choice, short_answer",
    ),
    lesson_file: str | None = typer.Option(
        None,
        "--lesson-file",
        "-l",
        help="Lesson JSON for formative assessment",
    ),
    unit_file: str | None = typer.Option(
        None,
        "--unit-file",
        "-u",
        help="Unit JSON for summative assessment",
    ),
    context: str = typer.Option(
        "", "--context", "-c", help="Additional context (DBQ)"
    ),
) -> None:
    """Generate intelligent assessments — DBQ, summative, formative, or quiz."""
    check_api_key_or_exit()

    from clawed.assessment import AssessmentGenerator

    persona = load_persona_or_exit()
    gen = AssessmentGenerator(AppConfig.load())
    out_dir = _output_dir()

    if type == "formative":
        _assess_formative(gen, persona, out_dir, lesson_file)
    elif type == "summative":
        _assess_summative(gen, persona, out_dir, unit_file)
    elif type == "dbq":
        _assess_dbq(gen, persona, out_dir, topic, grade, context)
    elif type == "quiz":
        _assess_quiz(gen, persona, out_dir, topic, grade, questions, question_types)
    else:
        console.print(f"[red]Unknown assessment type '{type}'. Use: formative, summative, dbq, quiz[/red]")
        raise typer.Exit(1)


def _assess_formative(
    gen: Any,
    persona: Any,
    out_dir: Path,
    lesson_file: str | None,
) -> None:
    from clawed.assessment import save_assessment
    if not lesson_file:
        console.print("[red]--lesson-file required for formative assessment.[/red]")
        raise typer.Exit(1)
    from clawed.lesson import load_lesson
    daily = load_lesson(Path(lesson_file))
    console.print(Panel(
        f"[bold]{daily.title}[/bold] \u2014 exit ticket for today's objective",
        title="Formative Assessment",
    ))
    with _safe_progress(console=console) as progress:
        task = progress.add_task("Generating exit ticket...", total=None)
        try:
            result = _run_async(gen.generate_formative(daily, persona))
        except (RuntimeError, ValueError) as e:
            console.print(f"[red]{friendly_error(e)}[/red]")
            raise typer.Exit(1) from e
        progress.update(task, description="Exit ticket ready!")
    path = save_assessment(result, out_dir, "formative")
    console.print(f"\n[green]Saved:[/green] {path}")
    console.print(Panel(
        f"[bold]Objective:[/bold] {result.objective}\n"
        f"[bold]Questions:[/bold] {len(result.questions)}\n"
        f"[bold]Time:[/bold] {result.time_minutes} minutes",
        title="Exit Ticket Summary",
    ))


def _assess_summative(
    gen: Any,
    persona: Any,
    out_dir: Path,
    unit_file: str | None,
) -> None:
    from clawed.assessment import save_assessment
    if not unit_file:
        console.print("[red]--unit-file required for summative assessment.[/red]")
        raise typer.Exit(1)
    from clawed.planner import load_unit
    unit_plan = load_unit(Path(unit_file))
    console.print(Panel(f"[bold]{unit_plan.title}[/bold] \u2014 unit test", title="Summative Assessment"))
    with _safe_progress(console=console) as progress:
        task = progress.add_task("Generating unit test...", total=None)
        try:
            result = _run_async(gen.generate_summative(unit_plan, persona))
        except (RuntimeError, ValueError) as e:
            console.print(f"[red]{friendly_error(e)}[/red]")
            raise typer.Exit(1) from e
        progress.update(task, description="Unit test ready!")
    path = save_assessment(result, out_dir, "summative")
    console.print(f"\n[green]Saved:[/green] {path}")
    console.print(Panel(
        f"[bold]Questions:[/bold] {len(result.questions)}\n"
        f"[bold]Total Points:[/bold] {result.total_points}\n"
        f"[bold]Rubric Criteria:[/bold] {len(result.rubric)}\n"
        f"[bold]Time:[/bold] {result.time_minutes} minutes",
        title="Unit Test Summary",
    ))


def _assess_dbq(
    gen: Any,
    persona: Any,
    out_dir: Path,
    topic: str,
    grade: str,
    context: str,
) -> None:
    from clawed.assessment import save_assessment
    if not topic:
        console.print("[red]--topic required for DBQ assessment.[/red]")
        raise typer.Exit(1)
    console.print(Panel(
        f"[bold]{topic}[/bold] \u2014 NYS Regents-style DBQ | Grade {grade}",
        title="Document-Based Question",
    ))
    with _safe_progress(console=console) as progress:
        task = progress.add_task("Generating DBQ with documents...", total=None)
        try:
            result = _run_async(gen.generate_dbq(topic, persona, grade_level=grade, context=context))
        except (RuntimeError, ValueError) as e:
            console.print(f"[red]{friendly_error(e)}[/red]")
            raise typer.Exit(1) from e
        progress.update(task, description="DBQ ready!")
    path = save_assessment(result, out_dir, "dbq")
    console.print(f"\n[green]Saved:[/green] {path}")
    console.print(Panel(
        f"[bold]Documents:[/bold] {len(result.documents)}\n"
        f"[bold]Rubric Criteria:[/bold] {len(result.rubric)}\n"
        f"[bold]Model Answer:[/bold] {'Yes' if result.model_answer else 'No'}\n"
        f"[bold]Time:[/bold] {result.time_minutes} minutes",
        title="DBQ Summary",
    ))


def _assess_quiz(
    gen: Any,
    persona: Any,
    out_dir: Path,
    topic: str,
    grade: str,
    questions: int,
    question_types: str,
) -> None:
    from clawed.assessment import save_assessment
    if not topic:
        console.print("[red]--topic required for quiz.[/red]")
        raise typer.Exit(1)
    console.print(Panel(
        f"[bold]{topic}[/bold] | Grade {grade} | {questions} questions ({question_types})",
        title="Quiz",
    ))
    with _safe_progress(console=console) as progress:
        task = progress.add_task("Generating quiz...", total=None)
        try:
            result = _run_async(gen.generate_quiz(
                topic=topic, question_count=questions,
                question_types=question_types, grade=grade, persona=persona,
            ))
        except (RuntimeError, ValueError) as e:
            console.print(f"[red]{friendly_error(e)}[/red]")
            raise typer.Exit(1) from e
        progress.update(task, description="Quiz ready!")
    path = save_assessment(result, out_dir, "quiz")
    console.print(f"\n[green]Saved:[/green] {path}")
    console.print(Panel(
        f"[bold]Questions:[/bold] {len(result.questions)}\n"
        f"[bold]Total Points:[/bold] {result.total_points}\n"
        f"[bold]Time:[/bold] {result.time_minutes} minutes",
        title="Quiz Summary",
    ))


@generate_app.command()
def rubric(
    task: str = typer.Option(
        ..., "--task", help="Description of the task to build a rubric for"
    ),
    criteria: int = typer.Option(
        4, "--criteria", "-c", help="Number of rubric criteria"
    ),
    grade: str = typer.Option("", "--grade", "-g", help="Grade level"),
) -> None:
    """Generate a detailed scoring rubric for any written task."""
    check_api_key_or_exit()

    from clawed.assessment import AssessmentGenerator, save_assessment

    persona = load_persona_or_exit()
    gen = AssessmentGenerator(AppConfig.load())

    console.print(
        Panel(
            f"[bold]{task}[/bold] | {criteria} criteria",
            title="Rubric Generator",
        )
    )

    with _safe_progress(console=console) as progress:
        prog_task = progress.add_task("Generating rubric...", total=None)
        try:
            result = _run_async(
                gen.generate_rubric(
                    task, persona, criteria_count=criteria, grade_level=grade
                )
            )
        except (RuntimeError, ValueError) as e:
            console.print(f"[red]{friendly_error(e)}[/red]")
            raise typer.Exit(1) from e
        progress.update(prog_task, description="Rubric ready!")

    out_dir = _output_dir()
    path = save_assessment(result, out_dir, "rubric")
    console.print(f"\n[green]Saved:[/green] {path}")

    # Display rubric as a table
    table = Table(title=f"Rubric: {task[:60]}")
    table.add_column("Criterion", style="bold")
    table.add_column("Excellent (4)", style="green")
    table.add_column("Proficient (3)", style="cyan")
    table.add_column("Developing (2)", style="yellow")
    table.add_column("Beginning (1)", style="red")
    for c in result.criteria:
        table.add_row(
            c.criterion, c.excellent, c.proficient, c.developing, c.beginning
        )
    console.print(table)
    console.print(f"\n[bold]Total Points:[/bold] {result.total_points}")


# ── Score command ────────────────────────────────────────────────────


@generate_app.command()
def score(
    lesson_file: str = typer.Option(
        ..., "--lesson-file", "-l", help="Path to a saved lesson JSON file"
    ),
) -> None:
    """Score a lesson plan on quality dimensions (1-5 per dimension)."""
    check_api_key_or_exit()

    import json

    from clawed.models import DailyLesson
    from clawed.quality import LessonQualityScore

    path = Path(lesson_file).expanduser().resolve()
    if not path.exists():
        console.print(f"[red]File not found:[/red] {path}")
        raise typer.Exit(1)

    data = json.loads(path.read_text(encoding="utf-8"))
    lesson_obj = DailyLesson.model_validate(data)

    with _safe_progress(console=console) as progress:
        task = progress.add_task("Scoring lesson quality...", total=None)
        scorer = LessonQualityScore()
        try:
            scores = _run_async(scorer.score(lesson_obj))
        except (RuntimeError, ValueError) as e:
            console.print(f"[red]{friendly_error(e)}[/red]")
            raise typer.Exit(1) from e
        progress.update(task, description="Scoring complete!")

    table = Table(title="Lesson Quality Score")
    table.add_column("Dimension", style="bold")
    table.add_column("Score", justify="center")
    table.add_column("Explanation")

    for dim in LessonQualityScore.dimensions:
        info = scores.get(dim, {})
        s = info.get("score", 0)
        color = "green" if s >= 4 else ("yellow" if s == 3 else "red")
        table.add_row(
            dim.replace("_", " ").title(),
            f"[{color}]{s}/5[/{color}]",
            info.get("explanation", ""),
        )

    console.print(table)
    overall = scores.get("overall", 0)
    color = "green" if overall >= 4 else ("yellow" if overall >= 3 else "red")
    console.print(
        f"\n[bold]Overall Score:[/bold] [{color}]{overall}/5[/{color}]"
    )


# ── Improve command ───────────────────────────────────────────────────


@generate_app.command()
def improve(
    days: int = typer.Option(
        7, "--days", "-d", help="Feedback window in days"
    ),
    analyze: bool = typer.Option(
        False, "--analyze", help="Run full analysis of feedback and update memory"
    ),
    reset: bool = typer.Option(
        False, "--reset", help="Clear all learned patterns (with confirmation)"
    ),
) -> None:
    """Show improvement stats, recent patterns, and memory contents.

    With --analyze: run a full analysis of recent feedback and update memory.
    With --reset: clear all learned patterns (requires confirmation).
    Without flags: show current improvement stats and learned patterns.
    """
    from clawed.memory_engine import get_improvement_stats, reset_memory

    # Handle --reset
    if reset:
        confirm = typer.confirm(
            "This will clear ALL learned patterns from memory.md. Are you sure?"
        )
        if confirm:
            reset_memory(confirm=True)
            console.print("[yellow]Memory reset to default template.[/yellow]")
        else:
            console.print("[dim]Reset cancelled.[/dim]")
        return

    # Handle --analyze (existing prompt improvement + memory engine)
    if analyze:
        check_api_key_or_exit()

        from clawed.database import Database
        from clawed.improver import improve_prompts

        db = Database()

        with _safe_progress(console=console) as progress:
            task = progress.add_task(
                "Analyzing feedback and improving prompts...", total=None
            )
            try:
                result = _run_async(improve_prompts(db, feedback_window_days=days))
            except (RuntimeError, ValueError) as e:
                console.print(f"[red]{friendly_error(e)}[/red]")
                raise typer.Exit(1) from e
            progress.update(task, description="Done!")

        db.close()

        status = result.get("status", "unknown")
        message = result.get("message", "")

        if status == "no_feedback":
            console.print(f"[yellow]{message}[/yellow]")
        elif status == "good":
            console.print(f"[green]{message}[/green]")
        elif status == "improved":
            console.print(
                Panel(
                    f"[green]{message}[/green]\n"
                    f"[bold]Prompt type:[/bold]"
                    f" {result.get('prompt_type', '')}\n"
                    f"[bold]New version:[/bold]"
                    f" {result.get('new_version', '')}\n"
                    f"[bold]Avg rating:[/bold]"
                    f" {result.get('feedback_summary', {}).get('avg_rating', '')}/5",
                    title="Prompt Improvement",
                )
            )
        else:
            console.print(f"[dim]{message}[/dim]")
        return

    # Default: show improvement stats and learned patterns
    stats = get_improvement_stats()

    # Build the stats table
    table = Table(title="Improvement Stats")
    table.add_column("Metric", style="bold")
    table.add_column("Value")

    table.add_row("Total lessons rated", str(stats["total_rated"]))
    avg = f"{stats['avg_rating']:.1f}/5" if stats["avg_rating"] > 0 else "--"
    table.add_row("Average rating", avg)
    table.add_row("Rating trend", stats["trend"])
    table.add_row("Total patterns learned", str(stats["total_patterns"]))
    table.add_row("  What works", str(stats["what_works_count"]))
    table.add_row("  What to avoid", str(stats["what_to_avoid_count"]))
    table.add_row("  Structural prefs", str(stats["structural_count"]))
    table.add_row("  Topic notes", str(stats["topic_notes_count"]))
    console.print(table)

    # Show recent patterns
    if stats["what_works"]:
        console.print("\n[green bold]Recent 'What Works' patterns:[/green bold]")
        for entry in stats["what_works"]:
            console.print(f"  [green]+[/green] {entry}")

    if stats["what_to_avoid"]:
        console.print("\n[red bold]Recent 'What to Avoid' patterns:[/red bold]")
        for entry in stats["what_to_avoid"]:
            console.print(f"  [red]-[/red] {entry}")

    if stats["total_patterns"] == 0:
        console.print(
            "\n[dim]No patterns learned yet. "
            "Generate and rate some lessons to start the feedback loop.[/dim]"
        )


# ── Evaluate command ──────────────────────────────────────────────────────


@generate_app.command()
def evaluate(
    lessons: int = typer.Option(
        5, "--lessons", "-n", help="Number of lessons to generate and evaluate"
    ),
    topic: str = typer.Option(
        "", "--topic", "-t", help="Topic for generated lessons (default: from persona)"
    ),
    grade: str = typer.Option(
        "", "--grade", "-g", help="Grade level (default: from persona)"
    ),
) -> None:
    """Generate lessons and evaluate voice consistency against your persona.

    This is the voice quality test harness. It generates N lessons using your
    persona, then uses the LLM to score each one on voice consistency,
    vocabulary match, and structure match.
    """
    check_api_key_or_exit()

    from clawed.evaluation import evaluate_voice_consistency
    from clawed.lesson import generate_lesson
    from clawed.models import DailyLesson, LessonBrief, UnitPlan

    persona = load_persona_or_exit()
    config = AppConfig.load()

    eval_topic = topic or persona.subject_area or "General Topics"
    eval_grade = grade or (persona.grade_levels[0] if persona.grade_levels else "8")

    console.print(
        Panel(
            f"Evaluating voice consistency\n"
            f"Persona: {persona.name}\n"
            f"Topic: {eval_topic} | Grade: {eval_grade}\n"
            f"Generating {lessons} lessons...",
            title="Voice Evaluation",
            border_style="blue",
        )
    )

    # Generate lessons
    generated: list[DailyLesson] = []
    with _safe_progress(console=console) as progress:
        task = progress.add_task("Generating lessons...", total=lessons)

        for i in range(1, lessons + 1):
            unit = UnitPlan(
                title=f"{eval_topic} Unit",
                subject=persona.subject_area or "General",
                grade_level=eval_grade,
                topic=eval_topic,
                duration_weeks=1,
                overview=f"A unit on {eval_topic}.",
                daily_lessons=[
                    LessonBrief(
                        lesson_number=1,
                        topic=f"{eval_topic} - Part {i}",
                        description=f"Lesson {i} on {eval_topic}",
                    )
                ],
            )
            try:
                lesson = _run_async(
                    generate_lesson(
                        lesson_number=1,
                        unit=unit,
                        persona=persona,
                        config=config,
                    )
                )
                lesson.lesson_number = i
                generated.append(lesson)
            except Exception as e:
                console.print(f"[yellow]Lesson {i} failed: {e}[/yellow]")
            progress.advance(task)

    if not generated:
        console.print("[red]No lessons generated. Check your LLM configuration.[/red]")
        raise typer.Exit(1)

    # Evaluate
    console.print("\nEvaluating voice consistency...")
    try:
        report = _run_async(evaluate_voice_consistency(persona, generated, config))
    except (RuntimeError, ValueError) as e:
        console.print(f"[red]{friendly_error(e)}[/red]")
        raise typer.Exit(1) from e

    # Display results
    eval_table = Table(title="Voice Evaluation Results")
    eval_table.add_column("Lesson", style="dim")
    eval_table.add_column("Voice", justify="center")
    eval_table.add_column("Vocab", justify="center")
    eval_table.add_column("Structure", justify="center")
    eval_table.add_column("Notes")

    for score in report.lesson_scores:
        eval_table.add_row(
            f"L{score.lesson_number}: {score.lesson_title[:30]}",
            f"{score.voice_consistency}/5",
            f"{score.vocabulary_match}/5",
            f"{score.structure_match}/5",
            score.notes[:50] if score.notes else "",
        )

    console.print(eval_table)

    console.print(
        Panel(
            f"Voice Consistency:  {report.avg_voice_consistency:.1f}/5\n"
            f"Vocabulary Match:   {report.avg_vocabulary_match:.1f}/5\n"
            f"Structure Match:    {report.avg_structure_match:.1f}/5\n"
            f"Overall Score:      {report.overall_score:.1f}/5\n\n"
            + (
                "Recommendations:\n" + "\n".join(f"  - {r}" for r in report.recommendations)
                if report.recommendations
                else "No recommendations."
            ),
            title="Summary",
            border_style="green" if report.overall_score >= 3.5 else "yellow",
        )
    )
