"""Chat routes — student chatbot endpoints.

Two routers:
- ``router`` (teacher): ``/api/chat`` with teacher bearer auth + rate limit.
- ``student_router`` (unauth): ``/api/chat/student`` with a tight rate limit
  so the embed snippet on a teacher's LMS can be reached by students
  without them needing the teacher's API token.

v4.11.2026 new route: previously the embed snippet pointed clients at
``/api/chat`` which is teacher-only, so every student request 401'd.
The new ``/api/chat/student`` route validates a ``lesson_id`` that
actually exists and then runs the same ``student_chat`` generator but
reads question/history only — it does NOT expose the teacher's bearer
token to anyone.

ED-3 audit fix: the student route now also requires a ``share_token``
that matches the lesson's share_token, so only holders of the share
link (containing both lesson_id and share_token) can access student chat.
"""

from __future__ import annotations

import json
import logging
import secrets
from typing import Any, Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from clawed.api.deps import get_db, limiter, require_auth
from clawed.chat import student_chat
from clawed.models import TeacherPersona

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"], dependencies=[Depends(require_auth)])
student_chat_router = APIRouter(tags=["chat-student"])


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., max_length=2000)


class ChatRequest(BaseModel):
    lesson_id: str = Field(..., min_length=1, max_length=200)
    question: str = Field(..., min_length=1, max_length=2000)
    history: list[ChatMessage] = Field(default_factory=list, max_length=20)
    conversation_token: str | None = Field(default=None, min_length=32, max_length=200)


class StudentChatRequest(ChatRequest):
    """Student chat requires a share_token in addition to lesson_id (ED-3 audit fix)."""
    share_token: str = Field(..., min_length=1, max_length=200)


async def _run_chat(req: ChatRequest, *, audience: str = "teacher") -> Any:
    """Shared chat backend used by both the teacher and student routes."""
    db = get_db()

    lesson_row = db.get_lesson(req.lesson_id)
    if not lesson_row:
        return JSONResponse({"error": "Lesson not found."}, status_code=404)

    try:
        lesson_data = json.loads(lesson_row["lesson_json"]) if lesson_row["lesson_json"] else {}
    except (json.JSONDecodeError, TypeError) as exc:
        logger.warning("Failed to parse lesson_json for lesson %s: %s", req.lesson_id, exc)
        lesson_data = {}

    unit = db.get_unit(lesson_row["unit_id"])
    teacher = db.get_teacher(unit["teacher_id"]) if unit else None
    if not teacher or not teacher.get("persona_json"):
        return JSONResponse({"error": "No teacher persona found."}, status_code=400)

    persona = TeacherPersona.model_validate_json(teacher["persona_json"])

    conversation_token = req.conversation_token
    if conversation_token:
        conversation_id = db.get_chat_conversation(conversation_token, req.lesson_id, audience)
        if conversation_id is None:
            return JSONResponse({"error": "Invalid conversation token."}, status_code=403)
    else:
        conversation_id, conversation_token = db.create_chat_conversation(req.lesson_id, audience)

    # Older clients can supply their own history on a new conversation. Never
    # retrieve the mixed legacy lesson history or override an existing session.
    history = [message.model_dump() for message in req.history] if req.conversation_token is None else []
    if not history:
        db_history = db.get_chat_history(req.lesson_id, limit=10, conversation_id=conversation_id)
        history = [{"role": m["role"], "content": m["content"]} for m in reversed(db_history)]

    try:
        response = await student_chat(
            question=req.question,
            lesson_json=lesson_data,
            persona=persona,
            chat_history=history,
        )
    except Exception:
        logger.error("Chat failed", exc_info=True)
        return JSONResponse({"error": "Chat failed. Please try again."}, status_code=500)

    db.insert_chat_message(req.lesson_id, "user", req.question, conversation_id=conversation_id)
    db.insert_chat_message(req.lesson_id, "assistant", response, conversation_id=conversation_id)

    return {"response": response, "lesson_id": req.lesson_id, "conversation_token": conversation_token}


@router.post("/chat")
@limiter.limit("30/minute")
async def chat_endpoint(request: Request, req: ChatRequest) -> Any:
    """Teacher-side chat endpoint (authenticated).

    Same backend as the student route; kept separate so teacher-only
    tooling can hit it with the bearer token and get richer rate limits.
    """
    return await _run_chat(req, audience="teacher")


@student_chat_router.post("/chat/student")
@limiter.limit("60/minute")
async def chat_student_endpoint(request: Request, req: StudentChatRequest) -> Any:
    """Unauthenticated chat endpoint for the LMS-embedded student widget.

    ED-3 audit fix: requires both lesson_id AND share_token. Only someone
    who has the share link (containing both values) can access student chat.
    Rate limited to 60 requests per minute per client IP to prevent abuse.
    """
    db = get_db()
    lesson_row = db.get_lesson(req.lesson_id)
    if not lesson_row:
        return JSONResponse({"error": "Lesson not found."}, status_code=404)

    stored_token = lesson_row.get("share_token") or ""
    if not stored_token or not secrets.compare_digest(req.share_token.encode(), stored_token.encode()):
        return JSONResponse({"error": "Invalid share token."}, status_code=403)

    return await _run_chat(req, audience="student")
