"""Tool: read_heartbeat — read the agent's schedule from HEARTBEAT.md."""

from __future__ import annotations

from typing import Any

from clawed.agent_core.context import AgentContext, ToolResult

HEARTBEAT_TEMPLATE = """\
# Heartbeat

## Morning Prep (6:00 AM school days)
- [ ] Check today's schedule
- [ ] Review any unfinished lessons for today
- [ ] Draft missing lessons
- [ ] Send daily summary via Telegram

## Weekly Planning (Sunday 7:00 PM)
- [ ] Draft next week's lesson sequence
- [ ] Check pacing against unit plan
- [ ] Flag any standards gaps

## Feedback Digest (8:00 PM daily)
- [ ] Summarize today's ratings and student questions
- [ ] Update SOUL.md with what worked and what didn't
"""


class ReadHeartbeatTool:
    """Read the agent's schedule and autonomous task list from HEARTBEAT.md."""

    risk_level = "read_only"

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "read_heartbeat",
                "description": (
                    "Read the agent's schedule and autonomous task list "
                    "from HEARTBEAT.md. Returns the current schedule "
                    "including morning prep, weekly planning, and feedback tasks."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        }

    async def execute(self, params: dict[str, Any], context: AgentContext) -> ToolResult:
        from clawed.paths import workspace_dir

        heartbeat_path = workspace_dir() / "HEARTBEAT.md"

        if not heartbeat_path.exists():
            # Create from default template
            heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
            heartbeat_path.write_text(HEARTBEAT_TEMPLATE, encoding="utf-8")
            return ToolResult(
                text=HEARTBEAT_TEMPLATE,
                side_effects=["Created default HEARTBEAT.md"],
            )

        try:
            content = heartbeat_path.read_text(encoding="utf-8")
            return ToolResult(text=content)
        except Exception as e:
            return ToolResult(text=f"Failed to read HEARTBEAT.md: {e}")
