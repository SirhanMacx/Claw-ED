"""Structured JSON output for CLI commands.

Every command that supports --json uses this module to produce
a standard envelope: {status, command, data, files, warnings, errors}.
"""

from __future__ import annotations

import json
import sys
import traceback
from typing import Any


def json_envelope(
    command: str,
    *,
    status: str = "success",
    data: Any = None,
    files: list[str] | None = None,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
) -> dict[str, Any]:
    """Build a standard JSON envelope."""
    return {
        "status": status,
        "command": command,
        "data": data,
        "files": files or [],
        "warnings": warnings or [],
        "errors": errors or [],
    }


def emit_json(envelope: dict[str, Any]) -> None:
    """Write JSON envelope to stdout and flush."""
    json.dump(envelope, sys.stdout, default=str)
    sys.stdout.write("\n")
    sys.stdout.flush()


def run_json_command(command: str, fn, **kwargs) -> None:
    """Run a function and emit its result as JSON.

    fn must return a dict with optional keys: data, files, warnings.
    On exception, emits error envelope.
    """
    try:
        result = fn(**kwargs)
        if result is None:
            result = {}
        envelope = json_envelope(
            command,
            data=result.get("data"),
            files=result.get("files", []),
            warnings=result.get("warnings", []),
        )
    except Exception as e:
        envelope = json_envelope(
            command,
            status="error",
            errors=[str(e), traceback.format_exc()],
        )
    emit_json(envelope)
