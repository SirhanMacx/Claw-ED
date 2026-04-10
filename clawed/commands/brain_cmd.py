"""CLI commands for the brain — list, get, search, dream, capture."""
from __future__ import annotations

import asyncio
from typing import Optional

import typer

from clawed.commands._helpers import console

brain_app = typer.Typer(
    name="brain",
    help="Manage the teaching brain — the compounding knowledge store.",
    rich_markup_mode="rich",
)


@brain_app.command("stats")
def stats_cmd() -> None:
    """Show brain statistics — pages per type."""
    from clawed.brain.store import BrainStore

    store = BrainStore()
    stats = store.stats()
    console.print("[bold cyan]Brain Statistics[/bold cyan]")
    console.print()
    total = 0
    for ptype, count in stats.items():
        console.print(f"  {ptype:12s}  [yellow]{count:5d}[/yellow] pages")
        total += count
    console.print()
    console.print(f"  [bold]Total:[/bold]      [green]{total:5d}[/green] pages")
    console.print(f"\n  Root: [dim]{store.root}[/dim]")


@brain_app.command("list")
def list_cmd(
    page_type: str = typer.Argument(
        "student",
        help="Page type: student, topic, lesson, original, concept, class, person",
    ),
    limit: int = typer.Option(20, "--limit", "-n", help="Max pages to list"),
) -> None:
    """List brain pages of a given type."""
    from clawed.brain.store import BrainStore

    store = BrainStore()
    slugs = store.list_pages(page_type)
    if not slugs:
        console.print(f"[yellow]No {page_type} pages found.[/yellow]")
        return

    console.print(f"[bold cyan]{page_type.title()} pages ({len(slugs)}):[/bold cyan]")
    for slug in slugs[:limit]:
        page = store.get(page_type, slug)
        if page:
            title = page.title
            n_entries = len(page.timeline)
            tier = page.metadata.get("tier", "?")
            console.print(
                f"  [green]{slug}[/green]  [dim]·[/dim] {title}  "
                f"[dim](tier {tier}, {n_entries} entries)[/dim]"
            )
    if len(slugs) > limit:
        console.print(f"\n  [dim]... and {len(slugs) - limit} more[/dim]")


@brain_app.command("get")
def get_cmd(
    page_type: str = typer.Argument(..., help="Page type"),
    slug: str = typer.Argument(..., help="Page slug"),
) -> None:
    """Read a brain page."""
    from clawed.brain.store import BrainStore

    store = BrainStore()
    page = store.get(page_type, slug)
    if page is None:
        console.print(f"[red]Page not found: {page_type}/{slug}[/red]")
        raise typer.Exit(1)

    console.print(page.render())


@brain_app.command("search")
def search_cmd(
    query: str = typer.Argument(..., help="Search query"),
    page_type: Optional[str] = typer.Option(
        None, "--type", "-t", help="Filter by page type",
    ),
    limit: int = typer.Option(10, "--limit", "-n", help="Max results"),
    include_corpus: bool = typer.Option(
        False, "--corpus/--no-corpus",
        help="Also search the curriculum corpus",
    ),
) -> None:
    """Hybrid search across brain pages (keyword + vector + RRF)."""
    from clawed.brain.search import hybrid_search

    results = hybrid_search(
        query,
        page_type=page_type,
        limit=limit,
        include_corpus=include_corpus,
    )
    if not results:
        console.print("[yellow]No results.[/yellow]")
        return

    console.print(
        f"[bold cyan]Results for '{query}':[/bold cyan] "
        f"({len(results)} found)\n"
    )
    for i, r in enumerate(results, start=1):
        console.print(
            f"{i}. [green]{r.page_type}/{r.slug}[/green] "
            f"[dim](score: {r.score:.3f}, via {r.source})[/dim]"
        )
        console.print(f"   [bold]{r.title}[/bold]")
        if r.snippet:
            console.print(f"   [dim]{r.snippet[:200]}[/dim]")
        console.print()


@brain_app.command("dream")
def dream_cmd(
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Report what would change, don't write",
    ),
    consolidate: bool = typer.Option(
        True, "--consolidate/--no-consolidate",
        help="Run LLM consolidation of compiled truth",
    ),
) -> None:
    """Run the dream cycle — overnight brain enrichment."""
    from clawed.brain.dream import dream_cycle

    console.print(
        "[bold cyan]Running dream cycle...[/bold cyan]" +
        (" [dim](dry run)[/dim]" if dry_run else "")
    )
    report = asyncio.run(dream_cycle(
        consolidate=consolidate,
        dry_run=dry_run,
    ))

    console.print()
    console.print(f"[green]Pages scanned:[/green] {report.pages_scanned}")
    console.print(f"[green]Consolidated:[/green] {report.pages_consolidated}")
    console.print(f"[green]Cross-links added:[/green] {report.cross_links_added}")

    if report.gaps_detected:
        console.print()
        console.print("[yellow]Gaps detected:[/yellow]")
        for gap in report.gaps_detected:
            console.print(f"  - {gap}")

    if report.errors:
        console.print()
        console.print("[red]Errors:[/red]")
        for err in report.errors:
            console.print(f"  - {err}")


@brain_app.command("capture")
def capture_cmd(
    message: str = typer.Argument(..., help="The insight to capture"),
    context: str = typer.Option("", "--context", "-c", help="Conversation context"),
    force: bool = typer.Option(
        False, "--force", "-f",
        help="Skip insight heuristic and always save",
    ),
) -> None:
    """Capture an original pedagogical insight to the brain."""
    from clawed.brain.capture import capture_original

    page = capture_original(
        message=message,
        context=context,
        source_channel="cli",
        force=force,
    )
    if page is None:
        console.print(
            "[yellow]Message didn't look like an insight. "
            "Use --force to save anyway.[/yellow]"
        )
        raise typer.Exit(1)

    console.print(f"[green]Captured:[/green] originals/{page.slug}")
    console.print(f"  Title: {page.title}")


@brain_app.command("add-student")
def add_student_cmd(
    name: str = typer.Argument(..., help="Student name (e.g. 'Julia M.')"),
    tier: int = typer.Option(
        2, "--tier", "-t",
        help="Tier 1=IEP/struggling, 2=typical, 3=minimal tracking",
    ),
    notes: str = typer.Option("", "--notes", "-n", help="Initial notes"),
) -> None:
    """Create a student brain page."""
    from datetime import datetime

    from clawed.brain.store import BrainPage, BrainStore

    store = BrainStore()
    slug = store.slugify(name)
    if store.exists("student", slug):
        console.print(
            f"[yellow]Student page already exists: {slug}[/yellow]"
        )
        raise typer.Exit(1)

    today = datetime.now().strftime("%Y-%m-%d")
    page = BrainPage(
        slug=slug,
        page_type="student",
        title=name,
        compiled_truth=(
            "## Compiled Truth\n\n"
            f"{notes if notes else '_(awaiting observation)_'}\n\n"
            "## Strengths\n\n_(to be filled in)_\n\n"
            "## Challenges\n\n_(to be filled in)_\n\n"
            "## Accommodations\n\n_(to be filled in)_"
        ),
        metadata={
            "tier": str(tier),
            "created": today,
            "updated": today,
        },
    )
    store.save(page)
    console.print(f"[green]Created:[/green] students/{slug} (tier {tier})")
