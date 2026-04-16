"""Claw-ED entry point router.

Routes to the TypeScript Ink TUI (if Node.js available) or falls back
to the Python typer CLI. The teacher never needs to know about this
routing — they just run `clawed`.

Usage:
    clawed                  → Interactive mode (Ink TUI or Python REPL)
    clawed lesson "Topic"   → Direct command (routes to Python --json if Ink TUI)
    clawed --python ...     → Force Python CLI (skip Node.js check)
    clawed daemon start     → Start background Telegram daemon
"""
from __future__ import annotations

import contextlib
import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def _data_dir() -> str:
    """Return the EDUAGENT_DATA_DIR, respecting the env var override."""
    return os.environ.get("EDUAGENT_DATA_DIR", str(Path.home() / ".eduagent"))


def _find_bundled_cli_js() -> str | None:
    """Find the pre-built cli.js bundled in the package.

    Checks the installed package's _cli_bundle directory first, then
    falls back to dev environment paths (cli/dist/ and cli/source/).
    Returns the absolute path to cli.js or None if not found.
    """
    # Check package data directory
    pkg_dir = Path(__file__).parent
    cli_js = pkg_dir / "_cli_bundle" / "cli.js"
    if cli_js.exists():
        return str(cli_js)

    # Check if we're in a dev environment with the cli/ directory
    repo_root = pkg_dir.parent
    # Build output goes to cli/dist/cli.js
    for dev_path in [
        repo_root / "cli" / "dist" / "cli.js",
        repo_root / "cli" / "source" / "cli.js",
    ]:
        if dev_path.exists():
            return str(dev_path)

    return None


def _find_daemon_entry() -> str | None:
    """Find the Telegram daemon entry point (JS or TS).

    Checks for compiled JS in daemon/dist/, raw TS in daemon/ (for dev
    mode with tsx), and the bundled daemon.js in the package. Returns
    the absolute path or None if not found.
    """
    pkg_dir = Path(__file__).parent
    repo_root = pkg_dir.parent

    # Dev environment
    daemon_ts = repo_root / "daemon" / "index.ts"
    daemon_js = repo_root / "daemon" / "dist" / "index.js"

    if daemon_js.exists():
        return str(daemon_js)
    if daemon_ts.exists():
        # Use ts-node or tsx for dev mode
        return str(daemon_ts)

    # Bundled daemon
    bundled = pkg_dir / "_cli_bundle" / "daemon.js"
    if bundled.exists():
        return str(bundled)

    return None


def _ed_greeting() -> None:
    """Print Ed's proactive greeting before the TUI launches.

    Reads the teacher's name and recent context from config.json to
    personalize the greeting. Instant — no LLM call, pure Python.
    The teacher sees Ed's voice before the cursor appears.
    """
    import json
    import random

    _cfg_dir = _data_dir()
    config_path = Path(_cfg_dir) / "config.json"
    name = "there"
    try:
        if config_path.exists():
            data = json.loads(config_path.read_text())
            tp = data.get("teacher_profile", {})
            raw = tp.get("name", "")
            if raw:
                # Use just the last name with title, or first name
                parts = raw.strip().split()
                if len(parts) >= 2 and parts[0] in ("Mr.", "Ms.", "Mrs.", "Dr.", "Mr", "Ms", "Mrs", "Dr"):
                    name = " ".join(parts[:2])
                else:
                    name = parts[0]
    except (KeyError, FileNotFoundError, json.JSONDecodeError):
        pass  # Greeting personalization is cosmetic; fall back to default name

    greetings = [
        f"Hey {name}! What are we working on today?",
        f"Good to see you, {name}. What do you need?",
        f"Hey {name}! Ready when you are.",
        f"Welcome back, {name}. What's on the agenda?",
    ]

    print(f"\n  \033[32m🍎 {random.choice(greetings)}\033[0m\n")


def _show_node_notice() -> None:
    """Show clean branded startup banner.

    Displays the Claw-ED logo, version, teacher name, and KB stats.
    """
    import json

    from clawed import __version__

    _cfg_dir = _data_dir()
    config_path = Path(_cfg_dir) / "config.json"
    name = ""
    model = ""
    try:
        if config_path.exists():
            data = json.loads(config_path.read_text())
            tp = data.get("teacher_profile", {})
            name = tp.get("name", "")
            provider = data.get("provider", "")
            model = data.get(f"{provider}_model", "") if provider else ""
    except (KeyError, FileNotFoundError, json.JSONDecodeError):
        pass  # Banner display is cosmetic; proceed with defaults

    print()
    print("  🍎 C L A W - E D")
    print(f"  Your AI co-teacher  v{__version__}")
    if name:
        print(f"  \033[32m{name}\033[0m", end="")
        if model:
            print(f"  \033[90m· {model}\033[0m", end="")
        print()
    print()


def _maybe_start_bot_background() -> None:
    """Auto-start the Telegram bot as a background subprocess if configured.

    Checks for a Telegram token in config and a bot.lock file.
    If the token exists and no bot is running, spawns `python -m clawed bot`
    as a detached process. The bot runs silently in the background —
    the teacher never needs to open a second terminal.
    """
    if not _check_telegram_token():
        return

    _cfg_dir = os.environ.get("EDUAGENT_DATA_DIR", str(Path.home() / ".eduagent"))
    lock_file = Path(_cfg_dir) / "bot.lock"

    # Check if a bot is already running
    if lock_file.exists():
        try:
            pid = int(lock_file.read_text(encoding="utf-8").strip())
            # Check if PID is alive
            if sys.platform == "win32":
                result = subprocess.run(
                    ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                    capture_output=True, text=True, timeout=5,
                )
                if str(pid) in result.stdout:
                    return  # Bot already running
            else:
                os.kill(pid, 0)  # Raises OSError if dead
                return  # Bot already running
        except (ValueError, OSError, subprocess.TimeoutExpired):
            # Stale lock — continue to start a new bot
            with contextlib.suppress(OSError):
                lock_file.unlink()

    # Spawn bot as detached background process
    try:
        python = sys.executable
        if sys.platform == "win32":
            # Windows: detached, no console window
            subprocess.Popen(
                [python, "-m", "clawed", "bot"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                creationflags=0x08000000 | 0x00000008,  # CREATE_NO_WINDOW | DETACHED_PROCESS
            )
        else:
            # Unix: nohup-style detached
            subprocess.Popen(
                [python, "-m", "clawed", "bot"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )
    except (ImportError, OSError):
        pass  # Never block the CLI — bot is best-effort


def _check_telegram_token() -> bool:
    """Return True if a Telegram bot token is configured, False otherwise.

    Checks config.json first, then keyring, then env var.
    """
    import json

    _cfg_dir = os.environ.get("EDUAGENT_DATA_DIR", str(Path.home() / ".eduagent"))
    config_path = Path(_cfg_dir) / "config.json"

    # 1. Check config.json (fastest, no imports)
    if config_path.exists():
        try:
            data = json.loads(config_path.read_text())
            token = data.get("telegram_bot_token", "")
            if token and token.strip():
                return True
        except (json.JSONDecodeError, OSError):
            pass

    # 2. Check environment variable
    if os.environ.get("TELEGRAM_BOT_TOKEN"):
        return True

    # 3. Check keyring (slower, may not be installed)
    try:
        from clawed.config import get_api_key
        token = get_api_key("telegram")
        if token and token.strip():
            return True
    except (ImportError, KeyError, FileNotFoundError):
        pass  # Token check is best-effort; absence means "not configured"

    return False


def _resolve_key_for_provider(provider: str, config: dict[str, object]) -> str | None:
    """Find the best API key for a provider using a 5-step resolution chain.

    Checks in order: environment variable, Claude Code OAuth credentials,
    OS keyring, secrets.json, and inline config fields. Returns the first
    match or None if no key is found anywhere.
    """
    import json

    # 1. Already in env? User knows what they're doing — skip.
    env_map = {
        "anthropic": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
        "google": "GOOGLE_API_KEY",
        "ollama": "OLLAMA_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
    }
    env_var = env_map.get(provider)
    if env_var and os.environ.get(env_var):
        return os.environ[env_var]

    # 2. Anthropic: try Claude Code OAuth credentials
    if provider == "anthropic":
        for cred_path in [
            Path.home() / ".claude" / ".credentials.json",
            Path.home() / ".claude" / "credentials.json",
        ]:
            if cred_path.exists():
                try:
                    creds = json.loads(cred_path.read_text())
                    token = creds.get("claudeAiOauth", {}).get("accessToken")
                    if token:
                        return str(token)
                except (json.JSONDecodeError, OSError):
                    pass

    # 3. Keyring
    try:
        import keyring
        val = keyring.get_password("eduagent", f"{provider}_api_key")
        if val:
            return str(val)
    except ImportError:
        pass  # keyring is optional; fall through to secrets.json/env

    # 4. secrets.json
    secrets_path = Path(_data_dir()) / "secrets.json"
    if secrets_path.exists():
        try:
            secrets = json.loads(secrets_path.read_text())
            val = secrets.get(f"{provider}_api_key")
            if val:
                return str(val)
        except (json.JSONDecodeError, OSError):
            pass

    # 5. Inline in config (e.g. ollama_api_key field)
    key_field = f"{provider}_api_key"
    val = config.get(key_field)
    if val and val != "ollama-local":  # Skip sentinel value
        return str(val)

    return None


def _inject_config_env() -> None:
    """Inject teacher's config into env vars so the Node CLI can authenticate.

    Reads ~/.eduagent/config.json and resolves the API key for the active
    provider, then sets the appropriate env var (ANTHROPIC_API_KEY, etc.)
    so the TS CLI picks it up instead of falling back to settings.json.

    Never crashes — a failure here just means the TS CLI tries its own
    auth flow (which may or may not work).
    """
    import json

    config_path = Path(_data_dir()) / "config.json"
    if not config_path.exists():
        return  # First run — let onboarding handle it

    try:
        config = json.loads(config_path.read_text())
    except (json.JSONDecodeError, OSError):
        return

    provider = config.get("provider", "anthropic")
    os.environ.setdefault("CLAWED_PROVIDER", provider)

    # Resolve API key for the active provider
    key = _resolve_key_for_provider(provider, config)
    if key:
        env_var_map = {
            "anthropic": "ANTHROPIC_API_KEY",
            "openai": "OPENAI_API_KEY",
            "google": "GOOGLE_API_KEY",
            "ollama": "OLLAMA_API_KEY",
            "openrouter": "OPENROUTER_API_KEY",
        }
        env_var = env_var_map.get(provider)
        if env_var:
            os.environ.setdefault(env_var, key)
        # Google needs both GOOGLE_API_KEY and GEMINI_API_KEY
        if provider == "google":
            os.environ.setdefault("GEMINI_API_KEY", key)

    # Ollama base URL so the TS bridge knows where to connect
    if provider == "ollama":
        base = config.get("ollama_base_url", "")
        if base:
            os.environ.setdefault("OLLAMA_BASE_URL", base)


def _get_configured_model() -> str | None:
    """Read the teacher's chosen model from ~/.eduagent/config.json.

    Looks up the provider-specific model field (e.g. anthropic_model,
    openai_model) based on the active provider. Uses only stdlib imports
    so this runs before any third-party packages are loaded.
    """
    import json

    config_path = Path(_data_dir()) / "config.json"
    if not config_path.exists():
        return None
    try:
        config = json.loads(config_path.read_text())
    except (json.JSONDecodeError, OSError):
        return None

    provider = config.get("provider", "anthropic")
    # Each provider has its own model field
    model_fields = {
        "anthropic": "anthropic_model",
        "openai": "openai_model",
        "google": "google_model",
        "ollama": "ollama_model",
        "openrouter": "openrouter_model",
    }
    field = model_fields.get(provider)
    if field:
        value = config.get(field)
        return str(value) if value else None
    return None


def _handle_daemon(args: list[str]) -> None:
    """Route daemon subcommands to the Node.js daemon process.

    Validates that Node.js is installed and the daemon entry point exists,
    checks for a configured Telegram token, then executes the daemon with
    the provided arguments. Exits the process with the daemon's return code.
    """
    node = shutil.which("node")
    daemon_entry = _find_daemon_entry()

    if not node:
        print("The Telegram bot requires Node.js. Install from https://nodejs.org and try again.")
        sys.exit(1)

    if not daemon_entry:
        print("Telegram bot files not found. Try reinstalling: pip install --force-reinstall clawed")
        sys.exit(1)

    # Pre-check: Telegram token must be configured before spawning the daemon
    if not _check_telegram_token():
        print(
            "\nNo Telegram bot token found.\n"
            "\n"
            "To set up Telegram:\n"
            "1. Open Telegram and message @BotFather\n"
            "2. Send /newbot and follow the steps\n"
            "3. Copy the bot token\n"
            "4. Run: clawed config set-token --telegram YOUR_TOKEN\n"
        )
        sys.exit(0)

    # Check if it's a .ts file (dev mode) — use tsx or ts-node
    if daemon_entry.endswith(".ts"):
        tsx = shutil.which("tsx")
        if tsx:
            result = subprocess.run([tsx, daemon_entry, *args])
        else:
            result = subprocess.run([node, "--loader", "ts-node/esm", daemon_entry, *args])
    else:
        result = subprocess.run([node, daemon_entry, *args])

    sys.exit(result.returncode)


def main() -> None:
    """Entry point for the `clawed` command.

    Currently routes to the Python CLI for all interactive use.
    The TypeScript Ink TUI is available for --version only.
    """
    args = sys.argv[1:]

    # Route daemon commands to the Node.js daemon
    if args and args[0] == "daemon":
        _handle_daemon(args[1:])
        return

    # Allow forcing Python CLI
    if "--python" in args:
        args.remove("--python")
        sys.argv = [sys.argv[0], *args]

    # Python CLI subcommands — these are typer commands that should NEVER
    # go through the Node CLI (which would interpret them as chat prompts)
    python_commands = {
        "setup", "debug", "config", "ingest", "lesson", "unit", "full",
        "course", "materials", "assess", "rubric", "score", "improve",
        "evaluate", "differentiate", "sub-packet", "parent-note",
        "gap-analyze", "export", "share", "import", "demo", "train",
        "tui", "chat", "student-chat", "mcp-server", "serve", "bot",
        "student-bot", "sub", "parent-comm", "stats", "status",
        "persona", "standards", "templates", "skills", "school",
        "class", "queue", "workspace", "kb", "schedule", "game",
        "simulate", "generate-landing", "landing", "transcribe",
        "pacing", "year-map",
    }

    # Route known subcommands to Python CLI directly
    if args and args[0] in python_commands:
        sys.argv = [sys.argv[0], *args]
        _run_python_cli()
        return

    # For non-Anthropic providers, handle -p (headless/print) directly
    # because the Node CLI only supports Anthropic for direct API calls
    if args and ("-p" in args or "--print" in args):
        try:
            import json as _json
            _cfg_path = Path(_data_dir()) / "config.json"
            if _cfg_path.exists():
                _cfg = _json.loads(_cfg_path.read_text())
                if _cfg.get("provider", "anthropic") != "anthropic":
                    # Extract the prompt from args (everything after -p)
                    prompt_parts = []
                    skip_next = False
                    for a in args:
                        if skip_next:
                            skip_next = False
                            continue
                        if a in ("-p", "--print"):
                            continue
                        if a.startswith("--"):
                            skip_next = True
                            continue
                        prompt_parts.append(a)
                    prompt = " ".join(prompt_parts)
                    if prompt:
                        import asyncio

                        from clawed.llm import LLMClient
                        from clawed.models import AppConfig
                        cfg = AppConfig.load()
                        client = LLMClient(config=cfg)
                        response = asyncio.run(client.generate(prompt))
                        print(response)
                        sys.exit(0)
        except (ImportError, AttributeError, ValueError, OSError) as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    # ── First-run check ────────────────────────────────────────────────
    # If no config exists, the teacher has never set up Claw-ED.
    # Run the Python onboarding wizard BEFORE anything else, even if
    # the teacher passed a command or prompt as args.
    _cfg_dir = os.environ.get("EDUAGENT_DATA_DIR", str(Path.home() / ".eduagent"))
    config_path = Path(_cfg_dir) / "config.json"
    # Skip onboarding for info-only flags
    _info_flags = {"--version", "-v", "--help", "-h"}
    if not config_path.exists() and not (args and set(args) & _info_flags):
        # First run — show branded intro then setup wizard
        import time as _time

        from clawed import __version__
        print()
        print("  \033[32m🍎 C L A W - E D\033[0m")
        print(f"  \033[1mYour AI co-teacher\033[0m  v{__version__}")
        print()
        _time.sleep(1)
        try:
            from clawed.onboarding import quick_model_setup
            setup_result = quick_model_setup()
            if setup_result == "telegram":
                sys.argv = [sys.argv[0], "bot"]
                _run_python_cli()
                return
            # Terminal mode — fall through to TUI launch
        except (ImportError, AttributeError, OSError, KeyError) as e:
            print(f"Setup error: {e}", file=sys.stderr)

    # Auto-start Telegram bot in background if configured
    _maybe_start_bot_background()

    # Use the Ink TUI for interactive mode — the full Claw-ED TUI
    node = shutil.which("node")
    cli_js = _find_bundled_cli_js()

    if node and cli_js:
        os.environ['CLAWED_MODE'] = '1'
        # Increase Node.js heap for large curriculum ingestion (default 4GB is too small)
        existing = os.environ.get('NODE_OPTIONS', '')
        if '--max-old-space-size' not in existing:
            os.environ['NODE_OPTIONS'] = f'{existing} --max-old-space-size=8192'.strip()
        try:
            _inject_config_env()
        except Exception:
            logger.debug("startup_probe_failed", exc_info=True)

        # Permission bypass: DISABLED by default (F3 audit fix).
        # Teachers must explicitly opt in via CLAWED_AUTO_APPROVE=1 env var
        # or auto_approve_tools=true in config.json.
        # When bypassed, only read_only tools skip confirmation.
        import os as _os
        _auto = _os.environ.get("CLAWED_AUTO_APPROVE", "").lower() in ("1", "true", "yes")
        if not _auto:
            try:
                from clawed.models import AppConfig
                _auto = getattr(AppConfig.load(), "auto_approve_tools", False)
            except (FileNotFoundError, json.JSONDecodeError, KeyError):
                _auto = False  # Config load failure means no bypass
        if _auto and "--dangerously-skip-permissions" not in args:
            args = ["--dangerously-skip-permissions", *args]
            import sys as _sys
            print(
                "\u26a0\ufe0f  Permission bypass ACTIVE (CLAWED_AUTO_APPROVE=1). "
                "Sensitive tools still require approval via the central policy layer.",
                file=_sys.stderr,
            )

        # Inject --model from eduagent config so the Node CLI uses the
        # teacher's chosen model instead of defaulting to haiku
        if "--model" not in args:
            try:
                model = _get_configured_model()
                if model:
                    args = ["--model", model, *args]
            except (KeyError, FileNotFoundError, json.JSONDecodeError):
                pass  # Model config is best-effort; Node CLI has its own default

        # Ed speaks first — proactive greeting before the TUI cursor appears.
        # This runs from Python (instant, no LLM call) so the teacher sees
        # Ed's voice before they need to type anything.
        if not args:
            _ed_greeting()

        result = subprocess.run([node, cli_js, *args])
        sys.exit(result.returncode)
    else:
        if not args:
            _show_node_notice()
        _run_python_cli()


def _run_python_cli() -> None:
    """Run the Python typer CLI as the command handler.

    Used when Node.js is unavailable, the teacher passes --python,
    or the command is a known Python subcommand (setup, lesson, etc.).
    """
    from clawed.cli import app
    app()


if __name__ == "__main__":
    main()
