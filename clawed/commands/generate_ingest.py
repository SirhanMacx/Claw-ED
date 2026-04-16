"""Ingest & transcribe commands — split from generate.py for maintainability."""

from __future__ import annotations

import logging
from pathlib import Path

import typer
from rich.panel import Panel
from rich.table import Table

from clawed._json_output import run_json_command
from clawed.commands._helpers import (
    _safe_progress,
    console,
    friendly_error,
)
from clawed.commands._helpers import output_dir as _output_dir
from clawed.commands._helpers import run_async as _run_async
from clawed.commands.generate import generate_app
from clawed.models import AppConfig

logger = logging.getLogger(__name__)

# ── Ingest command ───────────────────────────────────────────────────────


def _ingest_json(*, path):
    """Run ingest and return structured result for JSON output."""
    from clawed.ingestor import extract_rich
    from clawed.ingestor import ingest_path as _ingest
    from clawed.persona import extract_persona, load_persona, merge_persona, save_persona

    source = Path(path).expanduser().resolve()
    documents = _ingest(source)
    if not documents:
        return {"data": {"documents_count": 0, "images_count": 0, "persona_extracted": False}, "files": []}

    # Count images via rich extraction
    total_images = 0
    for doc in documents:
        if doc.source_path:
            extraction = extract_rich(Path(doc.source_path))
            if extraction:
                total_images += len(extraction.images)

    # Extract and merge persona
    new_persona = _run_async(extract_persona(documents))
    persona_path = _output_dir() / "persona.json"
    if persona_path.exists():
        try:
            existing = load_persona(persona_path)
            persona = merge_persona(existing, new_persona)
        except Exception:
            logger.warning("operation_failed", exc_info=True)
            persona = new_persona
    else:
        persona = new_persona
    out = save_persona(persona, _output_dir())

    return {
        "data": {
            "documents_count": len(documents),
            "images_count": total_images,
            "persona_extracted": True,
        },
        "files": [str(out)],
    }


@generate_app.command()
def ingest(
    path: str = typer.Argument(
        ..., help="Path to directory, ZIP file, or single file to ingest"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be processed without actually processing"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Ingest teaching materials and extract a teacher persona."""
    if json_output:
        run_json_command("gen.ingest", _ingest_json, path=path)
        return

    from clawed.ingestor import ingest_path, scan_directory

    source = Path(path).expanduser().resolve()

    if dry_run:
        console.print(
            Panel(
                f"[yellow]DRY RUN[/yellow] — scanning [bold]{source}[/bold]",
                title="Claw-ED",
            )
        )

        # Show format summary
        if source.is_dir():
            files, summary = scan_directory(source)
            console.print(f"\n[cyan]{summary}[/cyan]\n")
        documents = ingest_path(source, dry_run=True)

        if not documents:
            console.print("[red]No supported documents found.[/red]")
            raise typer.Exit(1)

        table = Table(title="Would Process")
        table.add_column("#", style="dim")
        table.add_column("Title", style="bold")
        table.add_column("Type")
        table.add_column("Path", style="dim")
        for i, doc in enumerate(documents, 1):
            table.add_row(
                str(i), doc.title, doc.doc_type.value.upper(), doc.source_path or ""
            )
        console.print(table)
        console.print(f"\n[green]{len(documents)} files would be processed.[/green]")
        return

    console.print(
        Panel(f"Ingesting materials from [bold]{source}[/bold]", title="Claw-ED")
    )

    # Scan once — reuse the file list for both summary and ingestion
    if source.is_dir():
        files, summary = scan_directory(source)
        console.print(f"\n[cyan]{summary}[/cyan]\n")
        file_count = len(files)
    else:
        file_count = 1

    with _safe_progress(console=console) as progress:
        task = progress.add_task(
            f"Ingesting {file_count} files...", total=file_count if file_count > 1 else None,
        )

        def _update_progress(current: int, total: int) -> None:
            progress.update(task, completed=current, total=total)

        documents = ingest_path(source, progress_callback=_update_progress)
        progress.update(
            task,
            description=f"Done — {len(documents)} documents extracted",
            completed=file_count,
        )

    if not documents:
        console.print("[red]No supported documents found.[/red]")
        raise typer.Exit(1)

    # Display what was found
    table = Table(title="Ingested Documents")
    table.add_column("#", style="dim")
    table.add_column("Title", style="bold")
    table.add_column("Type")
    table.add_column("Size", justify="right")
    for i, doc in enumerate(documents, 1):
        size = f"{len(doc.content):,} chars"
        table.add_row(str(i), doc.title, doc.doc_type.value.upper(), size)
    console.print(table)

    # Extract persona
    from clawed.persona import extract_persona, load_persona, merge_persona, save_persona

    with _safe_progress(console=console) as progress:
        task = progress.add_task("Analyzing teaching style...", total=None)
        try:
            new_persona = _run_async(extract_persona(documents))
        except (RuntimeError, ValueError) as e:
            console.print(f"[red]{friendly_error(e)}[/red]")
            raise typer.Exit(1) from e
        progress.update(task, description="Persona extracted!")

    # Merge with existing persona instead of overwriting
    persona_path = _output_dir() / "persona.json"
    old_persona = None
    if persona_path.exists():
        try:
            old_persona = load_persona(persona_path)
            persona = merge_persona(old_persona, new_persona)
            console.print("[cyan]Merged with existing persona.[/cyan]")
        except Exception:
            logger.warning("operation_failed", exc_info=True)
            persona = new_persona
    else:
        persona = new_persona

    # Override LLM-inferred name with configured teacher name
    try:
        cfg = AppConfig.load()
        if cfg.teacher_profile and cfg.teacher_profile.name:
            persona.name = f"{cfg.teacher_profile.name} Teaching Persona"
    except Exception:
        logger.warning("operation_failed", exc_info=True)
    # Also check identity.md
    try:
        from clawed.paths import workspace_dir
        identity_path = workspace_dir() / "identity.md"
        if identity_path.exists():
            import re
            content = identity_path.read_text(encoding="utf-8")
            name_match = re.match(r"^#\s+(.+)", content)
            if name_match:
                teacher_name = name_match.group(1).strip()
                if teacher_name and teacher_name != "Teacher":
                    persona.name = f"{teacher_name} Teaching Persona"
    except (FileNotFoundError, OSError):
        pass

    out = save_persona(persona, _output_dir())

    # Track persona changes for evolution
    try:
        from clawed.persona_evolution import record_ingestion_changes
        record_ingestion_changes(old_persona=old_persona, new_persona=persona)
    except ImportError:
        pass

    # Full pipeline: images + assets + chunks + KG + wiki
    kb_msg = ""
    asset_msg = ""
    try:
        from clawed.agent_core.identity import get_teacher_id
        from clawed.ingestor import full_ingest

        tid = get_teacher_id()
        ingest_result = full_ingest(
            source, teacher_id=tid,
            progress_callback=lambda msg: console.print(f"  [dim]{msg}[/dim]"),
        )
        kb_msg = (
            f"[bold]Knowledge base:[/bold] {ingest_result['chunks_indexed']} chunks"
        )
        if ingest_result["images_extracted"]:
            asset_msg = (
                f"[bold]Assets:[/bold] {ingest_result['assets_registered']} files, "
                f"{ingest_result['images_extracted']} images extracted"
            )
        if ingest_result["kg_entities"]:
            kb_msg += (
                f" · KG: {ingest_result['kg_entities']} concepts, "
                f"{ingest_result['kg_triples']} relationships"
            )
        if ingest_result["wiki_articles"]:
            kb_msg += f" · Wiki: {ingest_result['wiki_articles']} articles"
    except ImportError:
        pass

    info_parts = [
        f"[green]Persona saved to {out}[/green]\n",
        f"[bold]Style:[/bold] {persona.teaching_style.value.replace('_', ' ').title()}",
        f"[bold]Tone:[/bold] {persona.tone}",
        f"[bold]Subject:[/bold] {persona.subject_area}",
        f"[bold]Format:[/bold] {persona.preferred_lesson_format}",
    ]
    if kb_msg:
        info_parts.append(kb_msg)
    if asset_msg:
        info_parts.append(asset_msg)

    console.print(Panel("\n".join(info_parts), title="Teacher Persona"))


# ── Transcribe command ───────────────────────────────────────────────────


@generate_app.command()
def transcribe(
    audio_file: str = typer.Argument(
        ..., help="Path to audio file (ogg/wav/mp3/m4a)"
    ),
) -> None:
    """Transcribe a voice note to text using Whisper."""
    from clawed.voice import is_audio_file, transcribe_audio

    source = Path(audio_file).expanduser().resolve()
    if not source.exists():
        console.print(f"[red]File not found:[/red] {source}")
        raise typer.Exit(1)

    if not is_audio_file(source):
        console.print(f"[red]Unsupported format:[/red] {source.suffix}")
        console.print(
            "[dim]Supported: ogg, wav, mp3, m4a, flac, webm, opus[/dim]"
        )
        raise typer.Exit(1)

    with _safe_progress(console=console) as progress:
        progress.add_task("Transcribing audio...", total=None)
        try:
            text = _run_async(transcribe_audio(source))
        except RuntimeError as e:
            console.print(f"[red]{e}[/red]")
            raise typer.Exit(1) from e

    console.print(
        Panel(
            text,
            title="[bold green]Transcription[/bold green]",
            border_style="green",
        )
    )
