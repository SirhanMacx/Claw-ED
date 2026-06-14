"""Streaming agent chat (SSE) + live approval resolution.

This is the chat plane for the Claw-ED desktop/iOS agent UI. Unlike
``/gateway/chat`` (blocking JSON), this endpoint streams structured
events while the agent works:

    start              {}
    progress           {message}
    tool_start         {tool_name, params}
    tool_end           {tool_name, ok, summary, files}
    command_output     {chunk}
    approval_required  {approval_id, tool_name, description, params, risk_level}
    approval_resolved  {approval_id, approved, always?}
    final              {text, files, buttons}
    error              {message}
    done               {}

Auth: same ``require_auth`` boundary as every teacher route — loopback
bypass for the Mac app, device token for the iOS remote. Never weaken.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from clawed.api.deps import _via_cloudflare_edge, limiter, require_auth

logger = logging.getLogger(__name__)

router = APIRouter(tags=["agent"])

_QUEUE_POLL_SECONDS = 0.25
_HEARTBEAT_SECONDS = 15.0

# Agent turns whose SSE client disconnected mid-task. We keep a strong reference
# so the event loop doesn't garbage-collect them — they run to completion in the
# background (writing the lesson to the Mac) rather than being cancelled.
_BACKGROUND_TASKS: set[Any] = set()


def _detach_to_background(task: Any) -> None:
    """Let a still-running agent turn finish after the client goes away.

    A teacher's phone can drop the SSE stream over the tunnel on a long task
    (lesson generation). Cancelling here would lose the in-flight work and the
    output it was about to save. Instead we let it finish server-side; a
    reconnecting client can still resolve a pending approval (the broker is
    process-wide) and the produced files land on the Mac regardless.
    """
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)
    logger.info("SSE client disconnected; agent turn continues in the background.")


def _append_approval_footer(
    text: str,
    approvals: list[dict[str, Any]],
) -> str:
    """Append authoritative approval facts recorded by the SSE stream."""
    if not approvals:
        return text

    lines = [
        "Authoritative approval log for this turn:",
    ]
    for item in approvals:
        tool = str(item.get("tool_name") or "unknown_tool")
        risk = str(item.get("risk_level") or "unknown_risk")
        approved = item.get("approved")
        if approved is True:
            status = "approved"
        elif approved is False:
            status = "denied"
        else:
            status = "pending"
        always = " (standing approval)" if item.get("always") else ""
        lines.append(f"- {tool}: {status}{always}; risk={risk}")
    footer = "\n".join(lines)

    if "Authoritative approval log for this turn:" in text:
        return text
    if text.strip():
        return f"{text.rstrip()}\n\n{footer}"
    return footer


def _get_gateway() -> Any:
    from clawed.api.routes.gateway_chat import _get_gateway as _shared
    return _shared()


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


class StreamChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=10000)


@router.post("/gateway/chat/stream", dependencies=[Depends(require_auth)])
@limiter.limit("30/minute")
async def gateway_chat_stream(request: Request, req: StreamChatRequest) -> StreamingResponse:
    """Run one agent turn, streaming live events as Server-Sent Events."""
    gateway = _get_gateway()

    from clawed.agent_core.identity import get_teacher_id
    teacher_id = get_teacher_id()

    # A turn that arrived over the public tunnel (Cf-Ray) is held to the
    # stricter remote approval policy — no standing grants, no auto-approve.
    is_remote = _via_cloudflare_edge(request)

    queue: asyncio.Queue[tuple[str, dict[str, Any]]] = asyncio.Queue(maxsize=1000)
    approval_log: dict[str, dict[str, Any]] = {}

    def event_cb(event_type: str, data: dict[str, Any]) -> None:
        if event_type == "approval_required":
            approval_id = str(data.get("approval_id") or "")
            if approval_id:
                approval_log[approval_id] = {
                    "approval_id": approval_id,
                    "tool_name": data.get("tool_name"),
                    "risk_level": data.get("risk_level"),
                    "approved": None,
                    "always": False,
                }
        elif event_type == "approval_resolved":
            approval_id = str(data.get("approval_id") or "")
            if approval_id:
                entry = approval_log.setdefault(
                    approval_id,
                    {
                        "approval_id": approval_id,
                        "tool_name": data.get("tool_name"),
                        "risk_level": data.get("risk_level"),
                    },
                )
                entry["approved"] = data.get("approved")
                entry["always"] = bool(data.get("always", False))
        try:
            queue.put_nowait((event_type, data))
        except asyncio.QueueFull:
            logger.debug("Event queue full — dropped %s", event_type)

    def progress_cb(message: str) -> None:
        event_cb("progress", {"message": str(message)})

    task = asyncio.create_task(
        gateway.handle(
            req.message, teacher_id,
            progress_callback=progress_cb,
            transport="remote" if is_remote else "app",
            event_callback=event_cb,
            is_remote=is_remote,
        ),
    )

    async def generate() -> Any:
        yield _sse("start", {})
        idle = 0.0
        try:
            while True:
                try:
                    event_type, data = await asyncio.wait_for(
                        queue.get(), timeout=_QUEUE_POLL_SECONDS,
                    )
                    idle = 0.0
                    yield _sse(event_type, data)
                    continue
                except TimeoutError:
                    idle += _QUEUE_POLL_SECONDS

                if task.done() and queue.empty():
                    break
                if idle >= _HEARTBEAT_SECONDS:
                    idle = 0.0
                    yield ": keep-alive\n\n"

            try:
                result = task.result()
            except Exception:
                logger.error("Streaming chat failed", exc_info=True)
                yield _sse("error", {"message": "Something went wrong. Please try again."})
                yield _sse("done", {})
                return

            buttons = []
            if result.button_rows or result.buttons:
                rows = result.button_rows or [result.buttons]
                buttons = [
                    {"label": b.label, "callback_data": b.callback_data, "url": b.url}
                    for row in rows for b in row
                ]
            yield _sse("final", {
                "text": _append_approval_footer(
                    result.text, list(approval_log.values()),
                ),
                "files": [str(f) for f in result.files],
                "buttons": buttons,
            })
            yield _sse("done", {})
        finally:
            # Never cancel an in-flight turn on disconnect — that loses the
            # work + the lesson it's writing. Let it finish in the background.
            if not task.done():
                _detach_to_background(task)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ── Tool registry (Skills gallery) ───────────────────────────────────


@router.get("/agent/tools", dependencies=[Depends(require_auth)])
async def list_agent_tools(request: Request) -> dict[str, Any]:
    """List the agent's real tool registry for the Skills gallery.

    Read-only metadata: name, description (what the LLM sees), and the
    declared risk level (so the UI can show which actions ask first).
    """
    gateway = _get_gateway()
    registry = getattr(gateway, "_registry", None)
    schemas = list(registry.schemas()) if registry is not None else []
    if not schemas:
        # Legacy gateway has no registry — build a throwaway one from the
        # same package the agent gateway discovers. Also covers stale adopted
        # agents that have an empty registry object during startup.
        from pathlib import Path

        import clawed.agent_core.tools as tools_pkg
        from clawed.agent_core.tools.base import ToolRegistry

        registry = ToolRegistry()
        registry.discover(Path(tools_pkg.__file__).parent)
        schemas = list(registry.schemas())

    tools = []
    for schema in schemas:
        fn = schema.get("function", {})
        name = str(fn.get("name", "")).strip()
        if not name:
            continue
        tool = registry.get(name)
        tools.append({
            "name": name,
            "description": str(fn.get("description", "") or "").strip(),
            "risk_level": getattr(tool, "risk_level", "write_local"),
        })
    tools.sort(key=lambda t: str(t["name"]))
    return {"tools": tools}


# ── Approvals ────────────────────────────────────────────────────────


class ResolveApprovalRequest(BaseModel):
    approved: bool
    always: bool = False


@router.get("/approvals/pending", dependencies=[Depends(require_auth)])
async def pending_approvals(request: Request) -> dict[str, Any]:
    """List this teacher's pending approvals (for UI re-sync after reload)."""
    from clawed.agent_core.approvals import ApprovalManager
    from clawed.agent_core.identity import get_teacher_id

    mgr = ApprovalManager()
    items = mgr.pending_for_teacher(get_teacher_id())
    return {
        "approvals": [
            {
                "approval_id": pa.id,
                "description": pa.action_description,
                "tool_name": pa.action_payload.get("tool_name"),
                "risk_level": pa.action_payload.get("risk_level"),
                "created_at": pa.created_at,
            }
            for pa in items
        ],
    }


@router.post("/approvals/{approval_id}/resolve", dependencies=[Depends(require_auth)])
@limiter.limit("60/minute")
async def resolve_approval(
    request: Request, approval_id: str, req: ResolveApprovalRequest,
) -> dict[str, Any]:
    """Resolve a pending approval — wakes the paused agent loop if live."""
    from clawed.agent_core.approval_broker import ApprovalBroker, ApprovalDecision
    from clawed.agent_core.approvals import ApprovalManager
    from clawed.agent_core.identity import get_teacher_id

    mgr = ApprovalManager()
    pa = mgr.load(approval_id)
    if pa is None or pa.teacher_id != get_teacher_id():
        return {"ok": False, "error": "Approval not found."}
    if pa.status != "pending":
        return {"ok": False, "error": f"Already {pa.status}."}

    # Defense in depth: a device tapping "Always" over the tunnel cannot create
    # a standing grant — only the trusted local Mac can. Downgrade always→once
    # when the resolving request itself arrived over Cloudflare. (The live-turn
    # path enforces the same rule via context.is_remote; this covers a remote
    # tap landing on a turn that started locally, or with no live waiter.)
    effective_always = req.always and not _via_cloudflare_edge(request)

    broker = ApprovalBroker.instance()
    woke = broker.resolve(
        approval_id, ApprovalDecision(approved=req.approved, always=effective_always),
    )
    if not woke:
        # No live waiter (loop gone / different process) — persist the
        # decision so it acts as a standing record next time.
        if req.approved and effective_always:
            mgr.approve(approval_id)
        elif req.approved:
            mgr._update_status(approval_id, "consumed")
        else:
            mgr.reject(approval_id)
    return {"ok": True, "live": woke, "standing": effective_always and req.approved}
