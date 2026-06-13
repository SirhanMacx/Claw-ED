"""Core data types for the agent system."""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from clawed.models import AppConfig

logger = logging.getLogger(__name__)


@dataclass
class AgentContext:
    """Passed to every tool — the agent's working state."""

    teacher_id: str
    config: AppConfig
    teacher_profile: dict[str, Any]
    persona: dict[str, Any] | None
    session_history: list[dict[str, Any]]
    improvement_context: str
    agent_name: str = "Claw-ED"
    transport: str = "cli"
    # True when this turn arrived over the public tunnel (the iPhone remote),
    # as opposed to genuine loopback (the Mac app / CLI on this machine).
    # Remote turns are held to a stricter approval policy: no standing
    # "Always allow" grants are honored or created, and auto-approve never
    # applies — every risky action is confirmed fresh on the device. This
    # means a leaked device token cannot yield blanket shell/file access.
    is_remote: bool = False
    progress_callback: Callable[[str], None] | None = None
    # Live-transport event sink (SSE chat stream). When set, the loop emits
    # tool_start / tool_end / approval_required events and blocked tools may
    # pause for an interactive teacher decision instead of failing closed.
    event_callback: Callable[[str, dict[str, Any]], None] | None = None

    def notify_progress(self, message: str) -> None:
        """Send a progress update to the user if a callback is registered."""
        if self.progress_callback:
            try:
                self.progress_callback(message)
            except Exception as e:
                logger.debug("Progress notification failed: %s", e)

    def emit_event(self, event_type: str, data: dict[str, Any]) -> None:
        """Emit a structured live event to the UI if a sink is registered.

        Never raises — a UI hiccup must not break the agent loop.
        """
        if self.event_callback:
            try:
                self.event_callback(event_type, data)
            except Exception as e:
                logger.debug("Event emit failed (%s): %s", event_type, e)


@dataclass
class ToolResult:
    """What a tool returns to the agent."""

    text: str = ""
    files: list[Path] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)
    side_effects: list[str] = field(default_factory=list)
