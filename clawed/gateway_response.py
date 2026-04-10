"""Transport-agnostic response type for the Claw-ED gateway.

Every handler returns a GatewayResponse. Transports render it:
  - Telegram: send_message + send_document + reply_markup
  - Web API: JSON serialization
  - CLI: rich.print + file paths
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Button:
    """An action button that transports render as inline keyboards, HTML buttons, etc."""

    label: str
    callback_data: str
    url: str | None = None


@dataclass
class GatewayResponse:
    """What the gateway returns to any transport."""

    text: str = ""
    files: list[Path] = field(default_factory=list)
    buttons: list[Button] = field(default_factory=list)
    button_rows: list[list[Button]] = field(default_factory=list)
    typing: bool = False
    progress: str = ""

    @property
    def has_content(self) -> bool:
        return bool(self.text or self.files)

    @classmethod
    def empty(cls) -> GatewayResponse:
        return cls()
