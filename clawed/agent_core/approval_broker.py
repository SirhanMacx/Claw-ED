"""In-memory broker for interactive (live) approval resolution.

When the teacher is present on a live transport (the Mac app / iOS remote
chat stream), a blocked tool call should PAUSE the agent loop, surface an
approval card in the UI, and resume the moment the teacher clicks
Allow / Always / Deny — exactly like Claude Code / Codex desktop.

The broker holds an asyncio.Future per pending approval id. The SSE route
emits the ``approval_required`` event; the resolve endpoint completes the
future. Approval *records* are persisted by ApprovalManager — this broker
only carries the live wakeup signal and never stores anything sensitive.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# How long an interactive approval waits before giving up and blocking.
INTERACTIVE_TIMEOUT_SECONDS = 300.0


@dataclass(frozen=True)
class ApprovalDecision:
    """The teacher's live decision for one pending approval."""

    approved: bool
    always: bool = False


class ApprovalBroker:
    """Singleton registry of live approval futures, keyed by approval id."""

    _instance: ApprovalBroker | None = None

    def __init__(self) -> None:
        self._waiters: dict[str, asyncio.Future[ApprovalDecision]] = {}

    @classmethod
    def instance(cls) -> ApprovalBroker:
        if cls._instance is None:
            cls._instance = ApprovalBroker()
        return cls._instance

    def register(self, approval_id: str) -> asyncio.Future[ApprovalDecision]:
        """Create and remember a future the agent loop will await."""
        loop = asyncio.get_event_loop()
        fut: asyncio.Future[ApprovalDecision] = loop.create_future()
        self._waiters[approval_id] = fut
        return fut

    def resolve(self, approval_id: str, decision: ApprovalDecision) -> bool:
        """Complete a pending approval. Returns True if a waiter was found."""
        fut = self._waiters.pop(approval_id, None)
        if fut is None or fut.done():
            return False
        fut.set_result(decision)
        return True

    def discard(self, approval_id: str) -> None:
        """Remove a waiter without resolving (timeout / disconnect cleanup)."""
        fut = self._waiters.pop(approval_id, None)
        if fut is not None and not fut.done():
            fut.cancel()

    def pending_ids(self) -> list[str]:
        return [k for k, f in self._waiters.items() if not f.done()]

    async def wait(
        self, approval_id: str,
        timeout: float = INTERACTIVE_TIMEOUT_SECONDS,
    ) -> ApprovalDecision | None:
        """Await the teacher's decision; None on timeout."""
        fut = self._waiters.get(approval_id)
        if fut is None:
            return None
        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        except (TimeoutError, asyncio.CancelledError):
            return None
        finally:
            self._waiters.pop(approval_id, None)
