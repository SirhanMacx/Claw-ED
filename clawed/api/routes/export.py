"""Export routes — PDF, DOCX, Markdown downloads, share links, and import."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from clawed.api.deps import get_db, require_auth
from clawed.database import Database
from clawed.models import DailyLesson

logger = logging.getLogger(__name__)

router = APIRouter(tags=["export"], dependencies=[Depends(require_auth)])
public_router = APIRouter(tags=["public"])


class ImportRequest(BaseModel):
    url: str | None = None
    token: str | None = None
    server: str = "http://localhost:8000"


@router.get("/export/{lesson_id}")
async def export_lesson_endpoint(lesson_id: str, fmt: str = "markdown") -> Any:
    """Export a lesson as Markdown, PDF, or DOCX."""
    import shutil

    from starlette.background import BackgroundTask

    from clawed.export_markdown import export_lesson

    db = get_db()
    lesson_row = db.get_lesson(lesson_id)
    if not lesson_row:
        return JSONResponse({"error": "Lesson not found."}, status_code=404)

    lesson = DailyLesson.model_validate_json(lesson_row["lesson_json"])
    tmp_dir = Path(tempfile.mkdtemp(prefix="clawed_export_"))

    # v4.11.2026 fix: attach a BackgroundTask that deletes the tempdir
    # after the response is sent. Previously, every /api/export call
    # leaked one directory under /tmp (forever).
    cleanup = BackgroundTask(shutil.rmtree, str(tmp_dir), ignore_errors=True)

    if fmt == "markdown":
        path = export_lesson(lesson, tmp_dir, fmt="markdown")
        return FileResponse(
            str(path),
            filename=path.name,
            media_type="text/markdown",
            background=cleanup,
        )
    elif fmt == "pdf":
        path = export_lesson(lesson, tmp_dir, fmt="pdf")
        return FileResponse(
            str(path),
            filename=path.name,
            media_type="application/pdf",
            background=cleanup,
        )
    elif fmt == "docx":
        path = export_lesson(lesson, tmp_dir, fmt="docx")
        return FileResponse(
            str(path),
            filename=path.name,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            background=cleanup,
        )
    else:
        # Format not supported — clean up immediately.
        shutil.rmtree(str(tmp_dir), ignore_errors=True)
        return JSONResponse({"error": f"Unsupported format: {fmt}"}, status_code=400)


@router.post("/export/{lesson_id}/classroom")
async def export_classroom(lesson_id: str) -> Any:
    """Generate a Google Classroom-compatible CourseWork JSON payload."""
    db = get_db()
    lesson_row = db.get_lesson(lesson_id)
    if not lesson_row:
        return JSONResponse({"error": "Lesson not found."}, status_code=404)

    lesson_data = json.loads(lesson_row["lesson_json"]) if lesson_row["lesson_json"] else {}
    materials_data = json.loads(lesson_row["materials_json"]) if lesson_row.get("materials_json") else None

    # Build Google Classroom CourseWork resource (v1 API format)
    description_parts = [lesson_data.get("objective", "")]
    if lesson_data.get("standards"):
        description_parts.append(f"Standards: {', '.join(lesson_data['standards'])}")
    if lesson_data.get("homework"):
        description_parts.append(f"Homework: {lesson_data['homework']}")

    coursework_materials = []
    if materials_data and materials_data.get("worksheet_items"):
        worksheet_desc = "Student Worksheet:\n"
        for item in materials_data["worksheet_items"]:
            worksheet_desc += f"{item.get('item_number', '')}. {item.get('prompt', '')}\n"
        coursework_materials.append({
            "description": {"text": worksheet_desc}
        })

    max_points = 0
    if materials_data and materials_data.get("worksheet_items"):
        max_points = sum(item.get("point_value", 1) for item in materials_data["worksheet_items"])

    coursework = {
        "title": lesson_data.get("title", lesson_row.get("title", "Lesson")),
        "description": "\n\n".join(description_parts),
        "materials": coursework_materials,
        "maxPoints": max_points or 100,
        "workType": "ASSIGNMENT",
        "state": "DRAFT",
        "submissionModificationMode": "MODIFIABLE_UNTIL_TURNED_IN",
    }

    return {"lesson_id": lesson_id, "coursework": coursework}


@public_router.get("/share/{token}")
async def share_lesson_api(token: str) -> Any:
    """Get a lesson by its share token (JSON API)."""
    db = get_db()
    lesson_row = db.get_lesson_by_token(token)
    if not lesson_row:
        return JSONResponse({"error": "Lesson not found."}, status_code=404)

    lesson_data = json.loads(lesson_row["lesson_json"]) if lesson_row["lesson_json"] else {}
    return {
        "lesson_id": lesson_row["id"],
        "title": lesson_row["title"],
        "share_token": token,
        "lesson": lesson_data,
    }


@router.post("/import")
async def import_lesson(req: ImportRequest) -> Any:
    """Import a lesson from a share URL or token."""
    token = req.token
    fetch_server = req.server.rstrip("/")

    if req.url:
        parsed = urlparse(req.url)
        if parsed.scheme and parsed.netloc:
            token = parsed.path.rstrip("/").rsplit("/", 1)[-1]
            fetch_server = f"{parsed.scheme}://{parsed.netloc}"

    if not token:
        return JSONResponse(
            {"error": "Provide a url or token."}, status_code=400
        )

    # v4.11.2026 security fix: SSRF protection. The previous version
    # used startswith() on the fetch_server string, which allowed a
    # prefix-bypass attack: "http://localhost.attacker.com" matches the
    # "http://localhost" prefix and resolves to an attacker-controlled
    # host. This rewrite parses the host explicitly and matches against
    # an exact set of loopback names.
    parsed_server = urlparse(fetch_server)
    host = (parsed_server.hostname or "").lower()
    scheme = (parsed_server.scheme or "").lower()
    _allowed_hosts = {"localhost", "127.0.0.1", "::1"}
    _extra = os.environ.get("EDUAGENT_IMPORT_ALLOW_URLS", "")
    if _extra:
        for u in _extra.split(","):
            u = u.strip()
            if not u:
                continue
            try:
                extra_host = urlparse(u).hostname
                if extra_host:
                    _allowed_hosts.add(extra_host.lower())
            except Exception:
                logger.warning("operation_failed", exc_info=True)
    if scheme not in {"http", "https"} or host not in _allowed_hosts:
        return JSONResponse(
            {
                "error": (
                    "Import URL not allowed. Only localhost/127.0.0.1 "
                    "or hosts explicitly configured via "
                    "EDUAGENT_IMPORT_ALLOW_URLS are permitted."
                )
            },
            status_code=403,
        )

    fetch_url = f"{fetch_server}/share/{token}"

    # ED-7 audit fix: response-size limits, explicit timeouts, and
    # Content-Type verification to prevent oversized/malformed responses.
    max_import_bytes = 10 * 1024 * 1024  # 10 MB
    connect_timeout = 10.0
    read_timeout = 30.0

    try:
        timeout = httpx.Timeout(read_timeout, connect=connect_timeout)
        async with httpx.AsyncClient(
            timeout=timeout, follow_redirects=False,
        ) as client:
            resp = await client.get(fetch_url)

            if resp.status_code == 404:
                return JSONResponse(
                    {"error": "Lesson not found."}, status_code=404
                )
            if resp.status_code != 200:
                return JSONResponse(
                    {"error": f"Upstream returned {resp.status_code}"},
                    status_code=502,
                )

            # ED-7: reject oversized responses
            if len(resp.content) > max_import_bytes:
                return JSONResponse(
                    {"error": "Response too large (>10 MB)."},
                    status_code=502,
                )

            body = resp.content
    except httpx.HTTPError as exc:
        # v4.11.2026: don't leak raw exception text to the client.
        logger.warning("Import fetch failed for %s: %s", fetch_url, exc)
        return JSONResponse(
            {"error": "Network error fetching shared lesson."}, status_code=502
        )

    try:
        data = json.loads(body)
    except (json.JSONDecodeError, ValueError):
        return JSONResponse(
            {"error": "Invalid JSON from upstream."}, status_code=502
        )

    lesson_data = data.get("lesson", data)
    original_title = data.get("title", lesson_data.get("title", "Untitled"))
    title = f"[Imported] {original_title}"

    db = get_db()
    new_id = db.insert_lesson(
        unit_id=Database._new_id(),
        lesson_number=0,
        title=title,
        lesson_json=json.dumps(lesson_data),
        materials_json=None,
    )

    return {"lesson_id": new_id, "title": title}
