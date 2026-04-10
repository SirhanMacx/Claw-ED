"""Backward-compat shim — redirects to clawed.hermes_plugin.

All functionality moved to hermes_plugin.py as part of the
OpenClaw → Hermes Agent migration (2026-03-30).
"""

from clawed.hermes_plugin import (  # noqa: F401
    _fmt_lesson_summary,
    _fmt_persona,
    _fmt_unit_summary,
    _show_status,
    _transcribe_attachments,
    get_last_lesson_id,
    handle_message,
)

__all__ = [
    "_fmt_lesson_summary",
    "_fmt_persona",
    "_fmt_unit_summary",
    "get_last_lesson_id",
    "handle_message",
    "_show_status",
    "_transcribe_attachments",
]
