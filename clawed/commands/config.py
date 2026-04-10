"""Config, persona, standards, templates, skills, school, stats, and status commands.

This module is the registration hub: it creates all Typer sub-apps, defines the
register_stats / register_status helpers, then imports the split command modules
so their @*_app.command() decorators fire and attach commands to the apps.
"""

from __future__ import annotations

import typer
from rich.panel import Panel
from rich.table import Table

from clawed.commands._helpers import console
from clawed.models import AppConfig

config_app = typer.Typer(help="Configure Claw-ED settings.")
persona_app = typer.Typer(help="Manage teacher personas.")
standards_app = typer.Typer(help="Browse education standards (CCSS, NGSS, C3).")
templates_app = typer.Typer(help="Browse lesson structure templates.")
skills_app = typer.Typer(help="Browse subject-specific pedagogy skills.")
school_app = typer.Typer(help="Multi-teacher school deployment and shared curriculum.")
class_app = typer.Typer(help="Manage student class codes.")


# ── Stats command ────────────────────────────────────────────────────


def register_stats(app: typer.Typer) -> None:
    """Register the stats command on the main app."""

    @app.command()
    def stats(
        teacher_id: str = typer.Option(
            "local-teacher",
            "--teacher",
            "-t",
            help="Teacher ID",
        ),
    ):
        """Show a beautiful stats dashboard with rating trends and analytics.

        Displays lesson ratings, top topics, streaks, and areas for improvement.
        """
        from clawed.analytics import get_teacher_stats

        data = get_teacher_stats(teacher_id)

        # Header
        console.print()
        console.print(
            Panel(
                "[bold]Claw-ED Teaching Analytics[/bold]",
                border_style="blue",
            )
        )

        # Overview stats
        overview = Table(show_header=False, box=None, padding=(0, 2))
        overview.add_column("label", style="dim")
        overview.add_column("value", style="bold")
        overview.add_row("Total lessons", str(data["total_lessons"]))
        overview.add_row("Rated lessons", str(data["rated_lessons"]))
        overview.add_row("Total units", str(data["total_units"]))
        avg = data["overall_avg_rating"]
        stars = ("*" * round(avg) + " " * (5 - round(avg))) if avg else "No ratings yet"
        overview.add_row(
            "Average rating",
            f"{stars} ({avg}/5)" if avg else stars,
        )
        overview.add_row(
            "Usage streak",
            f"{data['streak']} day{'s' if data['streak'] != 1 else ''}",
        )
        console.print(
            Panel(
                overview,
                title="[blue]Overview[/blue]",
                border_style="blue",
            )
        )

        # Rating distribution
        dist = data["rating_distribution"]
        if any(dist.values()):
            dist_table = Table(show_header=True, title="Rating Distribution")
            dist_table.add_column("Stars", style="yellow")
            dist_table.add_column("Count", justify="right")
            dist_table.add_column("Bar")
            max_count = max(dist.values()) or 1
            for star in range(5, 0, -1):
                count = dist.get(star, 0)
                bar_len = int((count / max_count) * 20) if max_count else 0
                bar = "#" * bar_len
                dist_table.add_row(
                    f"{'*' * star}",
                    str(count),
                    f"[green]{bar}[/green]",
                )
            console.print(dist_table)

        # Ratings by subject
        by_subject = data["by_subject"]
        if by_subject:
            subj_table = Table(show_header=True, title="Ratings by Subject")
            subj_table.add_column("Subject")
            subj_table.add_column("Avg Rating", justify="right")
            for subj, avg_r in sorted(by_subject.items(), key=lambda x: x[1], reverse=True):
                color = "green" if avg_r >= 4 else "yellow" if avg_r >= 3 else "red"
                subj_table.add_row(subj, f"[{color}]{avg_r}/5[/{color}]")
            console.print(subj_table)

        # Top topics
        top = data["top_topics"]
        if top:
            top_table = Table(show_header=True, title="Most Effective Topics")
            top_table.add_column("Topic")
            top_table.add_column("Avg Rating", justify="right")
            top_table.add_column("Lessons", justify="right")
            for t in top:
                color = "green" if t["avg_rating"] >= 4 else "yellow" if t["avg_rating"] >= 3 else "red"
                top_table.add_row(
                    t["topic"],
                    f"[{color}]{t['avg_rating']}/5[/{color}]",
                    str(t["count"]),
                )
            console.print(top_table)

        # Needs improvement
        needs = data["needs_improvement"]
        if needs:
            needs_table = Table(
                show_header=True,
                title="[red]Needs Improvement[/red]",
            )
            needs_table.add_column("Lesson")
            needs_table.add_column("Rating", justify="right")
            needs_table.add_column("Date")
            for n in needs[:10]:
                needs_table.add_row(
                    n["title"] or "Untitled",
                    f"[red]{n['rating']}/5[/red]",
                    (n.get("created_at") or "")[:10],
                )
            console.print(needs_table)

        if not data["rated_lessons"]:
            console.print(
                "\n[dim]No ratings yet. Generate a lesson with 'clawed chat' and rate it to see analytics here.[/dim]"
            )
        console.print()


# ── Status command ───────────────────────────────────────────────────


def register_status(app: typer.Typer) -> None:
    """Register the status command on the main app."""

    @app.command()
    def status():
        """Quick one-line status check (no TUI, for scripts)."""
        cfg = AppConfig.load()
        profile = cfg.teacher_profile
        name = profile.name or "Teacher"
        provider = cfg.provider.value
        model_map = {
            "anthropic": cfg.anthropic_model,
            "openai": cfg.openai_model,
            "ollama": cfg.ollama_model,
            "google": cfg.google_model,
            "openrouter": cfg.openrouter_model,
        }
        model = model_map.get(provider, cfg.openai_model)

        has_token = bool(cfg.telegram_bot_token)
        tg_status = "[green]configured[/green]" if has_token else "[dim]not set[/dim]"

        console.print(
            f"[bold]{name}[/bold] | Model: {model} ({provider}) | Telegram: {tg_status} | Output: {cfg.output_dir}"
        )


# ── Import split modules so their decorators register commands ───────
# These imports MUST come after the app definitions above to avoid
# circular import errors (the split modules import the apps from here).

import clawed.commands.config_llm  # noqa: E402, F401
import clawed.commands.config_profile  # noqa: E402, F401
