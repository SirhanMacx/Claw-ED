"""Core data types for the agent system."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

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
    progress_callback: Optional[Callable[[str], None]] = None

    def notify_progress(self, message: str) -> None:
        """Send a progress update to the user if a callback is registered."""
        if self.progress_callback:
            try:
                self.progress_callback(message)
            except Exception as e:
                logger.debug("Progress notification failed: %s", e)


@dataclass
class ToolResult:
    """What a tool returns to the agent."""

    text: str = ""
    files: list[Path] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)
    side_effects: list[str] = field(default_factory=list)
