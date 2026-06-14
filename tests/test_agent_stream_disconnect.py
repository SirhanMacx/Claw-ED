"""A turn whose SSE client disconnects must finish in the background, not be
cancelled — otherwise a dropped phone stream loses the in-flight lesson."""
from __future__ import annotations

import asyncio

from clawed.api.routes.agent_stream import _BACKGROUND_TASKS, _detach_to_background


async def test_detached_task_runs_to_completion_not_cancelled() -> None:
    wrote = {}

    async def slow_turn() -> str:
        await asyncio.sleep(0.15)
        wrote["done"] = True  # the "lesson write" that must still happen
        return "ok"

    task = asyncio.create_task(slow_turn())
    # Simulate the SSE finally-block on client disconnect.
    _detach_to_background(task)

    assert task in _BACKGROUND_TASKS  # strong ref held (not GC'd)
    assert not task.cancelled()

    result = await task
    assert result == "ok"
    assert wrote.get("done") is True  # the work completed despite "disconnect"
    assert task not in _BACKGROUND_TASKS  # done-callback cleaned it up
