"""Hermes Agent transport — use Claw-ED as a Hermes skill.

This lets Manfred (or any Hermes Agent) use Claw-ED tools
directly through the Hermes gateway. Teachers who already
use Hermes get Claw-ED automatically.

Usage as a Hermes skill:
    from clawed.transports.hermes import handle_message
    response = await handle_message("plan a unit on WWI", teacher_id="teacher_123")

The existing clawed/hermes_plugin.py handles the heavy lifting
(intent dispatch, state management). This transport wraps it with
Gateway.handle() for the full Claw-ED experience (onboarding,
export buttons, feedback prompts).
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Optional

from clawed.gateway import Gateway

logger = logging.getLogger(__name__)

# Singleton gateway for the Hermes transport
_gateway: Optional[Gateway] = None


def _get_gateway() -> Gateway:
    """Get or create the singleton Gateway instance."""
    global _gateway
    if _gateway is None:
        _gateway = Gateway()
    return _gateway


async def handle_message(
    message: str,
    teacher_id: str = "hermes-default",
    files: list[Path] | None = None,
) -> str:
    """Process a message through the Claw-ED gateway.

    This is the main entry point for Hermes skills.
    Returns the response text (files and buttons are logged but not returned,
    since Hermes' skill interface is text-only).
    """
    gateway = _get_gateway()
    response = await gateway.handle(message, teacher_id, files=files, transport="mcp")

    # Hermes skills return text. Log files/buttons for debugging.
    if response.files:
        logger.info("Claw-ED generated %d file(s): %s", len(response.files), [f.name for f in response.files])
    if response.button_rows or response.buttons:
        logger.debug("Claw-ED suggested actions (not rendered in Hermes)")

    return response.text


async def handle_callback(callback_data: str, teacher_id: str = "hermes-default") -> str:
    """Handle a button callback (rating, export, etc.)."""
    gateway = _get_gateway()
    response = await gateway.handle_callback(callback_data, teacher_id)
    return response.text


def handle_message_sync(
    message: str,
    teacher_id: str = "hermes-default",
    files: list[Path] | None = None,
) -> str:
    """Synchronous wrapper for handle_message (convenience for non-async callers)."""
    return asyncio.run(handle_message(message, teacher_id, files))
