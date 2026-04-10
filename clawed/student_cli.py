"""Standalone student-facing terminal for Claw-ED.

Usage:
    python -m clawed.student_cli --class-code MR-MAC-P3
    clawed student-chat --class-code MR-MAC-P3

Students type questions about today's lesson and get responses in their
teacher's voice. First-time students are auto-registered.
"""

from __future__ import annotations

import asyncio
import sys
from typing import Optional

from rich.live import Live
from rich.panel import Panel
from rich.prompt import Prompt
from rich.spinner import Spinner

from clawed.commands._helpers import console


def _run_async(coro):
    """Run an async coroutine from synchronous code."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


def main(
    class_code: str,
    student_id: str = "student-001",
    student_name: Optional[str] = None,
) -> None:
    """Run the student chat terminal.

    Args:
        class_code: Class code provided by the teacher.
        student_id: Unique student identifier.
        student_name: Optional display name for the student.
    """
    from clawed.student_bot import StudentBot

    bot = StudentBot()

    # Validate the class code
    class_info = bot.get_class(class_code)
    if not class_info:
        console.print(f"[red]Class code '{class_code}' not found.[/red] Double-check with your teacher and try again.")
        sys.exit(1)

    # Auto-register first-time student
    if not bot.is_registered(student_id, class_code):
        name = student_name or student_id
        result = bot.register_student(student_id, class_code, name)
        console.print(f"[green]{result}[/green]\n")

    # Check for active lesson
    if not class_info.active_lesson_json:
        console.print("[yellow]Your teacher hasn't activated a lesson yet. Check back soon![/yellow]")
        sys.exit(1)

    import json

    lesson_data = json.loads(class_info.active_lesson_json)
    lesson_title = lesson_data.get("title", "Today's Lesson")

    mode_label = "Hints only" if class_info.hint_mode else "Full answers"

    console.print(
        Panel(
            f"[bold]{lesson_title}[/bold]\n\n"
            f"Ask me anything about today's lesson!\n"
            f"Mode: {mode_label}\n\n"
            f"Type [bold]/quit[/bold] to exit.",
            title=f"[bold green]Student Chat \u2014 {class_code}[/bold green]",
            border_style="green",
            padding=(1, 2),
        )
    )

    # Chat loop
    while True:
        try:
            message = Prompt.ask("\n[bold cyan]You[/bold cyan]")
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Goodbye![/dim]")
            break

        text = message.strip()
        if not text:
            continue
        if text.lower() in ("/quit", "/exit", "quit", "exit"):
            console.print("[dim]Goodbye! Keep up the great work.[/dim]")
            break

        with Live(
            Spinner("dots", text="[dim]Thinking...[/dim]", style="green"),
            console=console,
            transient=True,
        ):
            try:
                response = _run_async(bot.handle_message(text, student_id, class_code))
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


def cli_entry() -> None:
    """Entry point when run as ``python -m clawed.student_cli``."""
    import argparse

    parser = argparse.ArgumentParser(description="Claw-ED Student Chat \u2014 ask your teacher bot anything")
    parser.add_argument(
        "--class-code",
        required=True,
        help="Class code from your teacher (e.g. MR-MAC-P3)",
    )
    parser.add_argument(
        "--student-id",
        default="student-001",
        help="Your student ID (default: student-001)",
    )
    parser.add_argument(
        "--name",
        default=None,
        help="Your display name (optional)",
    )
    args = parser.parse_args()
    main(
        class_code=args.class_code,
        student_id=args.student_id,
        student_name=args.name,
    )


if __name__ == "__main__":
    cli_entry()
