"""Rich CLI for Claw-ED — beautiful terminal interface with typer.

This module registers all CLI sub-apps from clawed.commands.* modules.
The actual command implementations live in:
  - commands/generate.py  — ingest, unit, lesson, materials, full, etc.
  - commands/config.py    — config, persona, standards, templates, skills, school, waitlist
  - commands/export.py    — export, share, demo, landing
  - commands/bot.py       — chat, student-chat, bot, serve, mcp-server
"""

from __future__ import annotations

from typing import Any

import typer

from clawed import __version__
from clawed.commands._helpers import console

# UTF-8 encoding is enforced in clawed/__init__.py for all entry points
from clawed.commands.bot import bot_app
from clawed.commands.brain_cmd import brain_app
from clawed.commands.config import (
    class_app,
    config_app,
    persona_app,
    register_stats,
    register_status,
    school_app,
    skills_app,
    standards_app,
    templates_app,
)
from clawed.commands.drive import drive_app
from clawed.commands.export import (
    _DEMO_HTML,
    _lesson_to_html,
    export_app,
)
from clawed.commands.game import game_app
from clawed.commands.generate import generate_app
from clawed.commands.kb import kb_app
from clawed.commands.queue import queue_app
from clawed.commands.schedule_cmd import schedule_app
from clawed.commands.simulation import simulation_app
from clawed.commands.sub import sub_app
from clawed.commands.train import train_app
from clawed.commands.workspace_cmd import workspace_app

# ── Build the main app ──────────────────────────────────────────────────

app = typer.Typer(
    name="clawed",
    help="Your teaching files, your AI co-teacher.",
    rich_markup_mode="rich",
)


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"Claw-ED v{__version__}")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool | None = typer.Option(
        None,
        "--version",
        "-V",
        help="Show version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    """Your teaching files, your AI co-teacher."""
    if ctx.invoked_subcommand is None:
        from clawed.config import get_api_key, has_config
        from clawed.models import AppConfig

        needs_setup = False
        if not has_config():
            needs_setup = True
        else:
            # Config exists — but is the API key actually valid?
            cfg = AppConfig.load()
            provider = cfg.provider.value
            key = get_api_key(provider)
            if not key and provider != "ollama":
                console.print(
                    f"[yellow]No API key found for {provider}.[/yellow]\n"
                    "Let's fix that.\n"
                )
                needs_setup = True

        interface = "terminal"  # default

        if needs_setup:
            from clawed.onboarding import quick_model_setup
            try:
                interface = quick_model_setup()
            except (KeyboardInterrupt, EOFError) as e:
                console.print("\n[dim]Setup cancelled. Run clawed again anytime.[/dim]")
                raise typer.Exit() from e

            if interface == "skip":
                raise typer.Exit()

        if interface == "telegram":
            # Launch the Telegram bot — teacher continues setup on their phone
            cfg = AppConfig.load()
            token = cfg.telegram_bot_token
            if token:
                try:
                    from clawed.transports.telegram import run_bot
                    run_bot(token=token)
                except KeyboardInterrupt:
                    console.print("\n[yellow]Bot stopped.[/yellow]")
                except Exception as exc:
                    console.print(f"\n[red]Bot error:[/red] {exc}")
                    console.print("[dim]Check your bot token and try again.[/dim]")
            raise typer.Exit()

        # Terminal chat — agent handles onboarding conversationally
        import asyncio

        from clawed.transports.cli import run_chat
        try:
            asyncio.run(run_chat())
        except (KeyboardInterrupt, EOFError):
            pass
        except Exception as exc:
            err = str(exc).lower()
            if "api key" in err or "unauthorized" in err or "401" in err:
                console.print("\n[red]Your AI provider key doesn't seem to be working.[/red]")
                console.print("[dim]Run 'clawed setup --reset' to reconfigure your API key.[/dim]")
            elif "connection" in err or "connect" in err or "timeout" in err:
                console.print("\n[red]Can't connect to your AI provider.[/red]")
                console.print("[dim]Check your internet connection and try again.[/dim]")
            else:
                console.print(f"\n[red]Something went wrong:[/red] {exc}")
                console.print("[dim]Run 'clawed setup --reset' to reconfigure, or 'clawed --help' for commands.[/dim]")
        raise typer.Exit()


# ── Top-level setup command ────────────────────────────────────────────


@app.command()
def setup(
    reset: bool = typer.Option(False, "--reset", help="Reset existing config and start fresh"),
) -> None:
    """Set up Claw-ED — pick your AI provider and get started.

    \b
    Run this to:
      1. Choose your AI provider (Ollama Cloud, Claude, GPT)
      2. Paste your API key
      3. Optionally connect a Telegram bot

    Run with --reset to start fresh.
    """
    if reset:
        from clawed.onboarding import _clear_config
        _clear_config()

    from clawed.onboarding import quick_model_setup
    quick_model_setup()


@app.command()
def debug() -> None:
    """Show diagnostic info — config, API key status, connection test."""
    import asyncio
    import json

    from clawed.config import _SECRETS_FILE, get_api_key
    from clawed.models import AppConfig

    cfg = AppConfig.load()
    config_path = AppConfig.config_path()

    console.print("[bold]Claw-ED Debug Info[/bold]\n")
    console.print(f"  Version: {__version__}")
    console.print(f"  Config path: {config_path}")
    console.print(f"  Config exists: {config_path.exists()}")
    console.print(f"  Secrets path: {_SECRETS_FILE}")
    console.print(f"  Secrets exists: {_SECRETS_FILE.exists()}")

    if _SECRETS_FILE.exists():
        try:
            secrets = json.loads(_SECRETS_FILE.read_text(encoding="utf-8"))
            console.print(f"  Secrets keys: {list(secrets.keys())}")
        except Exception as e:
            console.print(f"  Secrets read error: {e}")

    provider = cfg.provider.value
    model_map = {
        "anthropic": cfg.anthropic_model,
        "openai": cfg.openai_model,
        "google": cfg.google_model,
        "ollama": cfg.ollama_model,
        "openrouter": cfg.openrouter_model,
    }
    active_model = model_map.get(provider, "unknown")
    console.print(f"\n  Provider: {provider}")
    console.print(f"  Model: {active_model}")
    if provider == "ollama":
        console.print(f"  Base URL: {cfg.ollama_base_url}")
    console.print(f"  Agent gateway: {cfg.agent_gateway}")

    # API key status for the active provider
    key = get_api_key(provider)
    if key:
        masked = key[:8] + "..." + key[-4:] if len(key) > 16 else "***"
        console.print(f"\n  {provider} key: {masked}")
    else:
        console.print(f"\n  {provider} key: [red]NONE[/red]")

    # Telegram
    console.print(f"\n  Telegram token: {cfg.telegram_bot_token[:12] + '...' if cfg.telegram_bot_token else 'NONE'}")

    # Connection test
    console.print("\n  [dim]Testing connection...[/dim]")
    try:
        from clawed.config import test_llm_connection
        result = asyncio.run(test_llm_connection(cfg))
        if result["connected"]:
            console.print(f"  [green]Connected: {result.get('message', 'OK')}[/green]")
        else:
            console.print(f"  [red]Failed: {result.get('error', 'unknown')}[/red]")
    except Exception as e:
        console.print(f"  [red]Connection test error: {e}[/red]")

    # Quick LLM test
    console.print("\n  [dim]Testing LLM call...[/dim]")
    try:
        from clawed.gateway import Gateway
        # Gateway() is a factory; typed Any because the concrete gateway class
        # is resolved at runtime via config.
        gw: Any = Gateway(config=cfg)
        llm_result: Any = asyncio.run(gw.handle("say hello in one word", "debug-test"))
        if "went wrong" in llm_result.text.lower() or "provider key" in llm_result.text.lower():
            console.print(f"  [red]LLM test failed: {llm_result.text}[/red]")
        else:
            console.print(f"  [green]LLM test passed: {llm_result.text[:80]}[/green]")
    except Exception as e:
        console.print(f"  [red]LLM test error: {e}[/red]")


# ── Register named sub-app groups ───────────────────────────────────────

app.add_typer(config_app, name="config")
app.add_typer(persona_app, name="persona")
app.add_typer(standards_app, name="standards")
app.add_typer(templates_app, name="templates")
app.add_typer(skills_app, name="skills")
app.add_typer(school_app, name="school")
app.add_typer(class_app, name="class")
app.add_typer(queue_app, name="queue")
app.add_typer(workspace_app, name="workspace")
app.add_typer(kb_app, name="kb")
app.add_typer(schedule_app, name="schedule")
app.add_typer(train_app, name="train")
app.add_typer(game_app, name="game")
app.add_typer(simulation_app, name="simulate")
app.add_typer(drive_app, name="drive")
app.add_typer(brain_app, name="brain")

# ── Register top-level commands from sub-modules ────────────────────────
# Commands from generate_app, export_app, and bot_app are registered as
# top-level commands on the main app (e.g. `clawed ingest`, not
# `clawed generate ingest`).

for _cmd_info in generate_app.registered_commands:
    app.registered_commands.append(_cmd_info)

for _cmd_info in export_app.registered_commands:
    app.registered_commands.append(_cmd_info)

for _cmd_info in bot_app.registered_commands:
    app.registered_commands.append(_cmd_info)

for _cmd_info in sub_app.registered_commands:
    app.registered_commands.append(_cmd_info)

# Register stats and status as top-level commands via helper functions
register_stats(app)
register_status(app)

# ── Backward compatibility ──────────────────────────────────────────────
# Tests and other modules import these directly from clawed.cli
__all__ = ["_DEMO_HTML", "_lesson_to_html", "app"]

if __name__ == "__main__":
    app()
