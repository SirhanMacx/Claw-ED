"""Claw-ED TUI Chat — full-screen terminal transport that connects to the gateway.

Launch:
    clawed serve &                   # start the gateway in background
    clawed tui                       # connect TUI to the running gateway
    clawed tui --port 9000           # connect to a different port

This is a thin transport — it renders the UI and sends every message to
the running `clawed serve` instance over HTTP (POST /api/gateway/chat).
No Gateway instantiation, no direct LLM calls. Same pattern as the
Telegram and web transports.
"""

from __future__ import annotations

try:
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import VerticalScroll
    from textual.widgets import Footer, Input, Static
except ImportError:
    raise ImportError(
        "textual is required for the TUI chat.\n"
        "Install with: pip install 'clawed[tui]'\n"
        "Or: pip install textual"
    )

import httpx


class ChatMessage(Static):
    """A single chat message bubble."""

    DEFAULT_CSS = """
    ChatMessage {
        margin: 0 0 1 0;
        padding: 0 2;
    }
    ChatMessage.user {
        margin-left: 8;
        color: $text;
    }
    ChatMessage.assistant {
        margin-right: 8;
        color: $text;
    }
    """

    def __init__(self, role: str, text: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self._role = role
        self._text = text
        self.add_class(role)

    def compose(self) -> ComposeResult:
        label = "[bold blue]You[/bold blue]" if self._role == "user" else "[bold green]Claw-ED[/bold green]"
        yield Static(f"{label}\n{self._text}")


class ThinkingIndicator(Static):
    """Animated thinking indicator."""

    DEFAULT_CSS = """
    ThinkingIndicator {
        margin: 0 0 1 0;
        padding: 0 2;
        color: $text-muted;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._frame = 0
        self._frames = ["Thinking.", "Thinking..", "Thinking..."]

    def on_mount(self) -> None:
        self.set_interval(0.4, self._animate)

    def _animate(self) -> None:
        self._frame = (self._frame + 1) % len(self._frames)
        self.update(
            f"[bold green]Claw-ED[/bold green]  [dim]{self._frames[self._frame]}[/dim]"
        )


class ClawEDChat(App):
    """Claw-ED TUI — transport client that connects to a running gateway."""

    TITLE = "Claw-ED Chat"

    CSS = """
    Screen {
        layout: vertical;
        background: $surface;
    }
    #title-bar {
        height: 1;
        background: $accent;
        color: $text;
        text-align: center;
        text-style: bold;
    }
    #status-bar {
        height: 1;
        background: $panel;
        color: $text-muted;
        padding: 0 2;
    }
    #chat-area {
        height: 1fr;
        border: solid $primary;
        padding: 1 0;
    }
    #input-box {
        dock: bottom;
        margin: 0 1;
    }
    """

    BINDINGS = [
        Binding("escape", "quit", "Quit", priority=True),
        Binding("ctrl+l", "clear_chat", "Clear chat"),
    ]

    def __init__(
        self,
        teacher_id: str = "local-teacher",
        host: str = "127.0.0.1",
        port: int = 8000,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._teacher_id = teacher_id
        self._base_url = f"http://{host}:{port}"
        self._client = httpx.AsyncClient(base_url=self._base_url, timeout=120.0)

    def compose(self) -> ComposeResult:
        yield Static("  [bold]Claw-ED Chat[/bold]", id="title-bar")
        yield Static(
            f"  Connected to {self._base_url}  |  /quit to exit, /clear to reset",
            id="status-bar",
        )
        yield VerticalScroll(id="chat-area")
        yield Input(placeholder="Type a message... (Esc to quit)", id="input-box")
        yield Footer()

    async def on_mount(self) -> None:
        self.query_one("#input-box", Input).focus()
        # Check gateway connectivity, then trigger onboarding greeting
        try:
            await self._client.get("/api/docs", timeout=3.0)
        except httpx.ConnectError:
            chat_area = self.query_one("#chat-area", VerticalScroll)
            await chat_area.mount(
                ChatMessage(
                    "assistant",
                    f"[red]Cannot connect to gateway at {self._base_url}[/red]\n"
                    "Start the server first: [bold]clawed serve[/bold]",
                )
            )
            return
        await self._send_message("hello", auto=True)

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return

        event.input.value = ""

        if text.lower() in ("/quit", "/exit", "quit", "exit"):
            self.exit()
            return

        if text.lower() == "/clear":
            chat_area = self.query_one("#chat-area", VerticalScroll)
            await chat_area.remove_children()
            self.notify("Session cleared")
            return

        await self._send_message(text)

    async def _send_message(self, text: str, auto: bool = False) -> None:
        chat_area = self.query_one("#chat-area", VerticalScroll)
        input_box = self.query_one("#input-box", Input)

        if not auto:
            user_msg = ChatMessage("user", text)
            await chat_area.mount(user_msg)
            chat_area.scroll_end(animate=False)

        # Show thinking indicator
        thinking = ThinkingIndicator(id="thinking")
        await chat_area.mount(thinking)
        chat_area.scroll_end(animate=False)
        input_box.disabled = True

        # POST to the running gateway
        response_text = ""
        files: list[str] = []
        buttons: list[dict] = []
        try:
            resp = await self._client.post(
                "/api/gateway/chat",
                json={"message": text, "teacher_id": self._teacher_id},
            )
            if resp.status_code == 200:
                data = resp.json()
                response_text = data.get("text", "")
                files = data.get("files", [])
                buttons = data.get("buttons", [])
            else:
                response_text = f"Gateway error (HTTP {resp.status_code}): {resp.text}"
        except httpx.ConnectError:
            response_text = (
                f"[red]Lost connection to gateway at {self._base_url}[/red]\n"
                "Is `clawed serve` still running?"
            )
        except Exception as e:
            response_text = f"Something went wrong: {e}"

        # Remove thinking, show response
        await thinking.remove()
        assistant_msg = ChatMessage("assistant", response_text)
        await chat_area.mount(assistant_msg)

        for f in files:
            file_msg = ChatMessage("assistant", f"[green]File saved:[/green] {f}")
            await chat_area.mount(file_msg)

        if buttons:
            options = [b["label"] for b in buttons]
            opts_msg = ChatMessage(
                "assistant", f"[dim]Options: {' | '.join(options)}[/dim]"
            )
            await chat_area.mount(opts_msg)

        chat_area.scroll_end(animate=False)
        input_box.disabled = False
        input_box.focus()

    def action_clear_chat(self) -> None:
        """Clear chat via keybinding."""
        chat_area = self.query_one("#chat-area", VerticalScroll)
        chat_area.remove_children()
        self.notify("Session cleared")

    async def on_unmount(self) -> None:
        await self._client.aclose()


def run_tui_chat(
    teacher_id: str = "local-teacher",
    host: str = "127.0.0.1",
    port: int = 8000,
) -> None:
    """Entry point — run the TUI chat transport."""
    app = ClawEDChat(teacher_id=teacher_id, host=host, port=port)
    app.run()
