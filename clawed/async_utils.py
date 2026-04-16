"""Shared async utility for running coroutines from sync or async contexts."""
from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any


def run_async_safe(coro: Coroutine[Any, Any, Any]) -> Any:
    """Run an async coroutine, handling both sync and async calling contexts.

    When called from inside a running event loop (e.g., agent_core tools),
    uses a thread to avoid nested asyncio.run() errors.  When called from
    plain sync code (CLI), uses asyncio.run() directly.
    """
    try:
        asyncio.get_running_loop()
        # We're inside an event loop — run in a worker thread
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result(timeout=30)
    except RuntimeError:
        # No running loop — safe to use asyncio.run()
        return asyncio.run(coro)
