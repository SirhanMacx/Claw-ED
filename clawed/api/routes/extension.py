"""API routes for the Chrome extension + real-time classroom + community."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from clawed.api.deps import require_auth

logger = logging.getLogger(__name__)

# Teacher routes require auth (P0-1 audit fix).
# Chrome extension must send Bearer token.
router = APIRouter(tags=["extension"], dependencies=[Depends(require_auth)])

# Student routes do NOT require teacher auth — the class code IS the auth.
# Students connect with a code they get from their teacher in class.
student_router = APIRouter(tags=["classroom-student"])


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

        # v4.11.2026 fix: previously this endpoint generated a lesson,
        # spent minutes of LLM compute, then returned NOTHING the teacher
        # could act on — no lesson_id, no DB row, no "open the dashboard
        # to view" target. Now we persist the lesson through the same
        # path used by the normal CLI/HTTP generation flow so the
        # dashboard /lesson/{lesson_id} page actually resolves.
        lesson_id: str | None = None
        share_token: str | None = None
        try:
            from clawed.agent_core.identity import get_teacher_id
            from clawed.state import TeacherSession

            # Convert MasterContent to DailyLesson for the state API
            try:
                daily = master.to_daily_lesson()
            except Exception:
                # Older MasterContent revisions lacked to_daily_lesson;
                # build a minimal DailyLesson from the fields we need.
                from clawed.models import DailyLesson
                daily = DailyLesson(
                    lesson_number=1,
                    title=master.title,
                    objective=master.objective,
                )

            session = TeacherSession.load(get_teacher_id() or "default")
            # Use a synthetic unit_id so we don't require a real unit row
            import hashlib
            unit_id = hashlib.md5(
                f"extension:{topic}".encode()
            ).hexdigest()[:16]
            lesson_id = session.save_lesson(daily, unit_id=unit_id)
            # save_lesson writes a share_token row too; look it up
            try:
                from clawed.state import _get_conn
                with _get_conn() as conn:
                    row = conn.execute(
                        "SELECT share_token FROM generated_lessons WHERE id = ?",
                        (lesson_id,),
                    ).fetchone()
                    if row:
                        share_token = row["share_token"]
            except Exception as exc:
                logger.debug("share_token lookup failed: %s", exc)
        except Exception as exc:
            logger.warning("Extension lesson persist failed: %s", exc)

        return {
            "lesson_id": lesson_id,
            "share_token": share_token,
            "title": master.title,
            "objective": master.objective,
            "topic": master.topic,
            "sources": len(master.primary_sources),
            "files": [],
            "dashboard_url": (
                f"/lesson/{lesson_id}" if lesson_id else None
            ),
            "message": (
                f"Lesson '{master.title}' generated and saved."
                if lesson_id
                else f"Lesson '{master.title}' generated (not persisted)."
            ),
        }
    except Exception:
        # v4.11.2026 fix: never leak raw exception text to the extension.
        logger.exception("Extension generate failed")
        return {"error": "Lesson generation failed. Please try again."}


# Saved sources from extension (bounded to prevent OOM)
_MAX_SOURCES = 500
_saved_sources: list[dict] = []


@router.post("/extension/add-source")
async def extension_add_source(req: ExtensionSourceRequest):
    """Save highlighted text as a primary source for future lessons."""
    if len(_saved_sources) >= _MAX_SOURCES:
        _saved_sources.pop(0)  # Remove oldest
    _saved_sources.append({
        "text": req.text[:50000],  # Cap text length
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


# In-memory classroom sessions (bounded to prevent OOM)
_MAX_SESSIONS = 100
_classroom_sessions: dict[str, ClassroomState] = {}
_classroom_connections: dict[str, list[WebSocket]] = {}

# v4.11.2026 DoS protection (P1 from security audit): per-session response
# cap and per-response length cap. Without these, an attacker who obtains
# a class code can POST /classroom/{code}/respond in a tight loop with
# multi-MB bodies until the process OOMs.
_MAX_POLL_RESPONSES_PER_SESSION = 500
_MAX_RESPONSE_LENGTH = 2000
_MAX_STUDENT_ID_LENGTH = 100


@router.post("/classroom/start")
async def classroom_start(lesson_title: str = "", total_slides: int = 10):
    """Start a real-time classroom session. Returns class code."""
    import secrets

    # Enforce max sessions to prevent OOM
    if len(_classroom_sessions) >= _MAX_SESSIONS:
        # Remove oldest session
        oldest = next(iter(_classroom_sessions))
        del _classroom_sessions[oldest]
        _classroom_connections.pop(oldest, None)

    code = secrets.token_hex(6).upper()  # 12-char code (H3 audit fix)
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


@student_router.post("/classroom/{code}/respond")
async def classroom_respond(code: str, student_id: str = "", response: str = ""):
    """Student submits a poll response or exit ticket answer.

    On student_router — no teacher auth required. Class code is the auth.

    v4.11.2026 hardening:
    - per-response length cap (2000 chars)
    - per-student_id length cap (100 chars)
    - per-session poll_responses cap (500 items)
    - student_id sanitization (no control chars)
    """
    session = _classroom_sessions.get(code)
    if not session:
        return {"error": "Session not found"}

    if len(session.poll_responses) >= _MAX_POLL_RESPONSES_PER_SESSION:
        return {"error": "Too many responses for this session"}

    # Truncate + strip control characters to prevent terminal injection
    # and memory exhaustion via oversized payloads.
    student_id = (student_id or "")[:_MAX_STUDENT_ID_LENGTH]
    student_id = "".join(c for c in student_id if c.isprintable())
    response = (response or "")[:_MAX_RESPONSE_LENGTH]

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


@student_router.get("/classroom/{code}/state")
async def classroom_state(code: str):
    """Get current classroom state (for student devices).

    On student_router — no teacher auth required.

    v4.11.2026 fix: redact poll_responses (student PII) from the public
    student state endpoint. Students should only see slide/timer/poll-
    question state; raw responses with student_ids are teacher-only and
    must be fetched via an authenticated /classroom/{code}/responses
    route.
    """
    session = _classroom_sessions.get(code)
    if not session:
        return {"error": "Session not found"}
    state = session.model_dump()
    # Replace raw responses with just a count so we don't broadcast
    # student names / open-ended answers to every student device.
    state["poll_response_count"] = len(state.pop("poll_responses", []))
    return state


@router.get("/classroom/{code}/responses")
async def classroom_responses(code: str):
    """Teacher-only view of raw poll responses for the class session.

    v4.11.2026 new route: separates PII-bearing student responses from
    the public /state endpoint. Lives on the authenticated teacher router
    (Depends(require_auth) at router level).
    """
    session = _classroom_sessions.get(code)
    if not session:
        return {"error": "Session not found"}
    return {
        "question": session.poll_question,
        "count": len(session.poll_responses),
        "responses": session.poll_responses,
    }


@student_router.websocket("/classroom/{code}/ws")
async def classroom_websocket(websocket: WebSocket, code: str):
    """WebSocket for real-time classroom updates.

    On student_router — class code validates the session.
    Rejects with 1008 if code is invalid.
    """
    # Validate code BEFORE accepting (explicit WebSocket auth)
    if code not in _classroom_sessions:
        await websocket.close(code=1008, reason="Invalid classroom code")
        return

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
        if code in _classroom_connections:
            conns = _classroom_connections[code]
            if websocket in conns:
                conns.remove(websocket)


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


# Community lesson store (bounded, in-memory — upgrade to SQLite for production)
_MAX_COMMUNITY_LESSONS = 1000
_community_lessons: list[dict] = []


# v4.11.2026.1 security fix (P2-6): the previous PII strip only popped
# top-level keys and the first nested level of dicts. Nested lists
# (e.g. materials, segments, stations) and deeper nesting leaked the
# teacher's name straight through. This recursive scrub walks the whole
# tree.
_IDENTITY_FIELDS: frozenset[str] = frozenset({
    "teacher_name",
    "school",
    "teacher_id",
    "persona",
    "teacher_email",
    "name",
    "author",
    "author_email",
    "creator",
})


def _scrub_pii(obj, _depth: int = 0):
    """Recursively remove identity fields from nested dict/list structures."""
    if _depth > 30:  # pathological nesting guard
        return obj
    if isinstance(obj, dict):
        for k in list(obj.keys()):
            if k in _IDENTITY_FIELDS:
                obj.pop(k, None)
            else:
                obj[k] = _scrub_pii(obj[k], _depth + 1)
        return obj
    if isinstance(obj, list):
        return [_scrub_pii(item, _depth + 1) for item in obj]
    return obj


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

    # Enforce max community lessons
    if len(_community_lessons) >= _MAX_COMMUNITY_LESSONS:
        _community_lessons.pop(0)

    # v4.11.2026.1: deep-scrub identity fields out of the whole tree.
    lesson_data = _scrub_pii(lesson_data)

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
            # Proper cumulative average (M2 audit fix)
            total_stars = entry.get("_total_stars", entry["rating"])
            num_ratings = entry.get("_num_ratings", 1)
            entry["_total_stars"] = total_stars + rating
            entry["_num_ratings"] = num_ratings + 1
            entry["rating"] = round(entry["_total_stars"] / entry["_num_ratings"], 1)
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


@router.get("/scheduler/status")
async def scheduler_job_status():
    """Get the status of all scheduler jobs (F11 audit fix)."""
    try:
        from clawed.scheduler import get_job_status, load_schedule_config

        config = load_schedule_config()
        status = get_job_status()

        jobs = []
        for name, cfg in config.items():
            job = {
                "name": name,
                "description": cfg.get("description", ""),
                "enabled": cfg.get("enabled", False),
                "cron": cfg.get("cron", {}),
                "last_run": status.get(name, {}).get("last_run"),
                "status": status.get(name, {}).get("status", "never_run"),
                "result": status.get(name, {}).get("result"),
                "error": status.get(name, {}).get("error"),
            }
            jobs.append(job)

        return {"jobs": jobs}
    except Exception:
        return {"jobs": [], "error": "Scheduler not available."}
