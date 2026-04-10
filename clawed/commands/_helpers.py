"""Shared CLI helpers used by all command modules."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import typer
from rich.console import Console

from clawed.models import AppConfig, TeacherPersona


def _is_utf8_terminal() -> bool:
    """Check if the terminal supports UTF-8."""
    import locale

    try:
        encoding = locale.getpreferredencoding(False)
        return encoding.lower().replace("-", "") in ("utf8",)
    except Exception:
        return False


def _make_console() -> Console:
    """Create a Rich console with safe encoding for all platforms.

    On Windows with non-UTF-8 terminals, forces UTF-8 on stdout/stderr
    so LLM-generated Unicode (arrows, em dashes, curly quotes) doesn't
    crash Rich's renderer. safe_box handles box-drawing characters.
    """
    force_ascii = sys.platform == "win32" and not _is_utf8_terminal()

    if force_ascii:
        # Force UTF-8 encoding on the output stream so Rich can render
        # Unicode content (→, —, ", etc.) even on cp1252 terminals.
        import io

        if hasattr(sys.stdout, "buffer"):
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "buffer"):
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

    kwargs: dict = {
        "highlight": False,
        "safe_box": force_ascii,
    }

    # On Windows with a rewrapped stdout, tell Rich to use it explicitly
    if force_ascii and hasattr(sys.stdout, "buffer"):
        kwargs["file"] = sys.stdout

    return Console(**kwargs)


console = _make_console()


def output_dir() -> Path:
    cfg = AppConfig.load()
    return Path(cfg.output_dir).expanduser().resolve()


def run_async(coro):
    """Run an async coroutine from synchronous CLI code."""
    return asyncio.run(coro)


def persona_path() -> Path:
    return output_dir() / "persona.json"


def get_default_subject() -> str:
    """Get default subject from the teacher's profile, or a generic fallback."""
    try:
        cfg = AppConfig.load()
        subjects = cfg.teacher_profile.subjects
        if subjects:
            return subjects[0]
    except Exception:
        pass
    return "General"


def _safe_progress(**kwargs):
    """Create a Progress bar that works on all platforms.

    On Windows with cp1252, Rich's SpinnerColumn() uses Braille characters
    that crash.  We substitute a plain TextColumn on win32.
    """
    from rich.progress import (
        BarColumn,
        Progress,
        SpinnerColumn,
        TaskProgressColumn,
        TextColumn,
    )

    columns: list = []
    if sys.platform == "win32":
        columns.append(TextColumn("[progress.description]{task.description}"))
    else:
        columns.append(SpinnerColumn())
        columns.append(TextColumn("[progress.description]{task.description}"))
    columns.extend([BarColumn(), TaskProgressColumn()])
    return Progress(*columns, **kwargs)


def check_api_key_or_exit() -> None:
    """Verify an API key is configured before starting expensive generation."""
    from clawed.config import get_api_key

    try:
        cfg = AppConfig.load()
    except Exception:
        console.print(
            "[red]Claw-ED is not configured yet.[/red]\n"
            "Run [bold]clawed setup[/bold] to pick your AI provider and add an API key."
        )
        raise typer.Exit(1)

    provider = cfg.provider.value if hasattr(cfg.provider, "value") else str(cfg.provider)
    if provider == "ollama":
        return  # Ollama doesn't need an API key

    key = get_api_key(provider)
    if not key:
        console.print(
            f"[red]No API key found for {provider}.[/red]\n"
            f"Set one with: [bold]clawed setup[/bold]\n"
            f"Or set the environment variable: [bold]{provider.upper()}_API_KEY[/bold]"
        )
        raise typer.Exit(1)


def friendly_error(e: Exception) -> str:
    """Convert technical exceptions to teacher-friendly messages."""
    msg = str(e)
    if "429" in msg or "rate" in msg.lower():
        return "The AI service is busy right now. Wait a minute and try again."
    if "401" in msg or "403" in msg or "auth" in msg.lower() or "invalid" in msg.lower():
        return "Your API key doesn't seem to work. Run 'clawed debug' to check your connection."
    if "timeout" in msg.lower() or "timed out" in msg.lower():
        return "The AI took too long to respond. Try again, or check your internet connection."
    if "connection" in msg.lower() or "connect" in msg.lower():
        return "Can't reach the AI service. Check your internet connection."
    if "model" in msg.lower() and ("not found" in msg.lower() or "404" in msg.lower()):
        return "The AI model wasn't found. Run 'clawed config show' to check your model setting."
    return f"Something went wrong: {msg}\nRun 'clawed debug' for details."


def load_persona_or_exit() -> TeacherPersona:
    path = persona_path()
    if path.exists():
        from clawed.persona import load_persona

        return load_persona(path)

    # No persona file -- offer a starter persona so teachers aren't blocked
    from clawed.starter_personas import get_starter_persona

    console.print(
        "[yellow]No teaching persona found.[/yellow]\n"
        "You can:\n"
        "  1. Run [bold]clawed ingest <path>[/bold] to learn from your files\n"
        "  2. Use a starter persona to get going right away\n"
    )

    # Try to detect subject from config
    try:
        cfg = AppConfig.load()
        subjects = cfg.teacher_profile.subjects if cfg.teacher_profile else []
        if subjects:
            persona = get_starter_persona(subjects[0])
            if persona:
                console.print(f"[cyan]Using starter persona for {persona.subject_area}.[/cyan]")
                return persona
    except Exception:
        pass

    # Default starter
    persona = get_starter_persona("social_studies")
    console.print(f"[cyan]Using default starter persona ({persona.subject_area}).[/cyan]")
    return persona
