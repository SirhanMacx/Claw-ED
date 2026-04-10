"""Tool routes — sub packet and parent communication generators."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from clawed.api.deps import limiter, require_auth

logger = logging.getLogger(__name__)

router = APIRouter(tags=["tools"], dependencies=[Depends(require_auth)])


# ── Sub Packet ────────────────────────────────────────────────────────


class SubPacketAPIRequest(BaseModel):
    teacher_name: str = Field(..., min_length=1, max_length=200)
    school: str = Field("", max_length=200)
    class_name: str = Field(..., min_length=1, max_length=200)
    grade: str = Field(..., min_length=1, max_length=20)
    subject: str = Field(..., min_length=1, max_length=100)
    date: str = Field(..., min_length=1, max_length=50)
    period_or_time: str = Field(..., min_length=1, max_length=100)
    lesson_topic: str = Field("", max_length=500)
    lesson_context: str = Field("", max_length=500)


@router.post("/sub-packet")
@limiter.limit("10/minute")
async def create_sub_packet(request: Request, req: SubPacketAPIRequest):
    """Generate a complete substitute teacher packet."""
    from clawed.llm import LLMClient
    from clawed.models import AppConfig
    from clawed.sub_packet import (
        SubPacketRequest,
        generate_sub_packet,
        sub_packet_to_markdown,
    )

    try:
        cfg = AppConfig.load()
        llm = LLMClient(cfg)
        sp_request = SubPacketRequest(**req.model_dump())
        packet = await generate_sub_packet(sp_request, llm)
        return {
            "packet": packet.model_dump(),
            "markdown": sub_packet_to_markdown(packet),
        }
    except Exception:
        logger.error("Sub packet generation failed", exc_info=True)
        return JSONResponse(
            {"error": "Sub packet generation failed. Please try again."},
            status_code=500,
        )


# ── Parent Communication ──────────────────────────────────────────────


class ParentCommAPIRequest(BaseModel):
    comm_type: str = Field(..., min_length=1, max_length=50)
    student_description: str = Field(..., min_length=1, max_length=1000)
    class_context: str = Field(..., min_length=1, max_length=500)
    tone: str = Field("professional and warm", max_length=100)
    additional_notes: str = Field("", max_length=1000)


@router.post("/parent-comm")
@limiter.limit("10/minute")
async def create_parent_comm(request: Request, req: ParentCommAPIRequest):
    """Generate a professional parent communication email."""
    from clawed.llm import LLMClient
    from clawed.models import AppConfig
    from clawed.parent_comm import (
        CommType,
        ParentCommRequest,
        generate_parent_comm,
        parent_comm_to_text,
    )

    # Resolve comm_type string to enum
    type_map = {
        "progress_update": CommType.PROGRESS_UPDATE,
        "progress": CommType.PROGRESS_UPDATE,
        "behavior_concern": CommType.BEHAVIOR_CONCERN,
        "behavior": CommType.BEHAVIOR_CONCERN,
        "positive_note": CommType.POSITIVE_NOTE,
        "positive": CommType.POSITIVE_NOTE,
        "upcoming_unit": CommType.UPCOMING_UNIT,
        "unit": CommType.UPCOMING_UNIT,
        "permission_request": CommType.PERMISSION_REQUEST,
        "permission": CommType.PERMISSION_REQUEST,
        "general_update": CommType.GENERAL_UPDATE,
        "general": CommType.GENERAL_UPDATE,
    }

    resolved_type = type_map.get(req.comm_type.lower())
    if resolved_type is None:
        return JSONResponse(
            {"error": f"Unknown comm_type: {req.comm_type}. Valid types: {', '.join(sorted(type_map.keys()))}"},
            status_code=400,
        )

    try:
        cfg = AppConfig.load()
        llm = LLMClient(cfg)
        pc_request = ParentCommRequest(
            comm_type=resolved_type,
            student_description=req.student_description,
            class_context=req.class_context,
            tone=req.tone,
            additional_notes=req.additional_notes,
        )
        comm = await generate_parent_comm(pc_request, llm)
        return {
            "comm": comm.model_dump(),
            "text": parent_comm_to_text(comm),
        }
    except Exception:
        logger.error("Parent comm generation failed", exc_info=True)
        return JSONResponse(
            {"error": "Parent communication generation failed. Please try again."},
            status_code=500,
        )
