"""Backward-compat shim — redirects to clawed.transports.hermes.

All functionality moved to hermes.py as part of the
OpenClaw → Hermes Agent migration (2026-03-30).
"""

from clawed.transports.hermes import (  # noqa: F401
    _get_gateway,
    handle_callback,
    handle_message,
    handle_message_sync,
)
