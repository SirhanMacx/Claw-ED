"""Proactive scheduler -- wires EduScheduler to the agent gateway.

AgentScheduler wraps the lower-level schedule config helpers and presents
a clean interface for the gateway, tools, and tests.  When a scheduled
task fires, the gateway's ``handle_system_event()`` routes it through the
agent loop so Claw-ED can reason about what to do.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class AgentScheduler:
    """Wraps EduScheduler and routes task execution through the gateway."""

    def __init__(self) -> None:
        from clawed.scheduler import load_schedule_config

        self._config = load_schedule_config()

    # -- Query ----------------------------------------------------------------

    def get_tasks(self) -> list[dict[str, Any]]:
        """Return list of all scheduled tasks with their config."""
        tasks: list[dict[str, Any]] = []
        for name, cfg in self._config.items():
            tasks.append(
                {
                    "name": name,
                    "enabled": cfg.get("enabled", False),
                    "schedule": cfg.get("cron", {}),
                    "description": cfg.get("description", ""),
                }
            )
        return tasks

    # -- Mutate ---------------------------------------------------------------

    def enable_task(self, task_name: str) -> None:
        """Enable a scheduled task by name."""
        from clawed.scheduler import enable_task

        enable_task(task_name)
        self._config = self._reload_config()

    def disable_task(self, task_name: str) -> None:
        """Disable a scheduled task by name."""
        from clawed.scheduler import disable_task

        disable_task(task_name)
        self._config = self._reload_config()

    def set_schedule(self, task_name: str, schedule: str) -> None:
        """Update a task's cron schedule from a simplified expression."""
        from clawed.scheduler import set_task_schedule

        set_task_schedule(task_name, schedule)
        self._config = self._reload_config()

    # -- Internal -------------------------------------------------------------

    @staticmethod
    def _reload_config() -> dict[str, dict[str, Any]]:
        from clawed.scheduler import load_schedule_config

        return load_schedule_config()
