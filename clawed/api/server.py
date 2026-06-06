"""FastAPI web server for Claw-ED — REST API + server-side rendered teacher dashboard."""

from __future__ import annotations

import html as html_mod
import json
import logging
import os
import sqlite3
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from clawed.api.deps import get_db, set_db
from clawed.database import Database

logger = logging.getLogger(__name__)

# Paths
_PKG_DIR = Path(__file__).parent
_TEMPLATE_DIR = _PKG_DIR / "templates"
_STATIC_DIR = _PKG_DIR / "static"

# Shared auth-denied response used by every page route.
_AUTH_DENIED = HTMLResponse(
    "<h1>401 — Auth required</h1>"
    '<form method="POST" action="/api/auth/bootstrap">'
    '<input name="token" placeholder="Paste your token" autofocus>'
    '<button type="submit">Authenticate</button>'
    "</form>",
    status_code=401,
)


def _check_page_auth(request: Request) -> bool:
    """Check auth for HTML pages via cookie, Bearer header, or localhost.

    F4 audit fix: ?token= query params are NO LONGER accepted for page
    auth. Use POST /api/auth/bootstrap or Bearer header instead.
    Tokens in URLs leak through browser history, bookmarks, referrers.

    v4.11.2026: timing-safe comparisons via secrets.compare_digest.
    """
    import secrets as _secrets

    from clawed.api.deps import get_api_token

    token = get_api_token()
    # Check cookie (primary method — set via POST /api/auth/bootstrap)
    cookie_val = request.cookies.get("clawed_token", "")
    if cookie_val and _secrets.compare_digest(cookie_val, token):
        return True
    # Check Bearer header (for API-like access)
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer ") and _secrets.compare_digest(auth[7:], token):
        return True
    # Check localhost bypass
    if os.environ.get("EDUAGENT_LOCAL_AUTH_BYPASS") == "1":
        client_ip = request.client.host if request.client else ""
        if client_ip in ("127.0.0.1", "::1", "localhost", "testclient"):
            return True
    return False


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup/shutdown lifecycle."""
    set_db(Database())
    yield
    db = get_db()
    if db:
        db.close()
    set_db(None)


# ── Decomposed helpers ──────────────────────────────────────────────


def _configure_middleware(app: FastAPI) -> Jinja2Templates:
    """Set up CORS, static file serving, and Jinja2 templates.

    Returns the configured *Jinja2Templates* instance for use by page routes.
    """
    # CORS — single middleware instance.
    # Supports localhost + Chrome extension origins (regex for extension IDs).
    cors_origins_raw = os.environ.get("EDUAGENT_CORS_ORIGINS", "")
    if cors_origins_raw:
        cors_origins = [o.strip() for o in cors_origins_raw.split(",") if o.strip()]
    else:
        cors_origins = [
            "http://localhost:8000",
            "http://127.0.0.1:8000",
        ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_origin_regex=r"^chrome-extension://[a-z]{32}$",
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )

    # Static files
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    # Templates
    return Jinja2Templates(directory=str(_TEMPLATE_DIR))


def _register_api_routes(app: FastAPI) -> None:
    """Import and mount all REST API routers under ``/api``."""
    from clawed.api.routes.chat import router as chat_router
    from clawed.api.routes.chat import (
        student_chat_router as chat_student_router,
    )
    from clawed.api.routes.export import public_router as export_public_router
    from clawed.api.routes.export import router as export_router
    from clawed.api.routes.extension import router as extension_router
    from clawed.api.routes.extension import student_router as student_classroom_router
    from clawed.api.routes.feedback import router as feedback_router
    from clawed.api.routes.gateway_chat import router as gateway_chat_router
    from clawed.api.routes.generate import router as generate_router
    from clawed.api.routes.ingest import router as ingest_router
    from clawed.api.routes.lessons import router as lessons_router
    from clawed.api.routes.school import router as school_router
    from clawed.api.routes.settings import router as settings_router
    from clawed.api.routes.tools import router as tools_router

    app.include_router(ingest_router, prefix="/api")
    app.include_router(generate_router, prefix="/api")
    app.include_router(chat_router, prefix="/api")
    app.include_router(chat_student_router, prefix="/api")  # No auth — student widget embed
    app.include_router(feedback_router, prefix="/api")
    app.include_router(export_router, prefix="/api")
    app.include_router(export_public_router, prefix="/api")
    app.include_router(settings_router, prefix="/api")
    app.include_router(school_router, prefix="/api")
    app.include_router(lessons_router, prefix="/api")
    app.include_router(tools_router, prefix="/api")
    app.include_router(gateway_chat_router, prefix="/api")
    app.include_router(extension_router, prefix="/api")
    app.include_router(student_classroom_router, prefix="/api")  # No auth — class code is auth


async def _page_auth_bootstrap(token: str = Form(...)) -> Any:
    """Accept auth token via POST and set a session cookie.

    Replaces the old ?token= query param flow to prevent token
    leakage through browser history, bookmarks, and referrers.
    """
    import secrets as _secrets

    from clawed.api.deps import get_api_token

    expected = get_api_token()
    if not _secrets.compare_digest(token, expected):
        return JSONResponse({"error": "Invalid token"}, status_code=401)

    is_https = os.environ.get("HTTPS", "").lower() in ("1", "true")
    response = RedirectResponse("/", status_code=303)
    response.set_cookie(
        "clawed_token", token,
        httponly=True,
        samesite="strict",
        secure=is_https,
        max_age=86400,
    )
    return response


async def _page_index(request: Request, templates: Jinja2Templates) -> Any:
    """Index page: redirect to dashboard if onboarded, else show wizard."""
    if not _check_page_auth(request):
        return _AUTH_DENIED
    db = get_db()
    teacher = db.get_default_teacher()
    has_persona = teacher is not None and teacher.get("persona_json") is not None
    onboarding_complete = db.is_onboarding_complete()

    if has_persona and onboarding_complete:
        return RedirectResponse(url="/dashboard", status_code=302)

    stats = db.get_stats()
    persona_data = None
    if teacher and teacher.get("persona_json"):
        with suppress(json.JSONDecodeError, TypeError):
            persona_data = json.loads(teacher["persona_json"])

    return templates.TemplateResponse(request, "index.html", {
        "stats": stats,
        "has_persona": has_persona,
        "onboarding_complete": onboarding_complete,
        "teacher_id": teacher["id"] if teacher else None,
        "persona": persona_data,
        "active_nav": "home",
    })


def _build_dashboard_context(
    db: Database, units: list[dict[str, Any]], teacher: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build template context for the dashboard/library page."""
    persona_name = ""
    persona_data = None
    if teacher and teacher.get("persona_json"):
        try:
            persona_data = json.loads(teacher["persona_json"])
            persona_name = persona_data.get("name", "")
        except (json.JSONDecodeError, TypeError):
            pass

    recent_items: list[dict[str, Any]] = []
    for u in units[:10]:
        recent_items.append({
            "type": "unit",
            "title": u["title"],
            "id": u["id"],
            "date": (u.get("created_at") or "")[:10],
        })
    for u in units[:5]:
        for lesson in db.list_lessons(u["id"])[:3]:
            recent_items.append({
                "type": "lesson",
                "title": lesson["title"] or f"Lesson {lesson.get('lesson_number', '')}",
                "id": lesson["id"],
                "date": (lesson.get("created_at") or "")[:10],
            })
    recent_items.sort(key=lambda x: x["date"], reverse=True)
    recent_items = recent_items[:10]

    active_lesson = None
    for u in units[:5]:
        for lesson in db.list_lessons(u["id"]):
            if lesson.get("share_token"):
                active_lesson = lesson
                break
        if active_lesson:
            break

    config_school = ""
    try:
        from clawed.models import AppConfig

        cfg = AppConfig.load()
        config_school = cfg.teacher_profile.school
    except (ImportError, FileNotFoundError, KeyError):
        pass

    return {
        "persona_name": persona_name,
        "persona": persona_data,
        "recent_items": recent_items,
        "active_lesson": active_lesson,
        "config_school": config_school,
    }


async def _page_dashboard(request: Request, templates: Jinja2Templates) -> HTMLResponse:
    """Dashboard page with recent activity and stats."""
    if not _check_page_auth(request):
        return _AUTH_DENIED
    db = get_db()
    stats = db.get_stats()
    units = db.list_units()
    for u in units:
        u["lesson_count"] = len(db.list_lessons(u["id"]))
    teacher = db.get_default_teacher()
    ctx = _build_dashboard_context(db, units, teacher)
    return templates.TemplateResponse(request, "dashboard.html", {
        "stats": stats,
        "units": units,
        **ctx,
        "active_nav": "home",
    })


def _build_lessons_list_html(
    all_lessons: list[dict[str, Any]],
    all_subjects: list[str],
    all_grades: list[str],
    subject_filter: str,
    grade_filter: str,
) -> str:
    """Render the lessons-list HTML table with filters."""
    rows_html = ""
    for les in all_lessons:
        score_display = f"{les['quality_score']}" if les.get("quality_score") else "-"
        rating_display = f"{'*' * les['rating']}" if les.get("rating") else "-"
        esc_token = html_mod.escape(str(les.get("share_token", "")))
        share_btn = f'<a href="/shared/{esc_token}">Share</a>' if les.get("share_token") else ""
        esc_id = html_mod.escape(str(les["id"]))
        esc_title = html_mod.escape(str(les["title"]))
        esc_subject = html_mod.escape(str(les["subject"]))
        esc_grade = html_mod.escape(str(les["grade_level"]))
        esc_date = html_mod.escape(str(les["date"]))
        esc_score = html_mod.escape(str(score_display))
        esc_rating = html_mod.escape(str(rating_display))
        rows_html += (
            f"<tr>"
            f"<td><a href='/lesson/{esc_id}'>{esc_title}</a></td>"
            f"<td>{esc_subject}</td>"
            f"<td>{esc_grade}</td>"
            f"<td>{esc_date}</td>"
            f"<td>{esc_score}</td>"
            f"<td>{esc_rating}</td>"
            f"<td>{share_btn}</td>"
            f"</tr>"
        )

    filter_html = ""
    if all_subjects:
        opts = "".join(
            f"<option value='{html_mod.escape(s)}'"
            f" {'selected' if s == subject_filter else ''}"
            f">{html_mod.escape(s)}</option>"
            for s in all_subjects
        )
        filter_html += (
            "<select name='subject' onchange='this.form.submit()'>"
            f"<option value=''>All Subjects</option>{opts}</select> "
        )
    if all_grades:
        opts = "".join(
            f"<option value='{html_mod.escape(g)}'"
            f" {'selected' if g == grade_filter else ''}"
            f">{html_mod.escape(g)}</option>"
            for g in all_grades
        )
        filter_html += (
            "<select name='grade' onchange='this.form.submit()'>"
            f"<option value=''>All Grades</option>{opts}</select>"
        )

    count_msg = (
        f"<p style='color:#999;margin-top:24px'>Showing {len(all_lessons)} lesson(s)</p>"
        if all_lessons
        else "<p>No lessons yet. <a href='/generate'>Generate one.</a></p>"
    )
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Lessons - Claw-ED</title>
<style>
body {{ font-family: -apple-system, system-ui, sans-serif;
  max-width: 1000px; margin: 20px auto; padding: 0 20px; }}
h1 {{ color: #1a73e8; }}
table {{ width: 100%; border-collapse: collapse; }}
th, td {{ padding: 10px 12px; text-align: left;
  border-bottom: 1px solid #e0e0e0; }}
th {{ background: #f5f5f5; font-weight: 600; }}
tr:hover {{ background: #f8f9fa; }}
a {{ color: #1a73e8; text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
.btn {{ display: inline-block; background: #1a73e8; color: white;
  padding: 10px 24px; border-radius: 6px;
  text-decoration: none; margin: 12px 0; }}
select {{ padding: 6px 10px; border-radius: 4px;
  border: 1px solid #ccc; margin-right: 8px; }}
.filters {{ margin: 16px 0; }}
</style></head><body>
<h1>All Lessons</h1>
<a href="/generate" class="btn">Generate New Lesson</a>
<form class="filters" method="get">{filter_html}</form>
<table>
<tr><th>Title</th><th>Subject</th><th>Grade</th>
<th>Date</th><th>Score</th><th>Rating</th><th></th></tr>
{rows_html}
</table>
{count_msg}
</body></html>"""


async def _page_lessons_list(request: Request) -> HTMLResponse:
    """Lesson list page: all generated lessons, filterable, newest first."""
    if not _check_page_auth(request):
        return _AUTH_DENIED
    db = get_db()
    subject_filter = request.query_params.get("subject", "")
    grade_filter = request.query_params.get("grade", "")

    all_lessons: list[dict[str, Any]] = []
    units = db.list_units()
    for u in units:
        if subject_filter and u.get("subject", "").lower() != subject_filter.lower():
            continue
        if grade_filter and u.get("grade_level", "").lower() != grade_filter.lower():
            continue
        for lesson in db.list_lessons(u["id"]):
            lesson_data = {}
            if lesson.get("lesson_json"):
                with suppress(json.JSONDecodeError, TypeError):
                    lesson_data = json.loads(lesson["lesson_json"])
            quality_score = None
            if lesson.get("scores_json"):
                try:
                    scores = json.loads(lesson["scores_json"])
                    quality_score = scores.get("overall") or scores.get("total")
                except (json.JSONDecodeError, TypeError):
                    pass
            all_lessons.append({
                "id": lesson["id"],
                "title": lesson.get("title") or lesson_data.get("title") or "Untitled",
                "subject": u.get("subject", ""),
                "grade_level": u.get("grade_level", ""),
                "date": (lesson.get("created_at") or "")[:10],
                "quality_score": quality_score,
                "rating": lesson.get("rating"),
                "share_token": lesson.get("share_token"),
            })

    all_lessons.sort(key=lambda x: x["date"], reverse=True)
    all_subjects = sorted({u.get("subject", "") for u in units if u.get("subject")})
    all_grades = sorted({u.get("grade_level", "") for u in units if u.get("grade_level")})

    html = _build_lessons_list_html(all_lessons, all_subjects, all_grades, subject_filter, grade_filter)
    return HTMLResponse(html)


async def _page_generate(request: Request, templates: Jinja2Templates) -> HTMLResponse:
    """Generate page with subject selection."""
    if not _check_page_auth(request):
        return _AUTH_DENIED
    from clawed.standards import STANDARDS

    db = get_db()
    teacher = db.get_default_teacher()
    has_persona = teacher is not None
    subjects = list(STANDARDS.keys())
    return templates.TemplateResponse(request, "generate.html", {
        "has_persona": has_persona,
        "subjects": subjects,
        "active_nav": "generate",
    })


def _build_state_frameworks(teacher_state: str) -> list[dict[str, Any]]:
    """Build framework info list for a given state."""
    state_frameworks: list[dict[str, Any]] = []
    if teacher_state:
        from clawed.state_standards import STATE_STANDARDS_CONFIG, get_framework_description

        state_cfg = STATE_STANDARDS_CONFIG.get(teacher_state, {})
        for subj_key in ("math", "ela", "science", "social_studies"):
            code = state_cfg.get(subj_key, "")
            if code:
                state_frameworks.append({
                    "label": subj_key.replace("_", " ").title(),
                    "code": code,
                    "description": get_framework_description(code),
                })
    return state_frameworks


async def _page_settings(request: Request, templates: Jinja2Templates) -> HTMLResponse:
    """Settings page with API keys, state frameworks, and class codes."""
    if not _check_page_auth(request):
        return _AUTH_DENIED
    from clawed.config import get_api_key, mask_api_key
    from clawed.models import AppConfig
    from clawed.state_standards import list_states

    cfg = AppConfig.load()
    db = get_db()
    teacher = db.get_default_teacher()
    persona_data = None
    if teacher and teacher.get("persona_json"):
        with suppress(json.JSONDecodeError, TypeError):
            persona_data = json.loads(teacher["persona_json"])

    teacher_state = cfg.teacher_profile.state if hasattr(cfg, "teacher_profile") else ""
    teacher_subjects = cfg.teacher_profile.subjects if hasattr(cfg, "teacher_profile") else []
    teacher_grades = cfg.teacher_profile.grade_levels if hasattr(cfg, "teacher_profile") else []

    state_frameworks = _build_state_frameworks(teacher_state)

    class_codes_list: list[dict[str, Any]] = []
    try:
        from clawed.state import _get_conn as _state_conn2
        from clawed.state import init_db as _state_init2

        _state_init2()
        teacher_id_for_codes = teacher["id"] if teacher else "local-teacher"
        with _state_conn2() as sconn2:
            cc_rows2 = sconn2.execute(
                "SELECT class_code, name, topic, expires_at, created_at FROM classes WHERE teacher_id = ?",
                (teacher_id_for_codes,),
            ).fetchall()
            class_codes_list = [dict(r) for r in cc_rows2]
    except (ImportError, sqlite3.OperationalError):
        pass

    anthropic_key = get_api_key("anthropic")
    openai_key = get_api_key("openai")
    openrouter_key = get_api_key("openrouter")
    google_key = get_api_key("google")

    return templates.TemplateResponse(request, "settings.html", {
        "config": cfg,
        "persona": persona_data,
        "anthropic_key_masked": mask_api_key(anthropic_key),
        "openai_key_masked": mask_api_key(openai_key),
        "openrouter_key_masked": mask_api_key(openrouter_key),
        "google_key_masked": mask_api_key(google_key),
        "has_anthropic_key": bool(anthropic_key),
        "has_openai_key": bool(openai_key),
        "has_openrouter_key": bool(openrouter_key),
        "has_google_key": bool(google_key),
        "states": list_states(),
        "teacher_state": teacher_state,
        "teacher_subjects": teacher_subjects,
        "teacher_grades": teacher_grades,
        "state_frameworks": state_frameworks,
        "class_codes": class_codes_list,
        "active_nav": "settings",
    })


async def _page_stats(request: Request, templates: Jinja2Templates) -> HTMLResponse:
    """Stats page with teacher analytics."""
    if not _check_page_auth(request):
        return _AUTH_DENIED
    db = get_db()
    teacher = db.get_default_teacher()
    teacher_id = teacher["id"] if teacher else "local-teacher"

    from clawed.analytics import get_teacher_stats

    stats_data = get_teacher_stats(teacher_id)

    return templates.TemplateResponse(request, "stats.html", {
        "stats": stats_data,
        "teacher_id": teacher_id,
    })


async def _page_lesson_detail(request: Request, lesson_id: str, templates: Jinja2Templates) -> HTMLResponse:
    """Lesson detail page with materials, scores, feedback, and embed snippet."""
    if not _check_page_auth(request):
        return _AUTH_DENIED
    db = get_db()
    lesson_row = db.get_lesson(lesson_id)
    if not lesson_row:
        return HTMLResponse("<h1>Lesson not found</h1>", status_code=404)
    try:
        lesson_data = json.loads(lesson_row["lesson_json"]) if lesson_row["lesson_json"] else {}
    except (json.JSONDecodeError, TypeError) as exc:
        logger.warning("Failed to parse lesson_json for %s: %s", lesson_id, exc)
        lesson_data = {}
    try:
        materials_data = json.loads(lesson_row["materials_json"]) if lesson_row.get("materials_json") else None
    except (json.JSONDecodeError, TypeError) as exc:
        logger.warning("Failed to parse materials_json for %s: %s", lesson_id, exc)
        materials_data = None
    try:
        scores_data = json.loads(lesson_row["scores_json"]) if lesson_row.get("scores_json") else None
    except (json.JSONDecodeError, TypeError) as exc:
        logger.warning("Failed to parse scores_json for %s: %s", lesson_id, exc)
        scores_data = None
    feedback_list = db.get_feedback_for_lesson(lesson_id)
    embed_snippet = (
        f'<script src="/static/widget.js" '
        f'data-lesson-id="{lesson_id}" '
        f'data-api-url="/api/chat/student"></script>'
    )

    class_codes = []
    try:
        from clawed.state import _get_conn as _state_conn
        from clawed.state import init_db as _state_init

        _state_init()
        with _state_conn() as sconn:
            cc_rows = sconn.execute(
                "SELECT class_code, name FROM classes WHERE active_lesson_id = ?",
                (lesson_id,),
            ).fetchall()
            class_codes = [{"code": r["class_code"], "name": r["name"]} for r in cc_rows]
    except (ImportError, sqlite3.OperationalError):
        pass

    return templates.TemplateResponse(request, "lesson.html", {
        "lesson": lesson_row,
        "lesson_data": lesson_data,
        "materials": materials_data,
        "scores": scores_data,
        "feedback_list": feedback_list,
        "share_url": f"/shared/{lesson_row['share_token']}",
        "embed_snippet": embed_snippet,
        "class_codes": class_codes,
    })


async def _page_share(request: Request, token: str, templates: Jinja2Templates) -> HTMLResponse:
    """Public shared lesson page (no auth required)."""
    db = get_db()
    lesson_row = db.get_lesson_by_token(token)
    if not lesson_row:
        return HTMLResponse("<h1>Lesson not found</h1>", status_code=404)
    try:
        lesson_data = json.loads(lesson_row["lesson_json"]) if lesson_row["lesson_json"] else {}
    except (json.JSONDecodeError, TypeError) as exc:
        logger.warning("Failed to parse shared lesson_json for token %s: %s", token, exc)
        lesson_data = {}
    return templates.TemplateResponse(request, "lesson.html", {
        "lesson": lesson_row,
        "lesson_data": lesson_data,
        "materials": None,
        "feedback_list": [],
        "share_url": f"/shared/{token}",
        "is_shared": True,
    })


def _register_page_routes(app: FastAPI, templates: Jinja2Templates) -> None:
    """Register the auth bootstrap endpoint and core HTML page routes.

    Covers: auth bootstrap, index/onboarding, dashboard, lessons list,
    generate, settings, stats, lesson detail, and share pages.
    """

    app.post("/api/auth/bootstrap")(_page_auth_bootstrap)

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> Any:
        return await _page_index(request, templates)

    @app.get("/dashboard", response_class=HTMLResponse)
    async def dashboard(request: Request) -> HTMLResponse:
        return await _page_dashboard(request, templates)

    @app.get("/lessons", response_class=HTMLResponse)
    async def lessons_list_page(request: Request) -> HTMLResponse:
        return await _page_lessons_list(request)

    @app.get("/generate", response_class=HTMLResponse)
    async def generate_page(request: Request) -> HTMLResponse:
        return await _page_generate(request, templates)

    @app.get("/settings", response_class=HTMLResponse)
    async def settings_page(request: Request) -> HTMLResponse:
        return await _page_settings(request, templates)

    @app.get("/stats", response_class=HTMLResponse)
    async def stats_page(request: Request) -> HTMLResponse:
        return await _page_stats(request, templates)

    @app.get("/lesson/{lesson_id}", response_class=HTMLResponse)
    async def lesson_page(request: Request, lesson_id: str) -> HTMLResponse:
        return await _page_lesson_detail(request, lesson_id, templates)

    @app.get("/share/{token}", response_class=HTMLResponse)
    @app.get("/shared/{token}", response_class=HTMLResponse)
    async def share_page(request: Request, token: str) -> HTMLResponse:
        return await _page_share(request, token, templates)


def _register_classroom_endpoints(app: FastAPI) -> None:
    """Register classroom-facing endpoints: student class pages and QR codes."""

    def _generate_qr_img(data: str) -> str:
        """Generate QR code locally. Falls back to plain link."""
        try:
            import base64
            import io

            import qrcode

            qr = qrcode.make(data)
            buf = io.BytesIO()
            # qrcode returns a PIL image whose .save accepts a format kwarg at runtime
            qr.save(buf, format="PNG")  # type: ignore[call-arg]
            b64 = base64.b64encode(buf.getvalue()).decode()
            return f'<img src="data:image/png;base64,{b64}" alt="QR Code" width="200">'
        except ImportError:
            return f'<a href="{data}">{data}</a>'

    @app.get("/student/{class_code}", response_class=HTMLResponse)
    async def student_class_page(request: Request, class_code: str) -> HTMLResponse:
        """Minimal student-facing page for a class code."""
        from clawed.state import _get_conn, init_db

        init_db()
        with _get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM classes WHERE class_code = ?", (class_code,)
            ).fetchone()

        if not row:
            return HTMLResponse("<h1>Class not found</h1>", status_code=404)

        class_name = row.get("name", class_code)
        class_topic = row.get("topic", "")
        teacher_id = row["teacher_id"]

        # Get teacher name
        teacher_name = teacher_id
        db = get_db()
        teacher = db.get_teacher(teacher_id)
        if teacher:
            teacher_name = teacher.get("name") or teacher_id

        # Get recent lesson topics from active lesson
        lesson_topics = []
        if row["active_lesson_json"]:
            try:
                lesson_data = json.loads(row["active_lesson_json"])
                lesson_topics.append(lesson_data.get("title", ""))
            except (json.JSONDecodeError, TypeError):
                pass

        esc_class_code = html_mod.escape(class_code)
        esc_class_name = html_mod.escape(class_name or class_code)
        esc_teacher_name = html_mod.escape(str(teacher_name))
        esc_class_topic = html_mod.escape(class_topic)
        esc_lesson_topics = [html_mod.escape(t) for t in lesson_topics if t]
        bot_link = f"https://t.me/clawed_bot?start={html_mod.escape(class_code)}"

        page_html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc_class_name} - Claw-ED</title>
<style>
body {{
  font-family: -apple-system, system-ui, sans-serif;
  max-width: 600px; margin: 40px auto;
  padding: 0 20px; background: #f8f9fa;
}}
.card {{
  background: white; border-radius: 12px; padding: 32px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1); text-align: center;
}}
h1 {{ color: #1a73e8; margin-bottom: 8px; }}
.teacher {{ color: #666; margin-bottom: 24px; }}
.code {{
  font-size: 2em; font-weight: bold; color: #1a73e8;
  background: #e8f0fe; padding: 12px 24px; border-radius: 8px;
  display: inline-block; margin: 16px 0; letter-spacing: 2px;
}}
.qr {{ margin: 24px 0; }}
.qr img {{ max-width: 200px; }}
.topic {{
  background: #e8f5e9; padding: 8px 16px;
  border-radius: 6px; margin: 8px 4px; display: inline-block;
}}
.join-btn {{
  display: inline-block; background: #1a73e8; color: white;
  padding: 14px 32px; border-radius: 8px;
  text-decoration: none; font-size: 1.1em; margin-top: 16px;
}}
.join-btn:hover {{ background: #1557b0; }}
.privacy {{ color: #999; font-size: 0.85em; margin-top: 24px; }}
</style></head><body>
<div class="card">
<h1>{esc_class_name}</h1>
<p class="teacher">Teacher: {esc_teacher_name}</p>
<div class="code">{esc_class_code}</div>
{''.join(f'<span class="topic">{t}</span>' for t in esc_lesson_topics)}
{f'<p><strong>Current Topic:</strong> {esc_class_topic}</p>' if class_topic else ''}
<p style="margin-top:24px"><strong>Scan to chat on Telegram:</strong></p>
<div class="qr">{_generate_qr_img(bot_link)}</div>
<a href="{bot_link}" class="join-btn">Open in Telegram</a>
<p class="privacy">No student data is displayed on this page.</p>
</div></body></html>"""

        return HTMLResponse(page_html)


def _safe_state_query(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    """Run a read query against state DB, returning list of Row dicts."""
    try:
        from clawed.state import _get_conn, init_db

        init_db()
        with _get_conn() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]
    except (ImportError, sqlite3.OperationalError):
        return []


def _build_daily_series(teacher_id: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build daily lessons and daily questions series for last 7 days."""
    day_names_short = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    today = datetime.now().date()

    daily_lessons: list[dict[str, Any]] = []
    daily_questions: list[dict[str, Any]] = []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        daily_lessons.append({"date": d.isoformat(), "label": day_names_short[d.weekday()], "count": 0})
        daily_questions.append({"date": d.isoformat(), "label": day_names_short[d.weekday()], "count": 0})

    rows = _safe_state_query(
        "SELECT DATE(created_at) as day, COUNT(*) as count FROM generated_lessons"
        " WHERE teacher_id = ? AND created_at >= datetime('now', '-7 days')"
        " GROUP BY day ORDER BY day",
        (teacher_id,),
    )
    day_counts = {r["day"]: r["count"] for r in rows}
    for item in daily_lessons:
        item["count"] = day_counts.get(item["date"], 0)

    q_rows = _safe_state_query(
        "SELECT DATE(created_at) as day, COUNT(*) as count FROM chat_messages"
        " WHERE role='user' AND created_at >= datetime('now', '-7 days')"
        " GROUP BY day ORDER BY day",
    )
    q_counts = {r["day"]: r["count"] for r in q_rows}
    for item in daily_questions:
        item["count"] = q_counts.get(item["date"], 0)

    return daily_lessons, daily_questions


async def _page_analytics(request: Request, templates: Jinja2Templates) -> HTMLResponse:
    """Analytics page with topic frequency, daily trends, quality trend."""
    if not _check_page_auth(request):
        return _AUTH_DENIED
    from clawed.analytics import get_teacher_stats

    db = get_db()
    teacher = db.get_default_teacher()
    teacher_id = teacher["id"] if teacher else "local-teacher"
    stats_data = get_teacher_stats(teacher_id)

    topic_frequency = _safe_state_query(
        "SELECT title as topic, COUNT(*) as count FROM generated_lessons"
        " WHERE teacher_id = ? AND title IS NOT NULL"
        " GROUP BY title ORDER BY count DESC LIMIT 10",
        (teacher_id,),
    )

    daily_lessons, daily_questions = _build_daily_series(teacher_id)

    quality_trend_rows = _safe_state_query(
        "SELECT strftime('%Y-W%W', created_at) as week, AVG(rating) as avg_rating"
        " FROM generated_lessons"
        " WHERE teacher_id = ? AND rating IS NOT NULL"
        " GROUP BY week ORDER BY week DESC LIMIT 12",
        (teacher_id,),
    )
    quality_trend = [
        {
            "week": r["week"],
            "week_short": r["week"][-3:] if r.get("week") else "",
            "avg_rating": round(r["avg_rating"], 1) if r.get("avg_rating") else 0,
        }
        for r in reversed(quality_trend_rows)
    ]

    top_questions = _safe_state_query(
        "SELECT content as question, COUNT(*) as count"
        " FROM chat_messages WHERE role='user'"
        " AND created_at >= datetime('now', '-7 days')"
        " GROUP BY content ORDER BY count DESC LIMIT 10",
    )

    return templates.TemplateResponse(request, "analytics.html", {
        "stats": stats_data,
        "topic_frequency": topic_frequency,
        "daily_lessons": daily_lessons,
        "daily_questions": daily_questions,
        "quality_trend": quality_trend,
        "top_questions": top_questions,
        "active_nav": "analytics",
    })


async def _page_library(request: Request, templates: Jinja2Templates) -> HTMLResponse:
    """Library view -- reuses _build_dashboard_context for consistency."""
    if not _check_page_auth(request):
        return _AUTH_DENIED
    db = get_db()
    stats = db.get_stats()
    units = db.list_units()
    for u in units:
        u["lesson_count"] = len(db.list_lessons(u["id"]))
    teacher = db.get_default_teacher()
    ctx = _build_dashboard_context(db, units, teacher)
    return templates.TemplateResponse(request, "dashboard.html", {
        "stats": stats,
        "units": units,
        **ctx,
        "active_nav": "library",
    })


async def _page_students(request: Request, templates: Jinja2Templates) -> HTMLResponse:
    """Students page -- chat activity and student engagement."""
    if not _check_page_auth(request):
        return _AUTH_DENIED
    db = get_db()
    stats = db.get_stats()

    lesson_chats: list[dict[str, Any]] = []
    units = db.list_units()
    for u in units[:10]:
        for lesson in db.list_lessons(u["id"]):
            history = db.get_chat_history(lesson["id"], limit=100)
            user_msgs = [m for m in history if m.get("role") == "user"]
            if user_msgs:
                lesson_chats.append({
                    "lesson_title": lesson.get("title") or "Untitled",
                    "lesson_id": lesson["id"],
                    "question_count": len(user_msgs),
                    "last_question": (user_msgs[0].get("created_at") or "")[:16] if user_msgs else "",
                })
    lesson_chats.sort(key=lambda x: x["question_count"], reverse=True)

    return templates.TemplateResponse(request, "students.html", {
        "stats": stats,
        "lesson_chats": lesson_chats[:20],
        "active_nav": "students",
    })


async def _page_profile(request: Request, templates: Jinja2Templates) -> HTMLResponse:
    """Profile page with API keys, state frameworks, telegram config."""
    if not _check_page_auth(request):
        return _AUTH_DENIED
    from clawed.config import get_api_key, mask_api_key
    from clawed.models import AppConfig
    from clawed.state_standards import list_states

    cfg = AppConfig.load()
    db = get_db()
    teacher = db.get_default_teacher()
    persona_data = None
    if teacher and teacher.get("persona_json"):
        with suppress(json.JSONDecodeError, TypeError):
            persona_data = json.loads(teacher["persona_json"])

    profile = cfg.teacher_profile
    state_frameworks = _build_state_frameworks(profile.state)

    telegram_token_masked = ""
    if cfg.telegram_bot_token:
        telegram_token_masked = mask_api_key(cfg.telegram_bot_token)

    return templates.TemplateResponse(request, "profile.html", {
        "profile": profile,
        "persona": persona_data,
        "states": list_states(),
        "state_frameworks": state_frameworks,
        "anthropic_key_masked": mask_api_key(get_api_key("anthropic")),
        "openai_key_masked": mask_api_key(get_api_key("openai")),
        "telegram_token_masked": telegram_token_masked,
    })


def _register_community_endpoints(app: FastAPI, templates: Jinja2Templates) -> None:
    """Register analytics, library, students, and profile page routes."""

    @app.get("/analytics", response_class=HTMLResponse)
    async def analytics_page(request: Request) -> HTMLResponse:
        return await _page_analytics(request, templates)

    @app.get("/library", response_class=HTMLResponse)
    async def library_page(request: Request) -> HTMLResponse:
        return await _page_library(request, templates)

    @app.get("/students", response_class=HTMLResponse)
    async def students_page(request: Request) -> HTMLResponse:
        return await _page_students(request, templates)

    @app.get("/profile", response_class=HTMLResponse)
    async def profile_page(request: Request) -> HTMLResponse:
        return await _page_profile(request, templates)


# ── Factory ─────────────────────────────────────────────────────────


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Delegates to focused helpers for middleware, API routes, page routes,
    classroom endpoints, and community/analytics endpoints.
    """
    from clawed import __version__

    app = FastAPI(
        title="Claw-ED",
        description="Your teaching files, your AI co-teacher.",
        version=__version__,
        lifespan=lifespan,
    )

    templates = _configure_middleware(app)
    _register_api_routes(app)
    _register_page_routes(app, templates)
    _register_classroom_endpoints(app)
    _register_community_endpoints(app, templates)

    return app


# Module-level app for `uvicorn clawed.api.server:app`
app = create_app()
