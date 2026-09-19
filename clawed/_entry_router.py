"""One owned Python entry point for all Claw-ED interfaces."""
from __future__ import annotations

import asyncio
import sys


def _run_python_cli() -> None:
    from clawed.cli import app
    app()


def main() -> None:
    args = sys.argv[1:]
    if args in (["--version"], ["-v"], ["-V"]):
        from clawed import __version__
        print(f"{__version__} (Claw-ED)")
        return
    if "--python" in args:
        args.remove("--python")
    if args and args[0] in ("-p", "--print"):
        if len(args) != 2 or not args[1].strip():
            raise SystemExit('Usage: clawed -p "your request"')
        from clawed.agent_core.core import Gateway
        from clawed.agent_core.identity import get_teacher_id
        result = asyncio.run(Gateway().handle(args[1], get_teacher_id(), transport="cli"))
        print(result.text)
        return
    if args and args[0] == "daemon":
        raise SystemExit("Use clawed bot for the Python Telegram transport; run it under your service manager.")
    sys.argv = [sys.argv[0], *args]
    _run_python_cli()
