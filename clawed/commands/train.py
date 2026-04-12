"""Continuous improvement pipeline for Claw-ED fleet agents.

Usage:
    clawed train --drive          Ingest from configured Google Drive folders
    clawed train --path PATH      Ingest local materials and refine persona
    clawed train --benchmark      Generate & score N lessons for quality check
    clawed train --full           Drive ingest + benchmark in sequence
"""

from __future__ import annotations

import json
import random
from datetime import date
from pathlib import Path

import typer
from rich.table import Table

from clawed._json_output import run_json_command
from clawed.commands._helpers import console
from clawed.commands._helpers import run_async as _run_async

train_app = typer.Typer(help="Continuous improvement pipeline.")

_TRAINING_DIR = Path("~/.eduagent/training").expanduser()


# ── Persona refinement helper ───────────────────────────────────────────

async def _refine_persona(documents: list) -> None:
    """Extract persona traits from new documents and merge into existing."""
    from clawed.commands._helpers import persona_path
    from clawed.models import AppConfig, TeacherPersona
    from clawed.persona import extract_persona, load_persona, merge_persona, save_persona

    config = AppConfig.load()
    new_persona = await extract_persona(documents, config)

    # Load existing persona if available
    pp = persona_path()
    existing = load_persona(pp) if pp.exists() else TeacherPersona()

    merged = merge_persona(existing, new_persona)
    save_persona(merged, pp.parent)
    console.print("[green]Persona updated.[/green]")


# ── Drive ingest ────────────────────────────────────────────────────────

async def _drive_ingest() -> list:
    """Download and ingest from configured Drive URLs. Returns documents."""
    from clawed.drive import ingest_drive_folder
    from clawed.models import AppConfig

    config = AppConfig.load()
    drive_urls = config.teacher_profile.drive_urls

    if not drive_urls:
        console.print(
            "[yellow]No Drive URLs configured.[/yellow] "
            "Run [bold]clawed config profile[/bold] to add Google Drive folders."
        )
        return []

    all_docs = []
    for url in drive_urls:
        console.print(f"[dim]Fetching:[/dim] {url}")
        try:
            docs = await ingest_drive_folder(url)
            all_docs.extend(docs)
            console.print(f"  -> {len(docs)} documents ingested")
        except Exception as exc:
            console.print(f"  [red]Error:[/red] {exc}")

    if all_docs:
        console.print(f"\n[green]{len(all_docs)} total documents from Drive.[/green]")
    return all_docs


# ── Path ingest ─────────────────────────────────────────────────────────

def _path_ingest(path: Path) -> list:
    """Ingest local files. Returns documents."""
    from clawed.ingestor import ingest_path

    if not path.exists():
        console.print(f"[red]Path not found:[/red] {path}")
        raise typer.Exit(1)

    docs = ingest_path(path)
    console.print(f"[green]{len(docs)} documents ingested from {path}[/green]")
    return docs


# ── Benchmark ───────────────────────────────────────────────────────────

async def _run_benchmark(n: int) -> dict:
    """Generate N lessons on random topics and score them. Returns report."""
    from clawed.commands._helpers import load_persona_or_exit
    from clawed.lesson import generate_master_content
    from clawed.llm import LLMClient
    from clawed.models import AppConfig, LessonBrief, UnitPlan
    from clawed.quality import score_voice_match
    from clawed.validation import validate_master_content

    persona = load_persona_or_exit()
    config = AppConfig.load()
    client = LLMClient(config)

    # Build a minimal unit for benchmarking
    subjects = config.teacher_profile.subjects or ["General Studies"]
    subject = random.choice(subjects)
    grades = config.teacher_profile.grade_levels or persona.grade_levels or ["9"]
    grade = random.choice(grades)

    topics = [
        "Causes of World War I", "Photosynthesis", "Linear Equations",
        "The Civil Rights Movement", "Climate Change", "Shakespeare's Hamlet",
        "The Water Cycle", "Fractions and Decimals", "Ancient Rome",
        "Supply and Demand", "DNA and Genetics", "Poetry Analysis",
    ]
    sample_topics = random.sample(topics, min(n, len(topics)))

    results = []
    persona_ctx = persona.to_prompt_context()

    for i, topic in enumerate(sample_topics, 1):
        console.print(f"[dim]Generating lesson {i}/{n}: {topic}...[/dim]")
        try:
            unit = UnitPlan(
                title=f"Benchmark: {topic}",
                subject=subject,
                grade_level=grade,
                topic=topic,
                duration_weeks=1,
                overview=f"Benchmark lesson on {topic}",
                daily_lessons=[LessonBrief(
                    lesson_number=1,
                    topic=topic,
                    description=f"Students will understand key aspects of {topic}",
                )],
            )
            mc = await generate_master_content(
                lesson_number=1, unit=unit, persona=persona, config=config,
            )

            # Score voice match
            lesson_text = mc.model_dump_json()[:3000]
            voice_score = await score_voice_match(lesson_text, persona_ctx, client)

            # Validate content structure
            errors = validate_master_content(mc, topic)
            pedagogy_score = max(1.0, 5.0 - len(errors) * 0.5)
            diff_score = round((voice_score + pedagogy_score) / 2, 1)
            overall = round((voice_score + pedagogy_score + diff_score) / 3, 1)

            results.append({
                "topic": topic,
                "voice": round(voice_score, 1),
                "pedagogy": round(pedagogy_score, 1),
                "differentiation": diff_score,
                "overall": overall,
                "errors": errors,
            })
        except Exception as exc:
            console.print(f"  [red]Failed:[/red] {exc}")
            results.append({
                "topic": topic,
                "voice": 0.0, "pedagogy": 0.0,
                "differentiation": 0.0, "overall": 0.0,
                "errors": [str(exc)],
            })

    # Display table
    table = Table(title=f"Benchmark Results ({len(results)} lessons)")
    table.add_column("Topic", style="bold")
    table.add_column("Voice", justify="right")
    table.add_column("Pedagogy", justify="right")
    table.add_column("Differentiation", justify="right")
    table.add_column("Overall", justify="right")

    for r in results:
        table.add_row(
            r["topic"][:20],
            f"{r['voice']:.1f}",
            f"{r['pedagogy']:.1f}",
            f"{r['differentiation']:.1f}",
            f"{r['overall']:.1f}",
        )
    console.print(table)

    # Save report
    report = {
        "date": str(date.today()),
        "n": len(results),
        "results": results,
        "avg_overall": round(
            sum(r["overall"] for r in results) / max(len(results), 1), 2
        ),
    }
    _TRAINING_DIR.mkdir(parents=True, exist_ok=True)
    report_path = _TRAINING_DIR / f"{date.today()}_train_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    console.print(f"[dim]Report saved: {report_path}[/dim]")

    return report


# ── Main command ────────────────────────────────────────────────────────

def _train_json(*, benchmark, n):
    """Run benchmark training and return structured result for JSON output."""
    import io
    import sys

    # Suppress console output during benchmark (Rich tables go to stdout)
    old_stdout = sys.stdout
    sys.stdout = io.StringIO()
    try:
        report = _run_async(_run_benchmark(n))
    finally:
        sys.stdout = old_stdout

    return {
        "data": {
            "mode": "benchmark",
            "lessons_generated": report.get("n", 0),
            "avg_score": report.get("avg_overall", 0),
            "scores": report.get("results", []),
        },
        "files": [],
    }


@train_app.callback(invoke_without_command=True)
def train(
    drive: bool = typer.Option(False, "--drive", help="Ingest from Google Drive folders"),
    path: str | None = typer.Option(None, "--path", help="Ingest local materials"),
    benchmark: bool = typer.Option(False, "--benchmark", help="Generate & score lessons"),
    n: int = typer.Option(3, "-n", help="Number of benchmark lessons"),
    full: bool = typer.Option(False, "--full", help="Run drive + benchmark"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Continuous improvement pipeline for Claw-ED fleet agents."""

    if json_output:
        run_json_command("train", _train_json, benchmark=benchmark, n=n)
        return

    if not any([drive, path, benchmark, full]):
        console.print(
            "[yellow]Specify a mode:[/yellow] --drive, --path, --benchmark, or --full\n"
            "Run [bold]clawed train --help[/bold] for details."
        )
        raise typer.Exit(0)

    async def _execute():
        docs = []

        # Drive ingest
        if drive or full:
            docs = await _drive_ingest()
            if docs:
                await _refine_persona(docs)

        # Path ingest
        if path:
            local_docs = _path_ingest(Path(path))
            if local_docs:
                await _refine_persona(local_docs)
                docs.extend(local_docs)

        # Benchmark
        if benchmark or full:
            await _run_benchmark(n)

        if docs:
            console.print(
                f"\n[bold green]Training complete.[/bold green] "
                f"{len(docs)} documents processed."
            )

    _run_async(_execute())
