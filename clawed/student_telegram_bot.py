"""Backward compatibility — import from clawed.transports.student_telegram."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from clawed.transports.student_telegram import *  # noqa: F401, F403
from clawed.transports.student_telegram import (  # noqa: F401
    STUDENT_BOT_COMMANDS,
    StudentTelegramBot,
    _get_session,
    _get_student_store,
    _persist_student_session,
    _student_sessions,
    _student_state_store,
    run_student_bot,
)


# Keep a local _ERROR_LOG so tests can patch it on this module
def _error_log_path() -> Path:
    from clawed.paths import data_dir

    return data_dir() / "student_errors.log"


_ERROR_LOG = _error_log_path()


def _log_error(error: Exception) -> None:
    """Backward-compat _log_error that uses this module's _ERROR_LOG."""
    try:
        _ERROR_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(_ERROR_LOG, "a") as f:
            import datetime

            f.write(f"[{datetime.datetime.now(datetime.timezone.utc).isoformat()}] {type(error).__name__}: {error}\n")
    except Exception:
        pass


async def _send_response(update: Any, text: str) -> None:
    """Backward-compat async _send_response matching the old signature."""
    if len(text) <= 4096:
        await update.message.reply_text(text)
    else:
        for chunk in [text[i : i + 4000] for i in range(0, len(text), 4000)]:
            await update.message.reply_text(chunk)
