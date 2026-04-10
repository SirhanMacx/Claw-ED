"""Tool: schedule_task — list, enable, disable, and reschedule agent tasks."""

from __future__ import annotations

from typing import Any

from clawed.agent_core.context import AgentContext, ToolResult


class ScheduleTaskTool:
    """Manage the agent's proactive scheduled tasks."""

    risk_level = "read_only"

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "schedule_task",
                "description": (
                    "Manage proactive scheduled tasks. "
                    "List all tasks, enable or disable a task by name, "
                    "or update a task's cron schedule."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["list", "enable", "disable", "set_schedule"],
                            "description": "The action to perform.",
                        },
                        "task_name": {
                            "type": "string",
                            "description": ("Name of the task (required for enable, disable, and set_schedule)."),
                        },
                        "schedule": {
                            "type": "string",
                            "description": (
                                "Cron schedule expression for set_schedule. "
                                "Accepts simplified formats like '6:00', "
                                "'sun 19:00', or 'hour=6 minute=0'."
                            ),
                        },
                    },
                    "required": ["action"],
                },
            },
        }

    async def execute(self, params: dict[str, Any], context: AgentContext) -> ToolResult:
        from clawed.agent_core.scheduler import AgentScheduler

        action = params.get("action", "list")
        task_name = params.get("task_name", "")
        schedule = params.get("schedule", "")

        scheduler = AgentScheduler()

        if action == "list":
            return self._list_tasks(scheduler)

        if action in ("enable", "disable", "set_schedule") and not task_name:
            return ToolResult(text=f"Action '{action}' requires a 'task_name' parameter.")

        if action == "enable":
            return self._enable_task(scheduler, task_name)

        if action == "disable":
            return self._disable_task(scheduler, task_name)

        if action == "set_schedule":
            if not schedule:
                return ToolResult(text="Action 'set_schedule' requires a 'schedule' parameter.")
            return self._set_schedule(scheduler, task_name, schedule)

        return ToolResult(text=f"Unknown action: {action}")

    # -- Private helpers -----------------------------------------------------

    @staticmethod
    def _list_tasks(scheduler: Any) -> ToolResult:
        tasks = scheduler.get_tasks()
        if not tasks:
            return ToolResult(text="No scheduled tasks configured.", data={"tasks": []})

        lines = [f"Scheduled tasks ({len(tasks)}):"]
        for t in tasks:
            status = "enabled" if t["enabled"] else "disabled"
            cron = t.get("schedule", {})
            cron_str = " ".join(f"{k}={v}" for k, v in cron.items()) if cron else "—"
            lines.append(f"  {t['name']} [{status}] cron: {cron_str}")
            if t.get("description"):
                lines.append(f"    {t['description']}")
        return ToolResult(text="\n".join(lines), data={"tasks": tasks})

    @staticmethod
    def _enable_task(scheduler: Any, task_name: str) -> ToolResult:
        try:
            scheduler.enable_task(task_name)
            return ToolResult(
                text=f"Task '{task_name}' enabled.",
                side_effects=[f"enabled-task:{task_name}"],
            )
        except Exception as e:
            return ToolResult(text=f"Failed to enable task '{task_name}': {e}")

    @staticmethod
    def _disable_task(scheduler: Any, task_name: str) -> ToolResult:
        try:
            scheduler.disable_task(task_name)
            return ToolResult(
                text=f"Task '{task_name}' disabled.",
                side_effects=[f"disabled-task:{task_name}"],
            )
        except Exception as e:
            return ToolResult(text=f"Failed to disable task '{task_name}': {e}")

    @staticmethod
    def _set_schedule(scheduler: Any, task_name: str, schedule: str) -> ToolResult:
        try:
            scheduler.set_schedule(task_name, schedule)
            return ToolResult(
                text=f"Task '{task_name}' schedule updated to '{schedule}'.",
                side_effects=[f"rescheduled-task:{task_name}"],
            )
        except Exception as e:
            return ToolResult(text=f"Failed to update schedule for '{task_name}': {e}")
