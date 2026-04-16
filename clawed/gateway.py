"""Feature-flag shim -- routes to legacy or agent gateway.

Re-exports all public names from the legacy gateway so existing
imports (EduAgentGateway, ActivityEvent, GatewayStats) keep working.
"""
from __future__ import annotations

from typing import Any

from clawed._legacy_gateway import (  # noqa: F401
    ActivityEvent,
    GatewayStats,
)
from clawed.models import AppConfig


def Gateway(*args: Any, **kwargs: Any) -> Any:  # noqa: N802
    """Factory that returns the appropriate Gateway based on config."""
    config = kwargs.get("config") or (args[0] if args else None)
    if config is None:
        config = AppConfig.load()

    if getattr(config, "agent_gateway", False):
        from clawed.agent_core.core import Gateway as AgentGateway
        # Forward extra kwargs (e.g. llm=) to the agent gateway
        fwd = {k: v for k, v in kwargs.items() if k != "config"}
        return AgentGateway(config=config, **fwd)

    from clawed._legacy_gateway import Gateway as LegacyGateway
    return LegacyGateway(config=config)


# Backward compatibility alias
EduAgentGateway = Gateway
