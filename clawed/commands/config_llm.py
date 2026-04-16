"""LLM and API key config commands — registered on config_app."""

from __future__ import annotations

import typer
from rich.panel import Panel

from clawed._json_output import run_json_command
from clawed.commands._helpers import console
from clawed.commands.config import config_app
from clawed.models import AppConfig, LLMProvider


@config_app.command("set-model")
def config_set_model(
    provider: str = typer.Argument(
        ..., help="LLM provider: anthropic, openai, ollama, google, or openrouter"
    ),
    model: str | None = typer.Option(
        None, "--model", "-m", help="Model name override"
    ),
):
    """Configure the LLM backend."""
    try:
        llm_provider = LLMProvider(provider.lower())
    except ValueError as e:
        console.print(
            f"[red]Unknown provider: {provider}[/red]."
            " Use: anthropic, openai, ollama, google, openrouter"
        )
        raise typer.Exit(1) from e

    cfg = AppConfig.load()
    cfg.provider = llm_provider

    if model:
        if llm_provider == LLMProvider.ANTHROPIC:
            cfg.anthropic_model = model
        elif llm_provider == LLMProvider.OPENAI:
            cfg.openai_model = model
        elif llm_provider == LLMProvider.OLLAMA:
            cfg.ollama_model = model

    cfg.save()
    model_name = model or {
        LLMProvider.ANTHROPIC: cfg.anthropic_model,
        LLMProvider.OPENAI: cfg.openai_model,
        LLMProvider.OLLAMA: cfg.ollama_model,
    }[llm_provider]

    console.print(
        Panel(
            f"[bold]Provider:[/bold] {llm_provider.value}\n"
            f"[bold]Model:[/bold] {model_name}",
            title="Configuration Updated",
        )
    )

    # Ping the provider to verify connectivity
    import json

    import httpx as _httpx

    if llm_provider == LLMProvider.OLLAMA:
        from clawed.config import get_api_key, is_ollama_cloud, set_api_key

        base = cfg.ollama_base_url.rstrip("/")
        if is_ollama_cloud(base):
            # Cloud: validate credentials instead of pinging /api/version
            api_key = get_api_key("ollama") or cfg.ollama_api_key
            if not api_key:
                from rich.prompt import Prompt

                key = Prompt.ask(
                    "[yellow]No API key found for Ollama Cloud.[/yellow]\n"
                    "  Enter your Ollama Cloud API key (from https://ollama.com > Settings > API Keys)"
                )
                if key and key.strip():
                    set_api_key("ollama", key.strip())
                    console.print("[green]API key saved.[/green]")
                else:
                    console.print(
                        "[yellow]Warning: No API key for Ollama Cloud. "
                        "Run: clawed config set-key ollama YOUR_KEY[/yellow]"
                    )
            else:
                console.print(f"[green]Ollama Cloud configured at {base}[/green]")
        else:
            # Local: ping /api/version
            try:
                resp = _httpx.get(f"{base}/api/version", timeout=5)
                version = resp.json().get("version", "unknown")
                console.print(f"[green]Connected to Ollama v{version}[/green]")
            except (json.JSONDecodeError, KeyError):
                console.print(
                    "[yellow]Warning: Can't reach Ollama at "
                    f"{cfg.ollama_base_url}. Is it running?[/yellow]"
                )
    elif llm_provider == LLMProvider.ANTHROPIC:
        from clawed.config import get_api_key

        key = get_api_key("anthropic")
        if key:
            if key.startswith("sk-ant-oat"):
                console.print("[green]Claude Code OAuth token detected.[/green]")
            elif key.startswith("sk-"):
                console.print("[green]API key format looks valid.[/green]")
            else:
                console.print("[green]Credentials found.[/green]")
        else:
            console.print(
                "[yellow]Warning: No Anthropic credentials found. "
                "Set ANTHROPIC_API_KEY or log in to Claude Code.[/yellow]"
            )
    elif llm_provider == LLMProvider.OPENAI:
        from clawed.config import get_api_key as _get_key
        key = _get_key("openai")
        if key and key.startswith("sk-"):
            console.print("[green]API key format looks valid.[/green]")
        elif key:
            console.print("[green]Credentials found.[/green]")
        else:
            console.print(
                "[yellow]Warning: No OpenAI API key found. "
                "Set OPENAI_API_KEY or run: clawed config set-key openai YOUR_KEY[/yellow]"
            )


@config_app.command("set-token")
def config_set_token(
    token: str = typer.Argument(
        ..., help="Telegram bot token from @BotFather"
    ),
):
    """Save your Telegram bot token so you don't need to pass it every time.

    After saving, just run:

        clawed bot

    No --token flag needed.
    """
    cfg = AppConfig.load()
    cfg.telegram_bot_token = token
    cfg.save()
    masked = (
        token[:5] + "..." + token[-4:] if len(token) > 12 else "***"
    )
    console.print(
        Panel(
            f"[bold green]Token saved![/bold green]\n\n"
            f"Token: {masked}\n\n"
            f"You can now start the bot with just:\n"
            f"  [cyan]clawed bot[/cyan]",
            title="Telegram Bot Token",
        )
    )


@config_app.command("set-search-key")
def config_set_search_key(
    key: str = typer.Argument(..., help="Web search API key"),
    provider: str = typer.Option(
        "brave", help="Search provider: brave, duckduckgo, or tavily"
    ),
):
    """Set a web search API key for research-powered lessons.

    Free options: Brave Search (1000 queries/month free), DuckDuckGo (no key needed).
    """
    from clawed.config import set_api_key

    set_api_key(f"search_{provider}", key)
    console.print(f"[green]\u2713 {provider.title()} search key saved.[/green]")


def _config_show_json():
    """Return config data for JSON output."""
    cfg = AppConfig.load()
    return {
        "data": cfg.model_dump() if hasattr(cfg, "model_dump") else cfg.dict(),
        "files": [],
    }


@config_app.command("show")
def config_show(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Show current configuration."""
    if json_output:
        run_json_command("config.show", _config_show_json)
        return

    from clawed.config import get_api_key

    cfg = AppConfig.load()
    token_display = "Not set"
    if cfg.telegram_bot_token:
        t = cfg.telegram_bot_token
        token_display = t[:5] + "..." + t[-4:] if len(t) > 12 else "***"
    search_key = get_api_key("search_brave") or get_api_key("search_tavily")
    search_display = "Not set"
    if search_key:
        search_display = (
            search_key[:5] + "..." + search_key[-4:]
            if len(search_key) > 12
            else "***"
        )
    console.print(
        Panel(
            f"[bold]Provider:[/bold] {cfg.provider.value}\n"
            f"[bold]Anthropic Model:[/bold] {cfg.anthropic_model}\n"
            f"[bold]OpenAI Model:[/bold] {cfg.openai_model}\n"
            f"[bold]Ollama Model:[/bold] {cfg.ollama_model}\n"
            f"[bold]Google Model:[/bold] {cfg.google_model}\n"
            f"[bold]OpenRouter Model:[/bold] {cfg.openrouter_model}\n"
            f"[bold]Ollama URL:[/bold] {cfg.ollama_base_url}\n"
            f"[bold]Output Dir:[/bold] {cfg.output_dir}\n"
            f"[bold]Export Format:[/bold] {cfg.export_format}\n"
            f"[bold]Include Homework:[/bold] {cfg.include_homework}\n"
            f"[bold]Telegram Token:[/bold] {token_display}\n"
            f"[bold]Web Search Key:[/bold] {search_display}",
            title="Claw-ED Configuration",
        )
    )
