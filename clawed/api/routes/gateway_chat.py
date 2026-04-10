"""Gateway chat route — teacher chat through the Gateway.

HTTP interface for TUI and web clients. Uses the unified teacher_id
from identity.py — callers cannot impersonate other teachers.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from clawed.api.deps import limiter, require_auth

logger = logging.getLogger(__name__)

router = APIRouter(tags=["gateway"])

_gateway = None


def _get_gateway():
    global _gateway
    if _gateway is None:
        from clawed.gateway import Gateway

        _gateway = Gateway()
    return _gateway


class GatewayChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=10000)


@router.post("/gateway/chat", dependencies=[Depends(require_auth)])
@limiter.limit("30/minute")
async def gateway_chat(request: Request, req: GatewayChatRequest):
    """Send a message through the Gateway.

    teacher_id is resolved server-side from the config — callers
    cannot specify or impersonate a different teacher.
    """
    gateway = _get_gateway()

    # Use canonical teacher_id — not caller-supplied
    from clawed.agent_core.identity import get_teacher_id

    teacher_id = get_teacher_id()

    try:
        result = await gateway.handle(
            req.message,
            teacher_id,
            transport="web",
        )
    except Exception:
        logger.error("Gateway chat failed", exc_info=True)
        return JSONResponse(
            {"error": "Something went wrong. Please try again."},
            status_code=500,
        )

    buttons = []
    if result.button_rows or result.buttons:
        rows = result.button_rows or [result.buttons]
        buttons = [
            {
                "label": b.label,
                "callback_data": b.callback_data,
                "url": b.url,
            }
            for row in rows
            for b in row
        ]

    return {
        "text": result.text,
        "files": [str(f) for f in result.files],
        "buttons": buttons,
    }
