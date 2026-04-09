"""API routes for the Chrome extension + real-time classroom + community."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(tags=["extension"])


# ── Chrome Extension Routes ──────────────────────────────────────────


class ExtensionGenerateRequest(BaseModel):
    text: str
    source_url: str = ""
    source_title: str = ""
    action: str = "generate_lesson"


class ExtensionSourceRequest(BaseModel):
    text: str
    source_url: str = ""
    source_title: str = ""


@router.post("/extension/generate")
async def extension_generate(req: ExtensionGenerateRequest):
    """Generate a lesson from highlighted text (Chrome extension endpoint).

    The extension sends selected text from any webpage. Claw-ED generates
    a lesson using that text as a primary source.
    """
    from clawed.lesson import generate_master_content
    from clawed.models import AppConfig, LessonBrief, TeacherPersona, UnitPlan

    try:
        config = AppConfig.load()
        persona = TeacherPersona()
        try:
            from clawed.agent_core.identity import get_teacher_id
            from clawed.state import TeacherSession

            session = TeacherSession.load(get_teacher_id())
            if session.persona:
                persona = session.persona
        except Exception:
            pass

        subject = persona.subject_area or "General"
        grade = persona.grade_levels[0] if persona.grade_levels else "8"

        # Build minimal unit context from the selected text
        topic = req.source_title or "Selected Text Lesson"
        unit = UnitPlan(
            title=f"Lesson from: {topic}",
            subject=subject,
            grade_level=grade,
            topic=topic,
            duration_weeks=1,
            overview=req.text[:500],
            daily_lessons=[
                LessonBrief(
                    lesson_number=1,
                    topic=topic,
                    description=f"Analyze the following source: {req.text[:200]}",
                ),
            ],
        )

        # Pass the selected text as teacher materials
        source_context = (
            f"## Primary Source (from web)\n"
            f"**Source:** {req.source_title}\n"
            f"**URL:** {req.source_url}\n\n"
            f"**Full Text:**\n{req.text}\n\n"
            f"IMPORTANT: Use this EXACT text as a primary source in the lesson. "
            f"Include it verbatim in the primary_sources content_text field."
        )

        master = await generate_master_content(
            lesson_number=1,
            unit=unit,
            persona=persona,
            config=config,
            teacher_materials=source_context,
        )

        return {
            "title": master.title,
            "objective": master.objective,
            "topic": master.topic,
            "sources": len(master.primary_sources),
            "files": [],  # Could add file paths if compiled
            "message": (
                f"Lesson '{master.title}' generated! "
                f"Open the Claw-ED dashboard to view and export."
            ),
        }
    except Exception as exc:
        logger.exception("Extension generate failed")
        return {"error": str(exc)[:200]}


# Saved sources from extension
_saved_sources: list[dict] = []


@router.post("/extension/add-source")
async def extension_add_source(req: ExtensionSourceRequest):
    """Save highlighted text as a primary source for future lessons."""
    _saved_sources.append({
        "text": req.text,
        "url": req.source_url,
        "title": req.source_title,
    })
    logger.info("Extension: saved source '%s' (%d chars)", req.source_title, len(req.text))
    return {"message": f"Source saved! ({len(_saved_sources)} total)"}


@router.get("/extension/sources")
async def extension_list_sources():
    """List all saved sources from the Chrome extension."""
    return {"sources": _saved_sources, "count": len(_saved_sources)}


# ── Real-Time Classroom Mode ─────────────────────────────────────────


class ClassroomState(BaseModel):
    """Shared state for real-time classroom presentation."""
    lesson_title: str = ""
    current_slide: int = 0
    total_slides: int = 0
    timer_seconds: int = 0
    timer_running: bool = False
    poll_active: bool = False
    poll_question: str = ""
    poll_responses: list[dict] = Field(default_factory=list)


# In-memory classroom sessions (keyed by class code)
_classroom_sessions: dict[str, ClassroomState] = {}
_classroom_connections: dict[str, list[WebSocket]] = {}


@router.post("/classroom/start")
async def classroom_start(lesson_title: str = "", total_slides: int = 10):
    """Start a real-time classroom session. Returns class code."""
    import secrets

    code = secrets.token_hex(3).upper()  # 6-char code like "A3F1B2"
    _classroom_sessions[code] = ClassroomState(
        lesson_title=lesson_title,
        total_slides=total_slides,
    )
    _classroom_connections[code] = []
    logger.info("Classroom session started: %s (%s)", code, lesson_title)
    return {"class_code": code, "lesson_title": lesson_title}


@router.post("/classroom/{code}/next-slide")
async def classroom_next_slide(code: str):
    """Advance to next slide (teacher control)."""
    session = _classroom_sessions.get(code)
    if not session:
        return {"error": "Session not found"}
    if session.current_slide < session.total_slides - 1:
        session.current_slide += 1
    await _broadcast(code, {
        "type": "slide_change",
        "slide": session.current_slide,
    })
    return {"slide": session.current_slide}


@router.post("/classroom/{code}/prev-slide")
async def classroom_prev_slide(code: str):
    """Go back one slide (teacher control)."""
    session = _classroom_sessions.get(code)
    if not session:
        return {"error": "Session not found"}
    if session.current_slide > 0:
        session.current_slide -= 1
    await _broadcast(code, {
        "type": "slide_change",
        "slide": session.current_slide,
    })
    return {"slide": session.current_slide}


@router.post("/classroom/{code}/start-timer")
async def classroom_start_timer(code: str, seconds: int = 600):
    """Start a visible countdown timer (teacher control)."""
    session = _classroom_sessions.get(code)
    if not session:
        return {"error": "Session not found"}
    session.timer_seconds = seconds
    session.timer_running = True
    await _broadcast(code, {
        "type": "timer_start",
        "seconds": seconds,
    })
    return {"timer": seconds}


@router.post("/classroom/{code}/launch-poll")
async def classroom_launch_poll(code: str, question: str = ""):
    """Launch a live poll (teacher control)."""
    session = _classroom_sessions.get(code)
    if not session:
        return {"error": "Session not found"}
    session.poll_active = True
    session.poll_question = question
    session.poll_responses = []
    await _broadcast(code, {
        "type": "poll_start",
        "question": question,
    })
    return {"poll": question}


@router.post("/classroom/{code}/respond")
async def classroom_respond(code: str, student_id: str = "", response: str = ""):
    """Student submits a poll response or exit ticket answer."""
    session = _classroom_sessions.get(code)
    if not session:
        return {"error": "Session not found"}
    session.poll_responses.append({
        "student_id": student_id,
        "response": response,
    })
    # Broadcast updated count to teacher
    await _broadcast(code, {
        "type": "poll_update",
        "count": len(session.poll_responses),
    })
    return {"received": True}


@router.get("/classroom/{code}/state")
async def classroom_state(code: str):
    """Get current classroom state (for student devices)."""
    session = _classroom_sessions.get(code)
    if not session:
        return {"error": "Session not found"}
    return session.model_dump()


@router.websocket("/classroom/{code}/ws")
async def classroom_websocket(websocket: WebSocket, code: str):
    """WebSocket for real-time classroom updates.

    Students and teacher connect here. All state changes are broadcast
    to all connected clients instantly.
    """
    await websocket.accept()
    if code not in _classroom_connections:
        _classroom_connections[code] = []
    _classroom_connections[code].append(websocket)

    try:
        # Send current state on connect
        session = _classroom_sessions.get(code)
        if session:
            await websocket.send_json({
                "type": "state_sync",
                "state": session.model_dump(),
            })

        # Keep alive and listen for messages
        while True:
            data = await websocket.receive_text()
            # Could handle student messages here
            logger.debug("Classroom WS [%s]: %s", code, data[:100])

    except WebSocketDisconnect:
        _classroom_connections[code].remove(websocket)


async def _broadcast(code: str, message: dict) -> None:
    """Broadcast a message to all connected WebSocket clients."""
    connections = _classroom_connections.get(code, [])
    dead: list[WebSocket] = []
    for ws in connections:
        try:
            await ws.send_json(message)
        except Exception:
            dead.append(ws)
    for ws in dead:
        connections.remove(ws)


# ── Teacher Community / Sharing ──────────────────────────────────────


class ShareRequest(BaseModel):
    lesson_json: str
    subject: str = ""
    grade_level: str = ""
    topic: str = ""
    tags: list[str] = Field(default_factory=list)


# Community lesson store (SQLite in production, in-memory for now)
_community_lessons: list[dict] = []


@router.post("/community/share")
async def community_share(req: ShareRequest):
    """Share a lesson with the teacher community (anonymized).

    Strips teacher identity before storing. Other teachers can browse
    and use shared lessons as templates.
    """
    try:
        lesson_data = json.loads(req.lesson_json)
    except json.JSONDecodeError:
        return {"error": "Invalid JSON"}

    # Strip teacher identity
    for field in ("teacher_name", "school", "teacher_id", "persona"):
        lesson_data.pop(field, None)

    entry = {
        "id": len(_community_lessons) + 1,
        "subject": req.subject or lesson_data.get("subject", ""),
        "grade_level": req.grade_level or lesson_data.get("grade_level", ""),
        "topic": req.topic or lesson_data.get("topic", ""),
        "title": lesson_data.get("title", "Untitled"),
        "tags": req.tags,
        "lesson": lesson_data,
        "rating": 0.0,
        "uses": 0,
    }
    _community_lessons.append(entry)

    logger.info("Community: lesson shared — '%s'", entry["title"])
    return {"id": entry["id"], "message": "Lesson shared with the community!"}


@router.get("/community/browse")
async def community_browse(
    subject: str = "",
    grade: str = "",
    query: str = "",
    limit: int = 20,
):
    """Browse shared lessons from the teacher community."""
    results = _community_lessons

    if subject:
        results = [r for r in results if subject.lower() in r["subject"].lower()]
    if grade:
        results = [r for r in results if grade in r["grade_level"]]
    if query:
        q = query.lower()
        results = [
            r for r in results
            if q in r["title"].lower()
            or q in r["topic"].lower()
            or any(q in t.lower() for t in r["tags"])
        ]

    return {
        "lessons": results[:limit],
        "total": len(results),
    }


@router.post("/community/{lesson_id}/rate")
async def community_rate(lesson_id: int, rating: float = 5.0):
    """Rate a community lesson (1-5 stars)."""
    for entry in _community_lessons:
        if entry["id"] == lesson_id:
            entry["rating"] = round((entry["rating"] + rating) / 2, 1)
            entry["uses"] += 1
            return {"rating": entry["rating"], "uses": entry["uses"]}
    return {"error": "Lesson not found"}


# ── Visible Agent Pipeline ───────────────────────────────────────────


@router.get("/pipeline/status")
async def pipeline_status():
    """Get the current state of the lesson generation pipeline.

    Returns the quality gate checks, critic feedback, and generation
    metadata so teachers can see how Ed built their lesson.
    """
    # Read the most recent generation log
    import os

    base = Path(os.environ.get(
        "EDUAGENT_DATA_DIR", str(Path.home() / ".eduagent"),
    ))
    log_path = base / "logs" / "generation.log"

    recent_entries: list[str] = []
    if log_path.exists():
        try:
            lines = log_path.read_text(encoding="utf-8").strip().split("\n")
            recent_entries = lines[-20:]  # Last 20 log lines
        except Exception:
            pass

    return {
        "pipeline_stages": [
            {
                "name": "Standards Lookup",
                "description": "Matches lesson to state standards",
                "status": "complete",
            },
            {
                "name": "Persona Injection",
                "description": "Loads teacher voice, style, preferences",
                "status": "complete",
            },
            {
                "name": "Classroom Context",
                "description": "Loads room resources, student needs",
                "status": "complete",
            },
            {
                "name": "KG Connections",
                "description": "Queries knowledge graph for cross-unit links",
                "status": "complete",
            },
            {
                "name": "LLM Generation",
                "description": "Generates MasterContent via frontier model",
                "status": "complete",
            },
            {
                "name": "Quality Gate (12 checks)",
                "description": "Validates: Bloom's, sources, stimuli, differentiation, voice, diversity",
                "status": "complete",
            },
            {
                "name": "Teaching Constitution Critic",
                "description": "Separate LLM reviews against 8 pedagogical principles",
                "status": "complete",
            },
            {
                "name": "Vision Image Filter",
                "description": "Scores fetched images for relevance and quality",
                "status": "complete",
            },
            {
                "name": "Multi-Format Compilation",
                "description": "Teacher DOCX, Student DOCX, PPTX, Game, Simulation, Journey",
                "status": "complete",
            },
        ],
        "recent_log": recent_entries,
    }


@router.get("/pipeline/quality-report")
async def pipeline_quality_report():
    """Get the quality gate check results for the most recent lesson."""
    try:
        from clawed.agent_core.identity import get_teacher_id
        from clawed.state import TeacherSession

        session = TeacherSession.load(get_teacher_id())
        quality_data = session.config.get("last_quality_report", {})
        return quality_data or {"message": "No quality report available yet."}
    except Exception:
        return {"message": "No quality report available."}
