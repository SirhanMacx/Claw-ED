"""First-run onboarding wizard for Claw-ED.

When a teacher runs `clawed chat` or `clawed bot` with no config,
this guided setup collects their teaching context, API key, and
optionally ingests existing lesson plans — so Claw-ED is ready to
go in under two minutes.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from clawed.commands._helpers import _safe_progress, console
from clawed.config import has_config, set_api_key, test_llm_connection
from clawed.models import AppConfig, LLMProvider, TeacherPersona, TeacherProfile
from clawed.state_standards import STATE_STANDARDS_CONFIG

logger = logging.getLogger(__name__)

_BASE_DIR = Path(os.environ.get("EDUAGENT_DATA_DIR", str(Path.home() / ".eduagent")))

# Full state names for autocomplete / fuzzy matching
US_STATES: list[str] = sorted(
    {v["name"] for v in STATE_STANDARDS_CONFIG.values()}
)

# Reverse lookup: full name -> abbreviation
_STATE_NAME_TO_ABBR: dict[str, str] = {
    v["name"].lower(): k for k, v in STATE_STANDARDS_CONFIG.items()
}
# Also map abbreviations directly
for _abbr in STATE_STANDARDS_CONFIG:
    _STATE_NAME_TO_ABBR[_abbr.lower()] = _abbr


def _resolve_state(raw: str) -> str | None:
    """Resolve a state name or abbreviation to a two-letter code."""
    key = raw.strip().lower()
    if not key:
        return None
    if key in _STATE_NAME_TO_ABBR:
        return _STATE_NAME_TO_ABBR[key]
    # Fuzzy prefix match
    for name, abbr in _STATE_NAME_TO_ABBR.items():
        if name.startswith(key):
            return abbr
    return None


def _ask_state() -> str:
    """Prompt for state with validation against the 50-state list."""
    while True:
        raw = Prompt.ask(
            "\n[bold]What state are you in?[/bold]  [dim](name or abbreviation)[/dim]"
        )
        abbr = _resolve_state(raw)
        if abbr:
            full_name = STATE_STANDARDS_CONFIG[abbr]["name"]
            console.print(f"  [green]\u2713[/green] {full_name}")
            return abbr
        console.print(f"  [red]Couldn't match \"{raw}\".[/red] Try the full name or two-letter code.")


def _ask_provider() -> tuple[LLMProvider, str | None]:
    """Show provider options and collect an API key."""
    table = Table(title="Choose your AI backend", show_header=True, header_style="bold")
    table.add_column("#", style="dim", width=3)
    table.add_column("Provider")
    table.add_column("Cost")
    table.add_column("Notes")
    table.add_row("1", "Google Gemini", "Free tier available", "Best for getting started \u2014 generous free quota")
    table.add_row("2", "Anthropic (Claude)", "Pay per token", "Highest quality")
    table.add_row("3", "OpenAI (GPT-4o)", "Pay per token", "Widely used")
    table.add_row("4", "Ollama (local)", "Free", "Runs on your machine \u2014 no internet needed")
    console.print()
    console.print(table)

    while True:
        choice = Prompt.ask(
            "\n[bold]Pick a provider[/bold]", choices=["1", "2", "3", "4"], default="1",
        )
        if choice == "1":
            provider = LLMProvider.GOOGLE
            console.print(
                "\n  [dim]Get a free API key at: https://aistudio.google.com/apikey[/dim]",
            )
            key = Prompt.ask("  [bold]Google AI API key[/bold]  [dim](AIza...)[/dim]")
            if not key.strip():
                console.print("  [red]API key cannot be empty.[/red]")
                continue
            return provider, key.strip()
        elif choice == "2":
            provider = LLMProvider.ANTHROPIC
            key = Prompt.ask("  [bold]Anthropic API key[/bold]  [dim](sk-ant-...)[/dim]")
            if not key.strip():
                console.print("  [red]API key cannot be empty.[/red]")
                continue
            return provider, key.strip()
        elif choice == "3":
            provider = LLMProvider.OPENAI
            key = Prompt.ask("  [bold]OpenAI API key[/bold]  [dim](sk-...)[/dim]")
            if not key.strip():
                console.print("  [red]API key cannot be empty.[/red]")
                continue
            return provider, key.strip()
        else:
            return LLMProvider.OLLAMA, None


def _test_connection(config: AppConfig) -> bool:
    """Test the LLM connection and show result."""
    console.print("\n  [dim]Testing connection...[/dim]")
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        result = loop.run_until_complete(test_llm_connection(config))
    except RuntimeError:
        result = asyncio.run(test_llm_connection(config))

    if result.get("connected"):
        console.print(f"  [green]\u2713 Connected![/green] {result.get('message', '')}")
        return True
    else:
        console.print(f"  [red]\u2717 Connection failed:[/red] {result.get('error', 'Unknown error')}")
        return False


def _detect_available_models() -> tuple[LLMProvider | None, str]:
    """Auto-detect what LLM backends are available.

    Checks: ANTHROPIC_API_KEY, OPENAI_API_KEY, OLLAMA_API_KEY (cloud),
    and Ollama running locally.
    Returns (provider, description) or (None, message).
    """
    # Check Google Gemini (free tier)
    if os.environ.get("GOOGLE_API_KEY"):
        return LLMProvider.GOOGLE, "Google Gemini API key found in environment"

    # Check Anthropic
    if os.environ.get("ANTHROPIC_API_KEY"):
        return LLMProvider.ANTHROPIC, "Anthropic API key found in environment"

    # Check OpenAI
    if os.environ.get("OPENAI_API_KEY"):
        return LLMProvider.OPENAI, "OpenAI API key found in environment"

    # Check Ollama Cloud (API key in env) — before local Ollama check
    if os.environ.get("OLLAMA_API_KEY"):
        return LLMProvider.OLLAMA, "Ollama Cloud API key found in environment"

    # Check local Ollama
    try:
        import httpx
        resp = httpx.get("http://localhost:11434/api/tags", timeout=3.0)
        if resp.status_code == 200:
            data = resp.json()
            models = [m.get("name", "") for m in data.get("models", [])]
            # Prefer these models in order
            preferred = ["gemma4", "minimax-m2.7", "qwen3.5", "llama4", "mistral"]
            for pref in preferred:
                for model in models:
                    if pref in model:
                        return LLMProvider.OLLAMA, f"Ollama running with {model}"
            if models:
                return LLMProvider.OLLAMA, f"Ollama running with {models[0]}"
            return LLMProvider.OLLAMA, "Ollama running (no models pulled yet)"
    except Exception:
        pass  # Ollama detection is a probe; absence is normal

    return None, (
        "No LLM backend detected.\n"
        "  Set ANTHROPIC_API_KEY or OPENAI_API_KEY in your environment,\n"
        "  or install Ollama (https://ollama.com/download) and run: ollama pull qwen3.5"
    )


def _open_folder_picker() -> str | None:
    """Open a native Finder/Explorer folder picker. Returns path or None."""
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()  # Hide the root window
        root.attributes("-topmost", True)  # Bring dialog to front
        folder = filedialog.askdirectory(
            title="Select your lesson plans folder",
        )
        root.destroy()
        return folder if folder else None
    except Exception:
        return None  # tkinter may not be available (headless, WSL); fall back to path input


def _ask_materials() -> tuple[str | None, str | None]:
    """Collect curriculum materials — local folder and/or Google Drive link.

    Offers a native file picker (Finder/Explorer) for non-technical teachers,
    with a paste-a-path fallback and Google Drive option.

    Returns (local_path, drive_url) — either or both may be None.
    """
    console.print(
        "\n[bold]Do you have existing lesson plans or curriculum materials?[/bold]\n"
        "  Claw-ED learns your teaching style from your files.\n"
        "  [dim]Supported: PDF, DOCX, PPTX, TXT, MD[/dim]\n"
    )

    console.print(
        "  How would you like to share your materials?\n"
        "    [bold][1][/bold] Browse for a folder (opens a file picker window)\n"
        "    [bold][2][/bold] Paste a folder path\n"
        "    [bold][3][/bold] Paste a Google Drive link\n"
        "    [bold][4][/bold] Skip for now\n"
    )

    local_path = None
    drive_url = None

    choice = Prompt.ask("  Choose", choices=["1", "2", "3", "4"], default="1")

    if choice == "1":
        # Native file picker
        console.print("  [dim]Opening folder picker...[/dim]")
        picked = _open_folder_picker()
        if picked:
            local_path = picked
            console.print(f"  [green]\u2713[/green] Selected: {picked}")
        else:
            console.print("  [dim]No folder selected. You can add materials later.[/dim]")

    elif choice == "2":
        # Manual path entry
        raw = Prompt.ask(
            "  [bold]Folder path[/bold]  [dim](e.g. ~/Documents/Lessons)[/dim]",
            default="",
        )
        path_str = raw.strip()
        if path_str:
            resolved = Path(path_str).expanduser().resolve()
            if resolved.exists():
                local_path = str(resolved)
                console.print(f"  [green]\u2713[/green] Found: {resolved}")
            else:
                console.print(f"  [red]Path not found:[/red] {resolved}")

    elif choice == "3":
        # Google Drive link
        raw_drive = Prompt.ask(
            "  [bold]Google Drive folder link[/bold]  [dim](paste the sharing URL)[/dim]",
            default="",
        )
        drive_str = raw_drive.strip()
        if drive_str and ("drive.google.com" in drive_str or "docs.google.com" in drive_str):
            drive_url = drive_str
            console.print("  [green]\u2713[/green] Drive link saved")
        elif drive_str:
            console.print("  [yellow]That doesn't look like a Google Drive link.[/yellow]")

    # Also ask for the other option if they provided one
    if local_path and not drive_url:
        raw_drive = Prompt.ask(
            "\n  [bold]Also have a Google Drive link?[/bold]  [dim](paste URL, or Enter to skip)[/dim]",
            default="",
        )
        if raw_drive.strip() and "drive.google.com" in raw_drive.strip():
            drive_url = raw_drive.strip()
            console.print("  [green]\u2713[/green] Drive link saved")

    if not local_path and not drive_url:
        console.print(
            "\n  [dim]No materials yet? No problem! You can add them anytime:[/dim]\n"
            "    [bold]clawed ingest ~/your-lessons/[/bold]\n"
        )

    return local_path, drive_url


def _ingest_materials(path_str: str, config: AppConfig) -> None:
    """Run ingestion with a progress bar and show persona summary."""
    import asyncio

    from clawed.ingestor import ingest_path

    source = Path(path_str)

    # Use scan_directory to count files (single walk) then ingest with progress
    from clawed.ingestor import scan_directory

    if source.is_dir():
        files, summary = scan_directory(source)
        if not files:
            console.print("  [yellow]No supported files found. You can ingest later with:[/yellow]")
            console.print("    [bold]clawed ingest <path>[/bold]")
            return
        console.print(f"  [dim]{summary}[/dim]")
        file_count = len(files)
    else:
        file_count = 1

    with _safe_progress(console=console) as progress:
        task = progress.add_task(
            f"Reading {file_count} files from {source.name}...",
            total=file_count,
        )

        def _on_progress(current: int, total: int) -> None:
            progress.update(task, completed=current, total=total)

        docs = ingest_path(source, progress_callback=_on_progress)
        progress.update(task, completed=file_count, description="Files processed")

    console.print(f"  [green]\u2713 Processed {len(docs)} files.[/green]")

    # Extract persona from documents
    try:
        from clawed.persona import extract_persona
        console.print("  [dim]Extracting teaching style patterns...[/dim]")
        persona = asyncio.run(extract_persona(docs, config))
        console.print(
            Panel(
                persona.to_prompt_context(),
                title="[bold green]Your Teaching Profile[/bold green]",
                border_style="green",
                padding=(0, 1),
            )
        )
    except Exception as e:
        console.print(f"  [yellow]Could not extract teaching style: {e}[/yellow]")
        console.print("  [dim]You can try again later with: clawed ingest <path>[/dim]")
        persona = TeacherPersona()
    console.print(f"  [green]\u2713 Persona saved — {persona.name or 'Teacher'} profile ready[/green]")


def _ingest_drive(drive_url: str, config: AppConfig) -> None:
    """Ingest materials from a Google Drive folder link."""
    console.print("\n  [dim]Connecting to Google Drive...[/dim]")
    try:
        from clawed.drive import ingest_drive_folder

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            docs = loop.run_until_complete(ingest_drive_folder(drive_url))
        finally:
            loop.close()

        if docs:
            console.print(f"  [green]\u2713 Imported {len(docs)} documents from Drive.[/green]")
        else:
            console.print("  [yellow]No documents found in that Drive folder.[/yellow]")
    except ImportError:
        console.print(
            "  [yellow]Google Drive support requires extra dependencies.[/yellow]\n"
            "    Install with: [bold]pip install 'clawed[google]'[/bold]\n"
            "    Then re-run: [bold]clawed setup[/bold]"
        )
    except Exception as e:
        console.print(f"  [red]Drive import failed:[/red] {e}")
        console.print("  [dim]You can try again later with: clawed ingest <drive-link>[/dim]")


def _show_persona_preview(subjects: list[str], grade_levels: list[str], state_abbr: str) -> bool:
    """Show a preview of what we learned and ask for confirmation."""
    from clawed.state_standards import STATE_STANDARDS_CONFIG
    state_name = STATE_STANDARDS_CONFIG.get(state_abbr, {}).get("name", state_abbr)

    preview = (
        f"I learned that you teach {', '.join(grade_levels)} grade "
        f"{', '.join(subjects)} in {state_name}."
    )
    console.print(f"\n  [bold]{preview}[/bold]")
    confirm = Prompt.ask("  Is this right?", choices=["y", "n"], default="y")
    return confirm.lower() == "y"


def _ask_provider_wizard() -> tuple[LLMProvider, str | None, str | None, str | None]:
    """New setup wizard provider selection — strongly recommends Ollama Cloud.

    Returns (provider, api_key, ollama_base_url, ollama_model).
    """
    console.print(
        "\n[bold]Claw-ED needs an AI service to generate your lessons.[/bold]\n"
        "We recommend Ollama Cloud — one flat monthly fee, unlimited lessons.\n"
    )
    console.print(
        "  [bold yellow]\u2605[/bold yellow] [bold]Ollama Cloud[/bold] — $20/month, unlimited lessons, great quality\n"
        "    Best for daily use. No surprise charges.\n"
        "    Sign up: [cyan]https://ollama.com[/cyan] \u2192 create account \u2192 Settings \u2192 API Keys\n"
    )

    key = Prompt.ask(
        "[bold]Paste your Ollama API key[/bold]  [dim](or press Enter to see other options)[/dim]",
        default="",
    )
    if key.strip():
        return (
            LLMProvider.OLLAMA,
            key.strip(),
            "https://ollama.com",
            "gemma4:31b-cloud",
        )

    # Show alternatives with plain-English descriptions
    console.print("\n[bold]Other options:[/bold]\n")
    console.print(
        "  [bold][1][/bold] Claude (by Anthropic) — highest quality, ~$0.10/lesson"
    )
    console.print(
        "        Sign up: [cyan]https://console.anthropic.com[/cyan] \u2192 API Keys"
    )
    console.print(
        "  [bold][2][/bold] GPT (by OpenAI) — high quality, ~$0.15/lesson"
    )
    console.print(
        "        Sign up: [cyan]https://platform.openai.com/api-keys[/cyan]"
    )
    console.print(
        "  [bold][3][/bold] Local Ollama — free, runs on your computer (requires separate install)"
    )
    console.print(
        "        Install: [cyan]https://ollama.com/download[/cyan]"
    )
    console.print("  [bold][4][/bold] Skip for now — I'll set this up later")

    while True:
        choice = Prompt.ask(
            "\n[bold]Pick an option[/bold]",
            choices=["1", "2", "3", "4"],
            default="1",
        )
        if choice == "1":
            akey = Prompt.ask("  [bold]Paste your Claude API key[/bold]  [dim](starts with sk-ant-)[/dim]")
            if not akey.strip():
                console.print("  [red]API key can't be empty. Try again or pick a different option.[/red]")
                continue
            return LLMProvider.ANTHROPIC, akey.strip(), None, None
        elif choice == "2":
            okey = Prompt.ask("  [bold]Paste your OpenAI API key[/bold]  [dim](starts with sk-)[/dim]")
            if not okey.strip():
                console.print("  [red]API key can't be empty. Try again or pick a different option.[/red]")
                continue
            return LLMProvider.OPENAI, okey.strip(), None, None
        elif choice == "3":
            return LLMProvider.OLLAMA, None, None, None
        else:
            return None, None, None, None


def _onboarding_marker() -> Path:
    """Return the onboarding-complete marker path, respecting EDUAGENT_DATA_DIR."""
    return _BASE_DIR / "workspace" / "onboarding_complete"


def _write_onboarding_marker() -> None:
    """Mark onboarding as complete so the first-run prompt doesn't re-inject."""
    marker = _onboarding_marker()
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("Completed via setup wizard\n")


def _clear_config() -> None:
    """Reset config to defaults for a fresh setup."""
    path = AppConfig.config_path()
    if path.exists():
        path.unlink()
    # Also remove the onboarding marker so first-run triggers again
    marker = _onboarding_marker()
    if marker.exists():
        marker.unlink()
    console.print("  [dim]Previous configuration cleared.[/dim]")


def _setup_google() -> AppConfig | None:
    """Configure Google Gemini provider. Returns config or None to skip."""
    console.print("\n  Get your free API key at: [cyan]https://aistudio.google.com/apikey[/cyan]\n")
    key = Prompt.ask("  [bold]Gemini API key[/bold]")
    if not key.strip():
        console.print("  [yellow]No key entered. Run 'clawed setup' when ready.[/yellow]\n")
        return None
    key = key.strip()
    config = AppConfig(provider=LLMProvider.GOOGLE)
    config.google_model = "gemini-2.5-flash"
    set_api_key("google", key)
    console.print(f"  [green]\u2713 Key saved ({key[:8]}...)[/green]")
    return config


def _setup_anthropic() -> AppConfig | None:
    """Configure Anthropic Claude provider. Returns config or None to skip."""
    console.print(
        "\n  Get your API key at: [cyan]https://console.anthropic.com[/cyan] \u2192 API Keys\n"
        "  Cost: ~$0.10 per lesson with Sonnet, ~$0.50 with Opus\n"
    )
    key = Prompt.ask("  [bold]Claude API key (starts with sk-ant-)[/bold]")
    if not key.strip():
        console.print("  [yellow]No key. Run 'clawed setup' when ready.[/yellow]\n")
        return None
    key = key.strip()
    config = AppConfig(provider=LLMProvider.ANTHROPIC)
    config.anthropic_model = "claude-sonnet-4-6"
    set_api_key("anthropic", key)
    console.print(f"  [green]\u2713 Key saved ({key[:8]}...)[/green]")
    return config


def _setup_ollama_cloud() -> AppConfig | None:
    """Configure Ollama Cloud provider. Returns config or None to skip."""
    console.print("\n  Sign up at: [cyan]https://ollama.com[/cyan] \u2192 Settings \u2192 API Keys\n")
    key = Prompt.ask("  [bold]Ollama API key[/bold]")
    if not key.strip():
        console.print("  [yellow]No key. Run 'clawed setup' when ready.[/yellow]\n")
        return None
    key = key.strip()
    config = AppConfig(provider=LLMProvider.OLLAMA)
    config.ollama_base_url = "https://ollama.com"
    config.ollama_model = "gemma4:31b-cloud"
    set_api_key("ollama", key)
    config.ollama_api_key = ""
    console.print(f"  [green]\u2713 Key saved ({key[:8]}...)[/green]")
    return config


def _setup_local_ollama(local_ollama: bool) -> AppConfig:
    """Configure local Ollama provider. Always returns a config."""
    import httpx

    config = AppConfig(provider=LLMProvider.OLLAMA)
    config.ollama_base_url = "http://localhost:11434"
    if local_ollama:
        try:
            resp = httpx.get("http://localhost:11434/api/tags", timeout=5.0)
            models = [m["name"] for m in resp.json().get("models", [])]
            if models:
                console.print(f"  [green]\u2713 Found models: {', '.join(models[:5])}[/green]")
                picked = _pick_best_ollama_model(models)
                config.ollama_model = picked
                console.print(f"  [green]\u2713 Using model: {picked}[/green]")
            else:
                console.print("  [yellow]No models found. Pull one: ollama pull qwen3.5[/yellow]")
                config.ollama_model = "qwen3.5"
        except Exception:
            logger.debug("Ollama model query failed; defaulting to qwen3.5", exc_info=True)
            config.ollama_model = "qwen3.5"
    else:
        console.print("  [yellow]Ollama not detected. Install it and pull a model first.[/yellow]")
        config.ollama_model = "qwen3.5"
    return config


def _pick_best_ollama_model(models: list[str]) -> str:
    """Pick the most capable model from a list of available Ollama models."""
    cloud_models = [m for m in models if ":cloud" in m]
    preferred = ["gemma4", "minimax-m2.7", "deepseek", "qwen3.5", "llama4"]
    for pref in preferred:
        for m in cloud_models:
            if pref in m:
                return m
    for pref in preferred:
        for m in models:
            if pref in m:
                return m
    return models[0]


def _setup_openai() -> AppConfig | None:
    """Configure OpenAI GPT provider. Returns config or None to skip."""
    console.print(
        "\n  Get your API key at: [cyan]https://platform.openai.com/api-keys[/cyan]\n"
        "  Cost: ~$0.15 per lesson with GPT-4o\n"
    )
    key = Prompt.ask("  [bold]OpenAI API key (starts with sk-)[/bold]")
    if not key.strip():
        console.print("  [yellow]No key. Run 'clawed setup' when ready.[/yellow]\n")
        return None
    key = key.strip()
    config = AppConfig(provider=LLMProvider.OPENAI)
    set_api_key("openai", key)
    console.print(f"  [green]\u2713 Key saved ({key[:8]}...)[/green]")
    return config


def _choose_interface(config: AppConfig) -> str:
    """Step 3 of quick setup: choose Telegram bot or terminal chat."""
    console.print(
        "\n[bold]Great -- you're all set up![/bold] One last thing:\n\n"
        "  [bold cyan][1][/bold cyan] Telegram bot \u2014 chat with me from your phone "
        "[dim](great for on-the-go planning)[/dim]\n"
        "  [bold cyan][2][/bold cyan] \u2605 Start chatting right here \u2014 "
        "I'll get to know you and your classroom\n"
    )
    interface = Prompt.ask("Choice", choices=["1", "2"], default="2")

    if interface == "1":
        console.print(
            "\n  Get a bot token from [bold]@BotFather[/bold] on Telegram:\n"
            "  1. Open Telegram, search for @BotFather\n"
            "  2. Send /newbot, pick a name and username\n"
            "  3. Copy the token BotFather gives you\n"
        )
        tg_token = Prompt.ask("  [bold]Paste your bot token[/bold]")
        if tg_token.strip():
            config.telegram_bot_token = tg_token.strip()
            set_api_key("telegram", tg_token.strip())
            config.save()
            console.print("\n  [green]\u2713 Bot configured![/green]")
            _write_onboarding_marker()
            console.print(
                "\n  [bold]Telegram bot will start automatically![/bold]\n"
                "  Open Telegram, find your bot, and send it:\n\n"
                '    [bold cyan]Hello![/bold cyan]\n\n'
                "  Claw-ED will introduce itself and get to know you.\n"
                "  [dim]The bot runs in the background -- no extra terminal needed.[/dim]\n"
            )
            return "telegram"
        console.print("  [dim]No token entered. Falling back to terminal chat.[/dim]\n")

    _write_onboarding_marker()
    console.print("\n  [green]\u2713 All set![/green] Let's chat -- I'll start by getting to know you.\n")
    return "terminal"


def quick_model_setup() -> str:
    """Minimal first-run setup: provider + key + interface choice. 30 seconds.

    Returns:
        "telegram" -- teacher wants to use Telegram (bot should start)
        "terminal" -- teacher wants terminal chat
        "skip" -- teacher skipped setup
    """
    console.print(Panel(
        "[bold]Hey there, fellow educator![/bold] \U0001f393\n\n"
        "I'm Claw-ED -- think of me as a colleague who's really good\n"
        "at turning your ideas into polished lesson plans, handouts,\n"
        "and slides.\n\n"
        "First, let's connect me to an AI service so I can start\n"
        "creating for you. This takes about 30 seconds.",
        title="[bold green]Claw-ED Setup[/bold green]",
        border_style="green",
        padding=(1, 2),
    ))

    # Detect local Ollama
    local_ollama = False
    try:
        import httpx
        resp = httpx.get("http://localhost:11434/api/tags", timeout=3.0)
        if resp.status_code == 200:
            local_ollama = True
    except Exception:
        pass  # Ollama not running is normal; just hide the menu option

    # Show provider menu
    console.print("\n[bold]Which AI service?[/bold]\n")
    console.print(
        "  [bold cyan][1][/bold cyan] \u2605 Google Gemini \u2014 free tier available, "
        "good quality [dim](easiest to start)[/dim]"
    )
    console.print("        Sign up: [cyan]https://aistudio.google.com/apikey[/cyan]")
    console.print("  [bold cyan][2][/bold cyan] Claude (Anthropic) \u2014 highest quality, ~$0.10/lesson")
    console.print("        Sign up: [cyan]https://console.anthropic.com[/cyan] \u2192 API Keys")
    console.print("  [bold cyan][3][/bold cyan] Ollama Cloud \u2014 $20/month, unlimited lessons")
    console.print("        Sign up: [cyan]https://ollama.com[/cyan] \u2192 Settings \u2192 API Keys")
    if local_ollama:
        console.print("  [bold cyan][4][/bold cyan] Local Ollama \u2014 detected on this machine, completely free")
    else:
        console.print("  [bold cyan][4][/bold cyan] Local Ollama \u2014 free, runs on your computer")
        console.print("        Install: [cyan]https://ollama.com/download[/cyan]")
    console.print("  [bold cyan][5][/bold cyan] GPT (OpenAI) \u2014 high quality, ~$0.15/lesson")
    console.print("        Sign up: [cyan]https://platform.openai.com/api-keys[/cyan]")
    console.print("  [bold cyan][6][/bold cyan] Try demo mode \u2014 no API key needed, see example output first")
    console.print("  [bold cyan][7][/bold cyan] Skip \u2014 I'll set this up later\n")

    choice = Prompt.ask("Choice", choices=["1", "2", "3", "4", "5", "6", "7"], default="1")

    if choice == "7":
        AppConfig().save()
        _write_onboarding_marker()
        console.print("\n  [yellow]No AI configured. Run 'clawed setup' when you're ready.[/yellow]\n")
        return "skip"

    if choice == "6":
        AppConfig().save()
        _write_onboarding_marker()
        console.print(
            "\n  [green]\u2713 Demo mode active![/green] Try: [bold]clawed demo[/bold] to see sample output.\n"
            "  When you're ready for real generation, run [bold]clawed setup[/bold].\n"
        )
        return "terminal"

    # Configure per provider
    setup_fns = {"1": _setup_google, "2": _setup_anthropic, "3": _setup_ollama_cloud, "5": _setup_openai}
    if choice == "4":
        config = _setup_local_ollama(local_ollama)
    elif choice in setup_fns:
        config = setup_fns[choice]()
        if config is None:
            AppConfig().save()
            _write_onboarding_marker()
            return "skip"
    else:
        config = AppConfig()

    config.save()
    return _choose_interface(config)


def run_setup_wizard(reset: bool = False) -> AppConfig:
    """Run the teacher-friendly setup wizard.

    This is the main entry point for `clawed setup`. It walks teachers
    through configuration in plain English with a strongly recommended
    default (Ollama Cloud).

    Args:
        reset: If True, clear existing config before starting.

    Returns the saved AppConfig so callers can proceed immediately.
    """
    if reset:
        _clear_config()

    # ── Step 1: Welcome ──
    console.print(
        Panel(
            "[bold]Welcome to Claw-ED![/bold]\n\n"
            "I'm your AI teaching assistant. I'll learn your teaching style\n"
            "and generate lessons, worksheets, and assessments in YOUR voice.\n\n"
            "Let's get you set up -- it takes about 60 seconds.",
            title="[bold green]\U0001f393 Claw-ED Setup[/bold green]",
            border_style="green",
            padding=(1, 2),
        )
    )

    # ── Step 2: About you ──
    subjects_raw = Prompt.ask("\n[bold]What subject(s) do you teach?[/bold]")
    subjects = [s.strip() for s in subjects_raw.split(",") if s.strip()]

    grades_raw = Prompt.ask("[bold]What grade level(s)?[/bold]")
    grade_levels = [g.strip() for g in grades_raw.split(",") if g.strip()]

    state_abbr = _ask_state()

    # Preview and confirm
    confirmed = _show_persona_preview(subjects, grade_levels, state_abbr)
    if not confirmed:
        console.print("  [dim]Let's try again.[/dim]")
        subjects_raw = Prompt.ask("[bold]What subject(s) do you teach?[/bold]")
        subjects = [s.strip() for s in subjects_raw.split(",") if s.strip()]
        grades_raw = Prompt.ask("[bold]What grade level(s)?[/bold]")
        grade_levels = [g.strip() for g in grades_raw.split(",") if g.strip()]
        state_abbr = _ask_state()

    # ── Step 3: Choose your AI ──
    detected_provider, detect_msg = _detect_available_models()

    provider = None
    api_key = None
    ollama_base_url = None
    ollama_model = None

    if detected_provider:
        # Auto-detected — confirm and use it
        provider_label = detect_msg
        if detected_provider == LLMProvider.ANTHROPIC:
            provider_label = "Anthropic (Claude)"
        elif detected_provider == LLMProvider.OPENAI:
            provider_label = "OpenAI (GPT)"
        elif "Cloud" in detect_msg:
            provider_label = "Ollama Cloud"
        else:
            provider_label = "local Ollama"
        console.print(f"\n  [green]\u2713 Found your {provider_label}.[/green] {detect_msg}")

        provider = detected_provider
        api_key = None  # Already in env

        # If Ollama Cloud detected via env, set cloud URL/model
        if detected_provider == LLMProvider.OLLAMA and "Cloud" in detect_msg:
            ollama_base_url = "https://ollama.com"
            ollama_model = "gemma4:31b-cloud"
    else:
        # No auto-detection — run the wizard
        provider, api_key, ollama_base_url, ollama_model = _ask_provider_wizard()

    # Save API key securely
    if api_key and provider:
        set_api_key(provider.value, api_key)

    # Build and save config
    profile = TeacherProfile(
        subjects=subjects,
        grade_levels=grade_levels,
        state=state_abbr,
    )

    config_kwargs: dict = {"teacher_profile": profile}
    if provider:
        config_kwargs["provider"] = provider
    if ollama_base_url:
        config_kwargs["ollama_base_url"] = ollama_base_url
    if ollama_model:
        config_kwargs["ollama_model"] = ollama_model
    if api_key and provider == LLMProvider.OLLAMA:
        set_api_key("ollama", api_key)
        # Don't put the key in config_kwargs — it would leak to config.json

    config = AppConfig(**config_kwargs)
    config.save()

    # ── Step 4: Test connection ──
    connected = False
    if provider is not None:
        connected = _test_connection(config)
        if not connected:
            retry = Prompt.ask(
                "  [yellow]Connection didn't work. Want to try again?[/yellow]",
                choices=["retry", "skip"],
                default="skip",
            )
            if retry == "retry":
                connected = _test_connection(config)
            if not connected:
                console.print(
                    "  [yellow]No worries — you can fix this anytime:[/yellow]\n"
                    "    [bold]clawed setup --reset[/bold]"
                )
    else:
        console.print(
            "\n  [yellow]No AI service configured yet. You can set one up anytime:[/yellow]\n"
            "    [bold]clawed setup[/bold]"
        )

    # ── Step 5: Import materials (optional) ──
    local_path, drive_url = _ask_materials()
    if local_path or drive_url:
        if local_path:
            profile.materials_paths = [local_path]
        if drive_url:
            profile.drive_urls = [drive_url]
        config.teacher_profile = profile
        config.save()
        try:
            from clawed.agent_core.identity import reset_cache
            reset_cache()
        except Exception:
            pass  # Cache reset is best-effort; stale cache clears on next startup
        if local_path:
            _ingest_materials(local_path, config)
        if drive_url:
            _ingest_drive(drive_url, config)

    # ── Step 6: Done ──
    _write_onboarding_marker()
    console.print(
        Panel(
            "[bold green]You're all set![/bold green]\n\n"
            "  [bold]clawed chat[/bold]                                  -- Start an interactive session\n"
            "  [bold]clawed lesson \"Topic\" -g 8 -s \"Subject\"[/bold]  -- Generate a lesson\n"
            "  [bold]clawed serve[/bold]                                 -- Launch the web dashboard\n"
            "  [bold]clawed setup --reset[/bold]                         -- Re-run this wizard anytime",
            title="[bold green]\u2705 Ready[/bold green]",
            border_style="green",
            padding=(1, 2),
        )
    )

    return config


def run_onboarding() -> AppConfig:
    """Run the interactive first-run onboarding wizard.

    This is a backward-compatible alias for run_setup_wizard().
    Returns the saved AppConfig so callers can proceed immediately.
    """
    return run_setup_wizard()


def _run_onboarding_legacy() -> AppConfig:
    """Legacy onboarding flow (preserved for reference).

    Returns the saved AppConfig so callers can proceed immediately.
    """
    console.print(
        Panel(
            "[bold]Welcome to Claw-ED![/bold]\n\n"
            "I was built by a teacher, for teachers.\n"
            "Let's get you set up in about a minute.",
            title="[bold green]\U0001f393 Claw-ED Setup[/bold green]",
            border_style="green",
            padding=(1, 2),
        )
    )

    # ── Model auto-detection ──
    detected_provider, detect_msg = _detect_available_models()
    if detected_provider:
        console.print(f"\n  [green]\u2713 Auto-detected:[/green] {detect_msg}")

    # ── Question 1: Subject(s) ──
    subjects_raw = Prompt.ask("\n[bold]What subject(s) do you teach?[/bold]")
    subjects = [s.strip() for s in subjects_raw.split(",") if s.strip()]

    # ── Question 2: Grade level(s) ──
    grades_raw = Prompt.ask("[bold]What grade level(s)?[/bold]")
    grade_levels = [g.strip() for g in grades_raw.split(",") if g.strip()]

    # ── Question 3: State ──
    state_abbr = _ask_state()

    # ── Preview and confirm ──
    confirmed = _show_persona_preview(subjects, grade_levels, state_abbr)
    if not confirmed:
        console.print("  [dim]Let's try again.[/dim]")
        subjects_raw = Prompt.ask("[bold]What subject(s) do you teach?[/bold]")
        subjects = [s.strip() for s in subjects_raw.split(",") if s.strip()]
        grades_raw = Prompt.ask("[bold]What grade level(s)?[/bold]")
        grade_levels = [g.strip() for g in grades_raw.split(",") if g.strip()]
        state_abbr = _ask_state()

    # ── API key selection ──
    if detected_provider and detected_provider != LLMProvider.OLLAMA:
        # Auto-detected a cloud provider, use it
        provider = detected_provider
        api_key = None  # Already in env
        console.print(f"  [green]\u2713 Using {provider.value} from environment.[/green]")
    elif detected_provider == LLMProvider.OLLAMA:
        provider = LLMProvider.OLLAMA
        api_key = None
        console.print("  [green]\u2713 Using local Ollama.[/green]")
    else:
        provider, api_key = _ask_provider()

    # Save key securely
    if api_key:
        set_api_key(provider.value, api_key)

    # Build and save config
    profile = TeacherProfile(
        subjects=subjects,
        grade_levels=grade_levels,
        state=state_abbr,
    )
    config = AppConfig(
        provider=provider,
        teacher_profile=profile,
    )
    config.save()

    # Test connection
    connected = _test_connection(config)
    if not connected and provider != LLMProvider.OLLAMA:
        console.print("  [yellow]You can update your key later with:[/yellow]")
        console.print(f"    [bold]clawed config set-key {provider.value}[/bold]")

    # ── Materials (optional) ──
    local_path, drive_url = _ask_materials()
    if local_path or drive_url:
        if local_path:
            profile.materials_paths = [local_path]
        if drive_url:
            profile.drive_urls = [drive_url]
        config.teacher_profile = profile
        config.save()
        try:
            from clawed.agent_core.identity import reset_cache
            reset_cache()
        except Exception:
            pass  # Cache reset is best-effort; stale cache clears on next startup
        if local_path:
            _ingest_materials(local_path, config)
        if drive_url:
            _ingest_drive(drive_url, config)

    # ── Auto-generate a sample lesson ──
    if connected:
        console.print("\n  [dim]Generating a sample lesson so you can see Claw-ED in action...[/dim]")
        try:
            from clawed.llm import LLMClient
            client = LLMClient(config)

            topic = subjects[0] if subjects else "Science"
            grade = grade_levels[0] if grade_levels else "8"

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                sample = loop.run_until_complete(
                    client.generate(
                        f"Generate a brief 3-sentence lesson opening (do-now/bell-ringer) "
                        f"for {grade} grade {topic}. Keep it concise.",
                        temperature=0.7,
                        max_tokens=300,
                    )
                )
            finally:
                loop.close()

            if sample and len(sample) > 10:
                console.print(
                    Panel(
                        sample.strip(),
                        title="[bold cyan]Sample Lesson Opening[/bold cyan]",
                        border_style="cyan",
                        padding=(0, 1),
                    )
                )
        except Exception:
            pass  # Sample lesson is best-effort

    # ── Success ──
    console.print(
        Panel(
            "[bold green]Setup complete! Here's how to use me:[/bold green]\n\n"
            "  [bold]clawed chat[/bold]         \u2014 Start an interactive session\n"
            "  [bold]clawed ingest <path>[/bold] \u2014 Feed me your lesson plans\n"
            "  [bold]clawed serve[/bold]         \u2014 Launch the web dashboard\n\n"
            "[dim]Tip: Run [bold]clawed ingest <path>[/bold] anytime to add more materials.[/dim]",
            title="[bold green]\u2705 Ready[/bold green]",
            border_style="green",
            padding=(1, 2),
        )
    )

    return config


def check_first_run() -> bool:
    """Check if this is a first run and launch onboarding if needed.

    Returns True if onboarding ran (or was skipped), False if config
    already existed. Callers should proceed normally either way.
    """
    if has_config():
        return False

    import sys
    if not sys.stdin.isatty():
        # Background mode (e.g. bot launched via cron/systemd) — skip interactive setup
        logger.info("Non-interactive mode, skipping onboarding wizard")
        # Create a minimal default config so the app can proceed
        try:
            cfg = AppConfig()
            cfg.save()
        except Exception:
            pass
        return True

    try:
        run_onboarding()
    except (KeyboardInterrupt, EOFError):
        console.print("\n[dim]Setup cancelled. Run [bold]clawed chat[/bold] again anytime.[/dim]")
    return True
