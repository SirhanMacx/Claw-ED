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
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from clawed.api.deps import get_db, limiter, require_auth
from clawed.chat import student_chat
from clawed.models import TeacherPersona

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"], dependencies=[Depends(require_auth)])
student_chat_router = APIRouter(tags=["chat-student"])


class ChatRequest(BaseModel):
    lesson_id: str = Field(..., min_length=1, max_length=200)
    question: str = Field(..., min_length=1, max_length=2000)
    history: list[dict[str, str]] = Field(default_factory=list, max_length=20)


async def _run_chat(req: ChatRequest) -> JSONResponse | dict:
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

    teacher = db.get_default_teacher()
    if not teacher or not teacher.get("persona_json"):
        return JSONResponse({"error": "No teacher persona found."}, status_code=400)

    persona = TeacherPersona.model_validate_json(teacher["persona_json"])

    history = req.history
    if not history:
        db_history = db.get_chat_history(req.lesson_id, limit=10)
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

    db.insert_chat_message(req.lesson_id, "user", req.question)
    db.insert_chat_message(req.lesson_id, "assistant", response)

    return {"response": response, "lesson_id": req.lesson_id}


@router.post("/chat")
@limiter.limit("30/minute")
async def chat_endpoint(request: Request, req: ChatRequest):
    """Teacher-side chat endpoint (authenticated).

    Same backend as the student route; kept separate so teacher-only
    tooling can hit it with the bearer token and get richer rate limits.
    """
    return await _run_chat(req)


@student_chat_router.post("/chat/student")
@limiter.limit("60/minute")
async def chat_student_endpoint(request: Request, req: ChatRequest):
    """Unauthenticated chat endpoint for the LMS-embedded student widget.

    Validated only by the lesson_id — which is unguessable (UUID) and
    is the same token already present in the public share flow. Rate
    limited to 60 requests per minute per client IP to prevent abuse.
    """
    return await _run_chat(req)
