"""Schedule management handler. Extracted from tg.py lines 948-1026."""

from __future__ import annotations

import logging

from clawed.gateway_response import GatewayResponse
from clawed.scheduler import disable_task, load_schedule_config

logger = logging.getLogger(__name__)


def _cron_to_human(cron: dict) -> str:
    hour = int(cron.get("hour", 0))
    minute = int(cron.get("minute", 0))
    day = cron.get("day_of_week", "")
    ampm = "AM" if hour < 12 else "PM"
    display_hour = hour if hour <= 12 else hour - 12
    if display_hour == 0:
        display_hour = 12
    time_str = f"{display_hour}:{minute:02d} {ampm}"
    if day:
        return f"{day.title()} at {time_str}"
    return f"Daily at {time_str}"


class ScheduleHandler:
    async def show(self, teacher_id: str) -> GatewayResponse:
        config = load_schedule_config()
        tasks = config.get("tasks", {})
        if not tasks:
            return GatewayResponse(text="No scheduled tasks configured.")
        lines = ["Your scheduled tasks:\n"]
        for name, task in tasks.items():
            status = "enabled" if task.get("enabled") else "disabled"
            cron = task.get("cron", {})
            time_str = _cron_to_human(cron) if cron else "not set"
            lines.append(f"  {name}: {status} ({time_str})")
        return GatewayResponse(text="\n".join(lines))

    async def disable(self, teacher_id: str, task_name: str) -> GatewayResponse:
        try:
            disable_task(task_name)
            return GatewayResponse(text=f"Disabled '{task_name}'.")
        except Exception as e:
            return GatewayResponse(text=f"Could not disable '{task_name}': {e}")

    async def enable(self, teacher_id: str, task_name: str, time_str: str = "") -> GatewayResponse:
        from clawed.scheduler import enable_task, set_task_schedule

        enable_task(task_name)
        if time_str:
            set_task_schedule(task_name, time_str)
        return GatewayResponse(text=f"Enabled '{task_name}'.")
