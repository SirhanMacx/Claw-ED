"""Knowledge base commands -- browse, search, and manage your curriculum wiki."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

import typer
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

from clawed.commands._helpers import console

kb_app = typer.Typer(help="Browse and manage your curriculum knowledge base.")

_BASE_DIR = Path(os.environ.get("EDUAGENT_DATA_DIR", str(Path.home() / ".eduagent")))
_CORPUS_DB = _BASE_DIR / "corpus" / "corpus.db"
_CURRICULUM_STATE = _BASE_DIR / "curriculum_state.json"
_CURRICULUM_CACHE = _BASE_DIR / "jon_curriculum_cache"
_CURRICULUM_KB_DB = _BASE_DIR / "memory" / "curriculum_kb.db"


def _corpus_exists() -> bool:
    return _CORPUS_DB.exists()


def _load_curriculum_state() -> dict:
    """Load curriculum_state.json if it exists."""
    if _CURRICULUM_STATE.exists():
        try:
            return json.loads(_CURRICULUM_STATE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


@kb_app.command("stats")
def kb_stats() -> None:
    """Show knowledge base statistics -- files ingested, topics, and coverage."""
    state = _load_curriculum_state()

    # Count files in curriculum cache
    cache_files = 0
    cache_dirs = 0
    if _CURRICULUM_CACHE.exists():
        for d in _CURRICULUM_CACHE.iterdir():
            if d.is_dir():
                cache_dirs += 1
                cache_files += sum(1 for f in d.iterdir() if f.is_file())

    # Count corpus entries
    corpus_count = 0
    corpus_subjects: set[str] = set()
    corpus_types: dict[str, int] = {}
    if _corpus_exists():
        try:
            conn = sqlite3.connect(str(_CORPUS_DB))
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT COUNT(*) as cnt FROM corpus_examples").fetchone()
            corpus_count = row["cnt"] if row else 0
            for r in conn.execute("SELECT DISTINCT subject FROM corpus_examples"):
                corpus_subjects.add(r["subject"])
            for r in conn.execute("SELECT content_type, COUNT(*) as cnt FROM corpus_examples GROUP BY content_type"):
                corpus_types[r["content_type"]] = r["cnt"]
            conn.close()
        except Exception:
            pass

    # Count curriculum KB chunks
    kb_chunks = 0
    if _CURRICULUM_KB_DB.exists():
        try:
            conn = sqlite3.connect(str(_CURRICULUM_KB_DB))
            row = conn.execute("SELECT COUNT(*) as cnt FROM chunks").fetchone()
            kb_chunks = row[0] if row else 0
            conn.close()
        except Exception:
            pass

    # Course info from curriculum state
    courses = state.get("courses", {})

    lines = []
    lines.append(f"[bold]Curriculum Cache:[/bold] {cache_files} files across {cache_dirs} subjects")
    if courses:
        lines.append(f"[bold]Active Courses:[/bold]  {len(courses)}")
    lines.append(f"[bold]Corpus Examples:[/bold] {corpus_count}")
    if corpus_subjects:
        lines.append(f"[bold]Subjects:[/bold]        {', '.join(sorted(corpus_subjects))}")
    if corpus_types:
        type_str = ", ".join(f"{k}: {v}" for k, v in sorted(corpus_types.items()))
        lines.append(f"[bold]By Type:[/bold]         {type_str}")
    lines.append(f"[bold]KB Chunks:[/bold]       {kb_chunks} searchable text chunks")

    if not _corpus_exists() and cache_files == 0:
        lines.append("")
        lines.append(
            "[yellow]No files ingested yet.[/yellow] "
            "Run [bold]clawed ingest <path>[/bold] to add your teaching materials."
        )

    console.print(
        Panel(
            "\n".join(lines),
            title="[bold]Knowledge Base Stats[/bold]",
            border_style="cyan",
        )
    )


@kb_app.command("topics")
def kb_topics() -> None:
    """List all topics from your curriculum -- courses, units, and what's coming up."""
    state = _load_curriculum_state()
    courses = state.get("courses", {})

    if not courses:
        console.print(
            "[dim]No curriculum data yet. "
            "Your topics will appear here after you ingest materials "
            "or set up your courses.[/dim]"
        )
        return

    table = Table(title="Your Courses and Topics")
    table.add_column("Course", style="bold")
    table.add_column("Grade", style="cyan", justify="center")
    table.add_column("Current Unit", style="green")
    table.add_column("Status", style="yellow")
    table.add_column("Next Up", style="dim")

    for _key, course in courses.items():
        table.add_row(
            course.get("name", _key),
            course.get("grade", ""),
            course.get("current_unit", ""),
            course.get("status", ""),
            course.get("next_unit", ""),
        )

    console.print(table)

    # Show completed units per course
    for _key, course in courses.items():
        completed = course.get("units_completed", [])
        remaining = course.get("units_remaining", [])
        if completed or remaining:
            course_name = course.get("name", _key)
            tree = Tree(f"[bold]{course_name}[/bold]")
            if completed:
                done_branch = tree.add("[green]Completed[/green]")
                for u in completed:
                    done_branch.add(f"[dim]{u}[/dim]")
            if remaining:
                todo_branch = tree.add("[yellow]Remaining[/yellow]")
                for u in remaining:
                    todo_branch.add(u)
            console.print(tree)
            console.print()


@kb_app.command("search")
def kb_search(
    query: str = typer.Argument(..., help="What to search for in your materials"),
    limit: int = typer.Option(10, "--limit", "-n", help="Max results to show"),
) -> None:
    """Search your curriculum knowledge base for topics, files, and examples."""
    query_lower = query.lower()
    results: list[dict] = []

    # 1. Search corpus.db
    if _corpus_exists():
        try:
            conn = sqlite3.connect(str(_CORPUS_DB))
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT id, content_type, subject, grade_level, topic,
                       quality_score, source, created_at
                FROM corpus_examples
                WHERE topic LIKE ? OR subject LIKE ? OR content_type LIKE ?
                ORDER BY quality_score DESC
                LIMIT ?
                """,
                (f"%{query_lower}%", f"%{query_lower}%", f"%{query_lower}%", limit),
            ).fetchall()
            for r in rows:
                results.append(
                    {
                        "source": "corpus",
                        "type": r["content_type"],
                        "subject": r["subject"],
                        "grade": r["grade_level"],
                        "topic": r["topic"] or "",
                        "quality": r["quality_score"],
                        "created": r["created_at"] or "",
                    }
                )
            conn.close()
        except Exception:
            pass

    # 2. Search curriculum_state.json
    state = _load_curriculum_state()
    for _key, course in state.get("courses", {}).items():
        course_name = course.get("name", "")
        current = course.get("current_unit", "")
        notes = course.get("notes", "")
        searchable = f"{course_name} {current} {notes}".lower()
        all_units = course.get("units_completed", []) + course.get("units_remaining", [])
        for unit in all_units:
            if query_lower in unit.lower():
                results.append(
                    {
                        "source": "curriculum",
                        "type": "unit",
                        "subject": course_name,
                        "grade": course.get("grade", ""),
                        "topic": unit,
                        "quality": 0,
                        "created": "",
                    }
                )
        if query_lower in searchable and not any(r["subject"] == course_name for r in results):
            results.append(
                {
                    "source": "curriculum",
                    "type": "course",
                    "subject": course_name,
                    "grade": course.get("grade", ""),
                    "topic": current,
                    "quality": 0,
                    "created": "",
                }
            )

    # 3. Search file names in curriculum cache
    if _CURRICULUM_CACHE.exists():
        for subject_dir in _CURRICULUM_CACHE.iterdir():
            if not subject_dir.is_dir():
                continue
            for f in subject_dir.iterdir():
                if query_lower in f.name.lower():
                    results.append(
                        {
                            "source": "files",
                            "type": f.suffix.lstrip(".") or "file",
                            "subject": subject_dir.name.replace("_", " ").title(),
                            "grade": "",
                            "topic": f.name,
                            "quality": 0,
                            "created": "",
                        }
                    )

    if not results:
        console.print(f"[yellow]No results found for '{query}'.[/yellow]")
        if not _corpus_exists():
            console.print(
                "[dim]Your knowledge base is empty. "
                "Run [bold]clawed ingest <path>[/bold] to add your teaching materials.[/dim]"
            )
        return

    # De-duplicate and limit
    seen = set()
    unique_results = []
    for r in results:
        key = (r["source"], r["subject"], r["topic"])
        if key not in seen:
            seen.add(key)
            unique_results.append(r)
    results = unique_results[:limit]

    table = Table(title=f"Search Results for '{query}'")
    table.add_column("Source", style="dim")
    table.add_column("Type", style="cyan")
    table.add_column("Subject", style="bold")
    table.add_column("Grade", justify="center")
    table.add_column("Topic / File")

    for r in results:
        table.add_row(
            r["source"],
            r["type"],
            r["subject"],
            r["grade"],
            r["topic"],
        )

    console.print(table)
    console.print(f"\n[dim]{len(results)} result(s) found.[/dim]")


@kb_app.command("browse")
def kb_browse() -> None:
    """Browse your ingested curriculum files organized by subject."""
    if not _CURRICULUM_CACHE.exists():
        console.print(
            "[dim]No curriculum files found.[/dim]\n"
            "Run [bold]clawed ingest <path>[/bold] to add your teaching materials, "
            "or point to a folder of your lesson files."
        )
        return

    subjects = sorted(d for d in _CURRICULUM_CACHE.iterdir() if d.is_dir())

    if not subjects:
        console.print("[dim]No subject folders found in curriculum cache.[/dim]")
        return

    tree = Tree("[bold]Your Teaching Materials[/bold]")

    for subject_dir in subjects:
        files = sorted(f for f in subject_dir.iterdir() if f.is_file())
        label = subject_dir.name.replace("_", " ").title()
        branch = tree.add(f"[bold cyan]{label}[/bold cyan] ({len(files)} files)")

        # Show up to 8 files per subject, then summarize
        for f in files[:8]:
            size_kb = f.stat().st_size / 1024
            suffix = f.suffix.upper().lstrip(".")
            branch.add(f"[dim]{suffix}[/dim] {f.name} [dim]({size_kb:.0f} KB)[/dim]")
        if len(files) > 8:
            branch.add(f"[dim]... and {len(files) - 8} more files[/dim]")

    console.print(tree)

    total_files = sum(sum(1 for f in d.iterdir() if f.is_file()) for d in subjects)
    console.print(f"\n[dim]{len(subjects)} subjects, {total_files} files total.[/dim]")


# ── Wiki compilation commands ────────────────────────────────────────


@kb_app.command("compile")
def kb_compile(
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Recompile all articles, even unchanged ones.",
    ),
) -> None:
    """Compile your curriculum into a searchable wiki.

    Synthesizes ingested documents into organized markdown articles.
    Incremental by default -- only recompiles changed documents.
    """
    from clawed.commands._helpers import _safe_progress, check_api_key_or_exit, run_async
    from clawed.wiki import compile_wiki

    check_api_key_or_exit()

    with _safe_progress(console=console) as progress:
        task = progress.add_task("Compiling wiki...", total=None)

        def _on_progress(doc_title: str, current: int, total: int) -> None:
            progress.update(
                task,
                total=total,
                completed=current,
                description=f"[dim]{doc_title[:40]}...[/dim]" if len(doc_title) > 40 else f"[dim]{doc_title}[/dim]",
            )

        result = run_async(compile_wiki(force=force, on_progress=_on_progress))

    # Display results
    if result.total == 0:
        console.print(
            Panel(
                "No ingested documents found.\n\n"
                "Ingest your curriculum first:\n"
                "  [bold]clawed ingest ~/path/to/materials[/bold]",
                title="[yellow]Wiki[/yellow]",
                border_style="yellow",
            )
        )
        return

    summary = (
        f"[green]{result.compiled}[/green] compiled, "
        f"[dim]{result.skipped} unchanged[/dim], "
        f"{result.total} total articles"
    )
    if result.errors:
        summary += f"\n[yellow]{len(result.errors)} errors:[/yellow]"
        for err in result.errors[:5]:
            summary += f"\n  [dim]{err}[/dim]"

    console.print(
        Panel(
            summary,
            title=(
                "[bold green]Wiki Compiled[/bold green]"
                if not result.errors
                else "[bold yellow]Wiki Compiled (with errors)[/bold yellow]"
            ),
            border_style="green" if not result.errors else "yellow",
        )
    )


@kb_app.command("query")
def kb_query(
    question: str = typer.Argument(..., help="Question to ask your curriculum wiki."),
) -> None:
    """Ask a question and get an answer from your compiled wiki."""
    from rich.markdown import Markdown

    from clawed.commands._helpers import check_api_key_or_exit, run_async
    from clawed.wiki import INDEX_PATH, query_wiki

    if not INDEX_PATH.exists():
        console.print(
            "[yellow]No wiki found.[/yellow] Compile your curriculum first:\n  [bold]clawed kb compile[/bold]"
        )
        raise typer.Exit(1)

    check_api_key_or_exit()
    console.print(f"[dim]Searching wiki for: {question}[/dim]\n")

    try:
        result = run_async(query_wiki(question))
    except FileNotFoundError as e:
        console.print(f"[yellow]{e}[/yellow]")
        raise typer.Exit(1)

    # Display answer
    console.print(Markdown(result.answer))
    if result.sources:
        console.print(f"\n[dim]Sources: {', '.join(result.sources)} ({result.articles_read} articles read)[/dim]")


@kb_app.command("lint")
def kb_lint() -> None:
    """Check your wiki for stale, missing, or orphaned articles."""
    from clawed.wiki import ARTICLES_DIR, lint_wiki

    if not ARTICLES_DIR.exists():
        console.print(
            "[yellow]No wiki found.[/yellow] Compile your curriculum first:\n  [bold]clawed kb compile[/bold]"
        )
        raise typer.Exit(1)

    result = lint_wiki()

    if result.healthy:
        console.print(
            Panel(
                "[green]All articles are up to date.[/green]\nNo stale, uncovered, or orphaned articles found.",
                title="[bold green]Wiki Health: Clean[/bold green]",
                border_style="green",
            )
        )
        return

    # Stale articles
    if result.stale:
        table = Table(title="Stale Articles (source changed since compilation)")
        table.add_column("Document", style="yellow")
        table.add_column("Compiled At", style="dim")
        for item in result.stale:
            table.add_row(item["doc_title"], item.get("compiled_at", ""))
        console.print(table)
        console.print("[dim]Fix: clawed kb compile[/dim]\n")

    # Uncovered documents
    if result.uncovered:
        table = Table(title="Uncovered Documents (ingested but no wiki article)")
        table.add_column("Document", style="cyan")
        table.add_column("Chunks", justify="right")
        for item in result.uncovered:
            table.add_row(item["doc_title"], str(item.get("chunk_count", 0)))
        console.print(table)
        console.print("[dim]Fix: clawed kb compile[/dim]\n")

    # Orphaned articles
    if result.orphaned:
        table = Table(title="Orphaned Articles (source deleted)")
        table.add_column("Article", style="red")
        table.add_column("Original Document", style="dim")
        for item in result.orphaned:
            table.add_row(item.get("article_file", ""), item["doc_title"])
        console.print(table)
        console.print("[dim]These articles reference deleted source files.[/dim]\n")
