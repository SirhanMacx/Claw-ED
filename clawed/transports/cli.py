"""Terminal chat interface — test Claw-ED from the command line."""

from __future__ import annotations

import asyncio
import logging

from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.spinner import Spinner

from clawed.commands._helpers import console
from clawed.gateway import Gateway
from clawed.state import TeacherSession

logger = logging.getLogger(__name__)

_WELCOME = """\
**Welcome back to Claw-ED!** Ready to plan some great lessons.

**Quick ideas:**
- *"plan a unit on photosynthesis for 8th grade, 2 weeks"*
- *"make a vocabulary worksheet for chapter 5"*
- *"use my files at ~/Documents/Lessons/"*

**Commands:** `/quit` to exit | `/status` for session info | `/clear` to reset
"""

_WELCOME_NEW = """\
**Welcome to Claw-ED** -- your AI co-teacher.

Your AI connection is ready. I'll introduce myself in a moment.

**Commands:** `/quit` to exit | `/status` for session info | `/clear` to reset
"""


async def run_chat(teacher_id: str = "local-teacher") -> None:
    """Run an interactive terminal chat session with Claw-ED."""
    gateway = Gateway()
    session = TeacherSession.load(teacher_id)

    if session.is_new:
        # New user: show a brief banner, then let the agent introduce itself
        console.print(
            Panel(
                Markdown(_WELCOME_NEW),
                title="[bold green]Claw-ED Chat[/bold green]",
                border_style="green",
                padding=(1, 2),
            )
        )
        # Auto-trigger the agent's onboarding greeting
        with Live(
            Spinner("dots", text="[dim]Getting ready...[/dim]", style="green"),
            console=console,
            transient=True,
        ):
            try:
                result = await gateway.handle("hello", teacher_id)
            except Exception:
                logger.debug("operation_failed", exc_info=True)
                result = None

        if result and result.text and "provider key" not in result.text.lower():
            response_text = result.text
        else:
            # LLM failed or returned an error — show a friendly offline greeting
            response_text = (
                "Hi there! I'm Claw-ED, your AI co-teacher.\n\n"
                "I can help you create lesson plans, handouts, slides, and "
                "assessments -- all tailored to your standards and style.\n\n"
                "It looks like the AI connection isn't working yet. "
                "Exit chat (`/quit`) and run:\n"
                "  `clawed setup --reset`\n\n"
                "Or see example output first with:\n"
                "  `clawed demo`"
            )

        console.print()
        console.print(
            Panel(
                response_text,
                title="[bold green]Claw-ED[/bold green]",
                border_style="green",
                padding=(0, 1),
            )
        )
        console.print()
    else:
        # Returning user: show the welcome banner with their name
        name = session.persona.name if session.persona else teacher_id
        console.print(
            Panel(
                Markdown(_WELCOME),
                title=f"[bold green]Claw-ED Chat -- {name}[/bold green]",
                border_style="green",
                padding=(1, 2),
            )
        )

    while True:
        try:
            message = Prompt.ask("[bold blue]You[/bold blue]")
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Goodbye![/dim]")
            break

        text = message.strip()
        if not text:
            continue

        # Built-in commands
        if text.lower() in ("/quit", "/exit", "quit", "exit"):
            console.print("[dim]Goodbye![/dim]")
            break

        if text.lower() == "/clear":
            session = TeacherSession(teacher_id=teacher_id)
            session.save()
            console.print("[yellow]Session cleared.[/yellow]\n")
            continue

        if text.lower() == "/status":
            text = "show status"

        # Catch common mistakes — teacher typing terminal commands inside chat
        if text.lower().startswith("clawed "):
            console.print(
                "[yellow]That's a terminal command — type it in PowerShell/Terminal, not here.[/yellow]\n"
                f"[dim]Exit chat first (/quit), then run: {text}[/dim]\n"
            )
            continue

        if text.lower() in ("/setup", "setup", "setup --reset"):
            console.print(
                "[yellow]To reconfigure, exit chat first (/quit), then run:[/yellow]\n"
                "[dim]  clawed setup --reset[/dim]\n"
            )
            continue

        # Show spinner while generating
        with Live(
            Spinner("dots", text="[dim]Thinking...[/dim]", style="green"),
            console=console,
            transient=True,
        ):
            try:
                result = await gateway.handle(text, teacher_id)
            except Exception as e:
                result = None
                response_text = f"Error: {e}"
            else:
                response_text = result.text

        console.print()
        console.print(
            Panel(
                response_text,
                title="[bold green]Claw-ED[/bold green]",
                border_style="green",
                padding=(0, 1),
            )
        )
        console.print()

        # Send any files the gateway produced
        if result and result.files:
            for f in result.files:
                console.print(f"[green]File: {f}[/green]")
            console.print()

        # Show buttons as text options in CLI
        if result and (result.button_rows or result.buttons):
            rows = result.button_rows or [result.buttons]
            options = [b.label for row in rows for b in row]
            console.print(f"[dim]Options: {' | '.join(options)}[/dim]\n")


def main(teacher_id: str = "local-teacher") -> None:
    """Synchronous entry point for the chat REPL."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        loop.run_until_complete(run_chat(teacher_id))
    except RuntimeError:
        asyncio.run(run_chat(teacher_id))
