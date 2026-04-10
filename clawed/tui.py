"""Claw-ED TUI — Live terminal dashboard built with Textual.

Launch:
    clawed serve --tui              # full gateway + TUI
    clawed serve --tui              # TUI only (demo, no Telegram)

The TUI subscribes to the gateway's event_bus and renders:
  - Teacher header (name, school, grades, active model)
  - Scrolling activity log with timestamps
  - Stats bar (messages, generations, errors, uptime)
  - Active session panel
  - Footer with keyboard shortcuts
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING

try:
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Horizontal
    from textual.widgets import DataTable, Footer, Static
except ImportError:
    raise ImportError(
        "textual is required for the TUI dashboard.\nInstall with: pip install 'clawed[tui]'\nOr: pip install textual"
    )

if TYPE_CHECKING:
    from clawed.gateway import EduAgentGateway


# ── Status icons ──────────────────────────────────────────────────────

_EVENT_ICONS = {
    "message_received": "\U0001f4e8",
    "generation_started": "\u2699\ufe0f",
    "generation_complete": "\u2705",
    "error": "\u274c",
    "system": "\U0001f4e1",
}


# ── Widgets ───────────────────────────────────────────────────────────


class TeacherHeader(Static):
    """Top banner: teacher identity and model info."""

    def __init__(self, gateway: EduAgentGateway, **kwargs) -> None:
        super().__init__(**kwargs)
        self._gateway = gateway

    def on_mount(self) -> None:
        cfg = self._gateway.config
        p = cfg.teacher_profile
        name = p.name or "Teacher"
        school = p.school or "Claw-ED"
        subjects = ", ".join(p.subjects) if p.subjects else "All Subjects"
        grades = f" Gr. {', '.join(p.grade_levels)}" if p.grade_levels else ""

        if cfg.provider.value == "ollama":
            model = cfg.ollama_model
        elif cfg.provider.value == "anthropic":
            model = cfg.anthropic_model
        else:
            model = cfg.openai_model
        provider = cfg.provider.value.title()

        self.update(
            f"  \U0001f393 {name}  \u00b7  {school}  \u00b7  {subjects}{grades}\n  \U0001f916 {provider} / {model}"
        )


class ActivityLog(Static):
    """Scrolling activity feed — consumes gateway event_bus."""

    def __init__(self, gateway: EduAgentGateway, **kwargs) -> None:
        super().__init__(**kwargs)
        self._gateway = gateway
        self._poll_task: asyncio.Task | None = None

    def compose(self) -> ComposeResult:
        table = DataTable(id="activity-table")
        table.cursor_type = "none"
        yield table

    def on_mount(self) -> None:
        table = self.query_one("#activity-table", DataTable)
        table.add_columns("Time", "Event", "Actor", "Message")
        self._poll_task = asyncio.create_task(self._poll_events())

    async def _poll_events(self) -> None:
        table = self.query_one("#activity-table", DataTable)
        while True:
            try:
                event = await asyncio.wait_for(self._gateway.event_bus.get(), timeout=0.5)
                ts = datetime.fromtimestamp(event.timestamp).strftime("%H:%M:%S")
                icon = _EVENT_ICONS.get(event.event_type, "\U0001f539")
                table.add_row(ts, f"{icon} {event.event_type}", event.actor, event.message[:80])
                table.move_cursor(row=table.row_count - 1)
            except TimeoutError:
                pass
            except asyncio.CancelledError:
                return
            except Exception:
                await asyncio.sleep(0.5)

    def clear_log(self) -> None:
        table = self.query_one("#activity-table", DataTable)
        table.clear()


class StatsBar(Static):
    """Bottom-left: today's numbers + uptime."""

    def __init__(self, gateway: EduAgentGateway, **kwargs) -> None:
        super().__init__(**kwargs)
        self._gateway = gateway

    def on_mount(self) -> None:
        self.set_interval(1.0, self._refresh)

    def _refresh(self) -> None:
        s = self._gateway._stats
        elapsed = int(s.uptime_seconds)
        h, remainder = divmod(elapsed, 3600)
        m, sec = divmod(remainder, 60)

        self.update(
            f"  [bold]Today[/bold]\n"
            f"  Messages:     {s.messages_today}\n"
            f"  Generations:  {s.generations_today}\n"
            f"  Errors:       {s.errors_today}\n"
            f"  Uptime:       {h}:{m:02d}:{sec:02d}"
        )


class ActivePanel(Static):
    """Bottom-right: active sessions."""

    def __init__(self, gateway: EduAgentGateway, **kwargs) -> None:
        super().__init__(**kwargs)
        self._gateway = gateway

    def on_mount(self) -> None:
        self.set_interval(2.0, self._refresh)

    def _refresh(self) -> None:
        sessions = self._gateway.active_sessions
        if not sessions:
            self.update("  [bold]Sessions[/bold]\n  No active sessions")
            return
        lines = ["  [bold]Sessions[/bold]"]
        for sid, info in list(sessions.items())[-5:]:  # last 5
            lines.append(f"  \U0001f9d1\u200d\U0001f3eb {info.get('name', sid)}")
        self.update("\n".join(lines))


# ── Main App ──────────────────────────────────────────────────────────


class EduAgentDashboard(App):
    """Claw-ED TUI — live dashboard for monitoring the gateway."""

    TITLE = "Claw-ED Dashboard"

    CSS = """
    Screen {
        layout: vertical;
        background: $surface;
    }
    #app-title {
        height: 1;
        background: $accent;
        color: $text;
        text-align: center;
        text-style: bold;
    }
    #teacher-header {
        height: 4;
        border: solid green;
        padding: 0 1;
        color: $text;
    }
    #activity-section {
        height: 1fr;
        border: solid $primary;
    }
    #activity-section DataTable {
        height: 100%;
    }
    #bottom-panels {
        height: 9;
        layout: horizontal;
    }
    #stats-bar {
        width: 1fr;
        border: solid $accent;
        padding: 0 1;
    }
    #active-panel {
        width: 1fr;
        border: solid $accent;
        padding: 0 1;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("c", "clear_log", "Clear log"),
    ]

    def __init__(self, gateway: EduAgentGateway, **kwargs) -> None:
        super().__init__(**kwargs)
        self._gateway = gateway

    def compose(self) -> ComposeResult:
        # Use a Static title bar instead of Textual's Header widget to avoid
        # HeaderTitle query mismatch across Textual versions (v0.56 → v8+).
        yield Static(f"  [bold]{self.TITLE}[/bold]", id="app-title")
        yield TeacherHeader(self._gateway, id="teacher-header")
        yield ActivityLog(self._gateway, id="activity-section")
        with Horizontal(id="bottom-panels"):
            yield StatsBar(self._gateway, id="stats-bar")
            yield ActivePanel(self._gateway, id="active-panel")
        yield Footer()

    def action_clear_log(self) -> None:
        self.query_one("#activity-section", ActivityLog).clear_log()

    def action_refresh(self) -> None:
        self.notify("Refreshed")
