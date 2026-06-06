"""Bot, serve, MCP server, chat, and student-chat commands."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from rich.panel import Panel

from clawed.commands._helpers import _safe_progress, console
from clawed.commands._helpers import run_async as _run_async
from clawed.models import AppConfig, LLMProvider

bot_app = typer.Typer()


# ── TUI Chat command ────────────────────────────────────────────────────


@bot_app.command()
def tui(
    teacher_id: str = typer.Option(
        "local-teacher", "--id", help="Teacher session ID"
    ),
    port: int = typer.Option(
        8000, "--port", "-p", help="Gateway server port"
    ),
    host: str = typer.Option(
        "127.0.0.1", "--host", "-h", help="Gateway server host"
    ),
) -> None:
    """Start the full-screen TUI chat — connects to a running gateway.

    \b
    A rich terminal interface for chatting with Claw-ED. Connects to a
    running `clawed serve` instance over HTTP. Start the server first:

        clawed serve &          # start gateway in background
        clawed tui              # connect the TUI

    Install TUI support: pip install 'clawed[tui]'
    """
    from clawed.onboarding import check_first_run

    check_first_run()

    try:
        from clawed.tui_chat import run_tui_chat
    except ImportError as e:
        console.print(f"[red]Missing dependency:[/red] {e}")
        console.print("\nInstall TUI support with:")
        console.print("  pip install 'clawed\\[tui]'", highlight=False)
        raise typer.Exit(1) from e

    run_tui_chat(teacher_id, host=host, port=port)


# ── Chat command ─────────────────────────────────────────────────────────


@bot_app.command()
def chat(
    teacher_id: str = typer.Option(
        "local-teacher", "--id", help="Teacher session ID"
    ),
) -> None:
    """Start an interactive chat session with Claw-ED in the terminal."""
    from clawed.onboarding import check_first_run

    check_first_run()

    from clawed.cli_chat import main as chat_main

    chat_main(teacher_id)


# ── Student chat command ─────────────────────────────────────────────────


@bot_app.command(name="student-chat")
def student_chat(
    class_code: str = typer.Option(
        ..., "--class-code", help="Class code from your teacher"
    ),
    student_id: str = typer.Option(
        "student-001", "--student-id", help="Your student ID"
    ),
) -> None:
    """Start a student chat session — ask questions about today's lesson."""
    from rich.live import Live
    from rich.prompt import Prompt
    from rich.spinner import Spinner

    from clawed.student_bot import StudentBot

    bot = StudentBot()
    class_info = bot.get_class(class_code)
    if not class_info:
        console.print(
            f"[red]Class code '{class_code}' not found.[/red]"
            " Check with your teacher."
        )
        raise typer.Exit(1)

    if not class_info.active_lesson_json:
        console.print(
            "[yellow]Your teacher hasn't activated a lesson yet."
            " Check back soon![/yellow]"
        )
        raise typer.Exit(1)

    import json as _json

    lesson_data = _json.loads(class_info.active_lesson_json)
    lesson_title = lesson_data.get("title", "Today's Lesson")

    console.print(
        Panel(
            f"*{lesson_title}*\n\n"
            f"Ask me anything about today's lesson!\n"
            f"Type '/quit' to exit.\n",
            title=(
                f"[bold green]Student Chat"
                f" — {class_code}[/bold green]"
            ),
            border_style="green",
            padding=(1, 2),
        )
    )

    while True:
        try:
            message = Prompt.ask("[bold cyan]You[/bold cyan]")
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Goodbye![/dim]")
            break

        text = message.strip()
        if not text:
            continue
        if text.lower() in ("/quit", "/exit", "quit", "exit"):
            console.print("[dim]Goodbye![/dim]")
            break

        with Live(
            Spinner(
                "dots",
                text="[dim]Thinking...[/dim]",
                style="green",
            ),
            console=console,
            transient=True,
        ):
            try:
                response = _run_async(
                    bot.handle_message(text, student_id, class_code)
                )
            except Exception as e:
                response = f"Oops, something went wrong: {e}"

        console.print()
        console.print(
            Panel(
                response,
                title="[bold green]Teacher[/bold green]",
                border_style="green",
                padding=(0, 1),
            )
        )
        console.print()


# ── MCP Server command ──────────────────────────────────────────────────


@bot_app.command(name="mcp-server")
def mcp_server() -> None:
    """Start the Claw-ED MCP server for tool integration.

    Uses stdio transport (the standard MCP transport). Connect to this
    server by launching the process and communicating over stdin/stdout.
    """
    from clawed.mcp_server import run_server

    console.print(
        Panel(
            "Starting MCP server (stdio transport)\n"
            "Tools: generate_lesson, generate_unit,"
            " ingest_materials, student_question,"
            " get_teacher_standards",
            title="[bold blue]Claw-ED MCP Server[/bold blue]",
            border_style="blue",
        )
    )
    run_server()


# ── First-run setup ──────────────────────────────────────────────────


def _first_run_setup() -> None:
    """Interactive first-run setup wizard. Only runs when no config exists."""
    from rich.prompt import Prompt

    from clawed.config import has_config, set_api_key, test_llm_connection

    if has_config():
        return

    console.print(
        Panel(
            "[bold]Welcome to Claw-ED![/bold]\n\n"
            "Let's get you set up in 2 minutes.",
            title="Setup",
            border_style="blue",
        )
    )

    # Provider selection
    provider_choice = Prompt.ask(
        "Which AI provider do you want to use?",
        choices=["ollama", "anthropic", "openai"],
        default="ollama",
    )

    cfg = AppConfig()
    cfg.provider = LLMProvider(provider_choice)

    # API key for cloud providers
    if provider_choice in ("anthropic", "openai"):
        api_key = Prompt.ask(
            f"Enter your {provider_choice.title()} API key",
            password=True,
        )
        if api_key.strip():
            set_api_key(provider_choice, api_key.strip())
            console.print("[green]API key saved securely.[/green]")

    # Test connection
    with _safe_progress(console=console) as progress:
        task = progress.add_task("Testing connection...", total=None)
        result = _run_async(test_llm_connection(cfg))
        progress.update(task, description="Done!")

    model = result.get("model", "")
    if result.get("connected"):
        console.print(f"[green]Connected to {model}[/green]")
    else:
        console.print(
            f"[yellow]Could not connect:"
            f" {result.get('error', 'unknown')}[/yellow]"
        )
        console.print(
            "[dim]You can update settings later at"
            " http://localhost:8000/settings[/dim]"
        )

    # Subject and grades
    subject = Prompt.ask("What subject do you teach?", default="Science")
    grades = Prompt.ask("What grade(s)?", default="8")

    cfg.save()

    console.print("\n[green]Configuration saved![/green]")
    console.print(
        f"[dim]Subject: {subject}, Grades: {grades}[/dim]\n"
    )


# ── Serve command ──────────────────────────────────────────────────────


@bot_app.command()
def serve(
    port: int = typer.Option(
        8000, "--port", "-p", help="Port to listen on"
    ),
    host: str = typer.Option(
        "127.0.0.1", "--host", "-h", help="Host to bind to"
    ),
    token: str | None = typer.Option(
        None,
        "--token",
        "-t",
        envvar="TELEGRAM_BOT_TOKEN",
        help="Telegram bot token",
    ),
    tui: bool = typer.Option(
        False, "--tui", help="Launch the live TUI dashboard"
    ),
    skip_setup: bool = typer.Option(
        False, "--skip-setup", help="Skip first-run setup wizard"
    ),
    reload: bool = typer.Option(
        False, "--reload", help="Enable auto-reload for development"
    ),
) -> None:
    """Start the Claw-ED server.

    \b
    Modes:
      clawed serve --token TOKEN --tui   # Full TUI + gateway + web
      clawed serve --token TOKEN         # Gateway + web (no TUI, for VPS)
      clawed serve --tui                 # TUI only (no Telegram, demos)
      clawed serve                       # Web server only
    """
    # Warn about non-localhost exposure
    if host not in ("127.0.0.1", "localhost", "::1"):
        console.print(
            f"[bold yellow]WARNING:[/bold yellow] Binding to [bold]{host}[/bold]. "
            "The web API has basic auth but is designed for localhost use. "
            "Use a reverse proxy (nginx, caddy) for production exposure."
        )

    # Print auth token for API access
    from clawed.api.deps import get_api_token
    api_token = get_api_token()
    console.print(f"API token: [bold]{api_token}[/bold]")

    cfg = AppConfig.load()

    # Warn if no AI provider is configured
    from clawed.config import get_api_key, has_config
    if not has_config():
        console.print(
            "[yellow]No configuration found.[/yellow] Run [bold]clawed setup[/bold] first,\n"
            "or open [cyan]http://localhost:8000/setup[/cyan] after the server starts."
        )
    elif not get_api_key(cfg.provider.value) and cfg.provider.value != "ollama":
        console.print(
            f"[yellow]No API key found for {cfg.provider.value}.[/yellow]\n"
            "Open [cyan]http://localhost:8000/settings[/cyan] to configure, "
            "or run [bold]clawed setup --reset[/bold]."
        )

    # Resolve token from saved config if not provided
    if not token:
        token = cfg.telegram_bot_token

    if tui:
        _serve_with_tui(
            token=token or None, host=host, port=port, config=cfg
        )
    elif token:
        _serve_gateway_headless(
            token=token, host=host, port=port, config=cfg
        )
    else:
        import uvicorn

        console.print(
            Panel(
                f"[bold]Starting Claw-ED web server[/bold]\n"
                f"[cyan]http://{host}:{port}[/cyan]\n"
                f"Dashboard:"
                f" [cyan]http://{host}:{port}/dashboard[/cyan]\n"
                f"Generate:"
                f" [cyan]http://{host}:{port}/generate[/cyan]\n"
                f"Settings:"
                f" [cyan]http://{host}:{port}/settings[/cyan]",
                title="Claw-ED Server",
                border_style="green",
            )
        )
        if cfg.agent_gateway:
            try:
                from clawed.scheduler import EduScheduler

                edu_scheduler = EduScheduler()
                edu_scheduler.register_jobs()
                edu_scheduler.start()
                console.print("[dim]Proactive scheduler started[/dim]")
            except Exception as e:
                console.print(
                    f"[dim]Scheduler not started: {e}[/dim]"
                )
        uvicorn.run(
            "clawed.api.server:app",
            host=host,
            port=port,
            reload=reload,
        )


@bot_app.command(name="app")
def app_launcher(
    port: int = typer.Option(
        8000, "--port", "-p", help="Port to listen on"
    ),
    no_open: bool = typer.Option(
        False, "--no-open", help="Don't open the browser automatically"
    ),
) -> None:
    """Launch the Claw-ED app — opens the local web experience in your browser.

    The friendly, no-terminal way to use Claw-ED. Starts the server bound to
    your own computer (127.0.0.1), trusts localhost so you skip the token
    prompt, and opens the app in your default browser. Nothing is exposed to
    the network. First-time users land on the API-key setup page.
    """
    import os as _os
    import threading
    import webbrowser

    import uvicorn

    # Trust same-machine requests so a teacher never hits a token wall.
    # Safe: the server only binds to 127.0.0.1 (this computer).
    _os.environ["EDUAGENT_LOCAL_AUTH_BYPASS"] = "1"

    cfg = AppConfig.load()
    from clawed.config import get_api_key, has_config

    needs_key = (not has_config()) or (
        cfg.provider.value != "ollama"
        and not get_api_key(cfg.provider.value)
    )
    landing = "/settings" if needs_key else "/"
    url = f"http://127.0.0.1:{port}{landing}"

    intro = (
        "[yellow]First time?[/yellow] Add your API key on the Settings page"
        " — there are step-by-step instructions right there.\n\n"
        if needs_key
        else ""
    )
    console.print(
        Panel(
            f"[bold]Claw-ED is starting[/bold]\n"
            f"Opening [cyan]{url}[/cyan] in your browser…\n\n"
            f"{intro}"
            "[dim]Runs only on this computer. Press Ctrl+C to stop.[/dim]",
            title="Claw-ED",
            border_style="green",
        )
    )

    if not no_open:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()

    uvicorn.run("clawed.api.server:app", host="127.0.0.1", port=port)


def _serve_with_tui(
    token: str | None,
    host: str,
    port: int,
    config: AppConfig | None = None,
) -> None:
    """Launch the full TUI dashboard with gateway."""
    try:
        from clawed.gateway import EduAgentGateway
        from clawed.tui import EduAgentDashboard
    except ImportError as e:
        console.print(f"[red]Missing dependency:[/red] {e}")
        console.print("\nInstall TUI support with:")
        console.print("  pip install 'clawed\\[tui]'", highlight=False)
        raise typer.Exit(1) from e

    gateway = EduAgentGateway(config=config)

    async def _run() -> None:
        # Start the gateway (near-instant)
        await gateway.start()

        # Start web server in background
        import uvicorn

        uv_config = uvicorn.Config(
            "clawed.api.server:app",
            host=host,
            port=port,
            log_level="warning",
        )
        server = uvicorn.Server(uv_config)
        server_task = asyncio.create_task(server.serve())

        # TUI blocks until quit — this is the main blocking call
        dashboard = EduAgentDashboard(gateway=gateway)
        try:
            await dashboard.run_async()
        finally:
            server.should_exit = True
            await server_task
            await gateway.stop()

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        console.print("\n[yellow]Stopped.[/yellow]")


def _serve_gateway_headless(
    token: str,
    host: str,
    port: int,
    config: AppConfig | None = None,
) -> None:
    """Run gateway + web server without TUI (VPS mode)."""
    # Check for existing standalone bot instance
    import os

    from clawed.transports.telegram import _BOT_LOCK

    if _BOT_LOCK.exists():
        try:
            pid = int(_BOT_LOCK.read_text(encoding="utf-8").strip())
            if pid != os.getpid():
                try:
                    os.kill(pid, 0)
                    console.print(
                        f"[yellow]A standalone Telegram bot is already running (PID {pid}).[/yellow]\n"
                        "[yellow]Starting web server only. Stop the bot first if you want serve to manage it.[/yellow]"
                    )
                    # Fall back to web-only mode
                    import uvicorn

                    uvicorn.run("clawed.api.server:app", host=host, port=port)
                    return
                except (OSError, SystemError):
                    pass  # Process is dead, stale lock — proceed normally
        except (ValueError, OSError):
            pass  # Invalid lock file — proceed normally

    from clawed.gateway import EduAgentGateway

    gateway = EduAgentGateway(config=config)

    console.print(
        Panel(
            f"[bold green]Claw-ED Gateway[/bold green]\n\n"
            f"Telegram: connected\n"
            f"Web: [cyan]http://{host}:{port}[/cyan]\n\n"
            f"[dim]Press Ctrl+C to stop[/dim]",
            title="Claw-ED",
            border_style="green",
        )
    )

    async def _run() -> None:
        import uvicorn

        # Start the gateway (near-instant — sets _running and emits event)
        await gateway.start()

        # Start proactive scheduler if agent_gateway is enabled
        edu_scheduler = None
        if config and config.agent_gateway:
            try:
                from clawed.scheduler import EduScheduler

                edu_scheduler = EduScheduler()
                edu_scheduler.register_jobs()
                edu_scheduler.start()
                console.print("[dim]Proactive scheduler started[/dim]")
            except Exception as e:
                console.print(
                    f"[dim]Scheduler not started: {e}[/dim]"
                )

        # Run the web server — this blocks until shutdown
        uv_config = uvicorn.Config(
            "clawed.api.server:app",
            host=host,
            port=port,
            log_level="warning",
        )
        server = uvicorn.Server(uv_config)
        try:
            await server.serve()
        finally:
            if edu_scheduler:
                edu_scheduler.stop()
            await gateway.stop()

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        console.print("\n[yellow]Gateway stopped.[/yellow]")


# ── Student bot command ──────────────────────────────────────────────


@bot_app.command(name="student-bot")
def student_bot_cmd(
    token: str | None = typer.Option(
        None,
        "--token",
        "-t",
        envvar="STUDENT_BOT_TOKEN",
        help="Student bot token from @BotFather",
    ),
) -> None:
    """Run the student-facing Telegram bot (separate from the teacher bot)."""
    from clawed.transports.student_telegram import StudentTelegramBot

    if not token:
        console.print(
            "[red]Error: provide --token or set"
            " STUDENT_BOT_TOKEN[/red]"
        )
        raise typer.Exit(1)

    console.print("[green]Starting student bot...[/green]")
    try:
        StudentTelegramBot(token).start()
    except KeyboardInterrupt:
        console.print("\n[yellow]Student bot stopped.[/yellow]")
    except ImportError as e:
        console.print(f"[red]Missing dependency:[/red] {e}")
        console.print(
            "\nInstall Telegram support with:"
            "\n  [cyan]pip install"
            " 'python-telegram-bot>=20.0'[/cyan]"
        )
        raise typer.Exit(1) from e


# ── Bot command ──────────────────────────────────────────────────────


@bot_app.command()
def bot(
    token: str | None = typer.Option(
        None,
        "--token",
        "-t",
        envvar="TELEGRAM_BOT_TOKEN",
        help="Telegram bot token from @BotFather (or set TELEGRAM_BOT_TOKEN env var)",
    ),
    data_dir: str | None = typer.Option(
        None,
        "--data-dir",
        help="Data directory (default: ~/.eduagent)",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Force start even if another instance appears to be running",
    ),
    kill: bool = typer.Option(
        False,
        "--kill",
        help="Kill any existing bot process and exit",
    ),
) -> None:
    """Start the Claw-ED Telegram bot.

    \b
    Get a bot token from @BotFather on Telegram, then run:

        # Polling mode — works on any machine, no public URL needed:
        clawed bot --token YOUR_TOKEN
        export TELEGRAM_BOT_TOKEN=YOUR_TOKEN && clawed bot

    Save the token permanently (so you don't have to pass it every time):
        clawed config set-token YOUR_TOKEN
        clawed bot
    """
    # Handle --kill: find and kill any existing bot process, then exit
    if kill:
        from clawed.transports.telegram import kill_bot_process
        if kill_bot_process():
            console.print("[green]Killed existing bot process.[/green]")
        else:
            console.print("[dim]No running bot process found.[/dim]")
        raise typer.Exit(0)

    from clawed.onboarding import check_first_run

    check_first_run()

    # Resolve token: --token flag > TELEGRAM_BOT_TOKEN env > saved config
    if not token:
        cfg = AppConfig.load()
        token = cfg.telegram_bot_token
    if not token:
        console.print(
            "[red]No bot token found.[/red]\n\n"
            "Provide one of:\n"
            "  1. [cyan]clawed bot --token YOUR_TOKEN[/cyan]\n"
            "  2. [cyan]export"
            " TELEGRAM_BOT_TOKEN=YOUR_TOKEN[/cyan]\n"
            "  3. [cyan]clawed config set-token"
            " YOUR_TOKEN[/cyan]  (saves permanently)\n\n"
            "Get a token from @BotFather on Telegram."
        )
        raise typer.Exit(1)

    data_path = (
        Path(data_dir).expanduser().resolve() if data_dir else None
    )

    from clawed.paths import data_dir as _data_dir_fn
    from clawed.transports.telegram import run_bot as run_new_bot

    console.print(
        Panel(
            f"[bold green]Claw-ED Telegram Bot[/bold green]\n\n"
            f"Starting bot...\n"
            f"Data directory:"
            f" {data_path or _data_dir_fn()}\n"
            f"Mode: polling (httpx)\n\n"
            f"[dim]Press Ctrl+C to stop[/dim]",
            title="Claw-ED",
            border_style="green",
        )
    )

    try:
        run_new_bot(
            token=token,
            data_dir=data_path,
            force=force,
        )
    except RuntimeError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from e
    except KeyboardInterrupt:
        console.print("\n[yellow]Bot stopped.[/yellow]")
