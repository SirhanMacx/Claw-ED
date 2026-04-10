"""Export routes — PDF, DOCX, Markdown downloads, share links, and import."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from clawed.api.deps import get_db, require_auth
from clawed.database import Database
from clawed.models import DailyLesson

router = APIRouter(tags=["export"], dependencies=[Depends(require_auth)])
public_router = APIRouter(tags=["public"])


class ImportRequest(BaseModel):
    url: Optional[str] = None
    token: Optional[str] = None
    server: str = "http://localhost:8000"


@router.get("/export/{lesson_id}")
async def export_lesson_endpoint(lesson_id: str, fmt: str = "markdown"):
    """Export a lesson as Markdown, PDF, or DOCX."""
    from clawed.export_markdown import export_lesson

    db = get_db()
    lesson_row = db.get_lesson(lesson_id)
    if not lesson_row:
        return JSONResponse({"error": "Lesson not found."}, status_code=404)

    lesson = DailyLesson.model_validate_json(lesson_row["lesson_json"])
    tmp_dir = Path(tempfile.mkdtemp())

    if fmt == "markdown":
        path = export_lesson(lesson, tmp_dir, fmt="markdown")
        return FileResponse(str(path), filename=path.name, media_type="text/markdown")
    elif fmt == "pdf":
        path = export_lesson(lesson, tmp_dir, fmt="pdf")
        return FileResponse(str(path), filename=path.name, media_type="application/pdf")
    elif fmt == "docx":
        path = export_lesson(lesson, tmp_dir, fmt="docx")
        return FileResponse(
            str(path),
            filename=path.name,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    else:
        return JSONResponse({"error": f"Unsupported format: {fmt}"}, status_code=400)


@router.post("/export/{lesson_id}/classroom")
async def export_classroom(lesson_id: str):
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
        coursework_materials.append({"description": {"text": worksheet_desc}})

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
async def share_lesson_api(token: str):
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
async def import_lesson(req: ImportRequest):
    """Import a lesson from a share URL or token."""
    token = req.token
    fetch_server = req.server.rstrip("/")

    if req.url:
        parsed = urlparse(req.url)
        if parsed.scheme and parsed.netloc:
            token = parsed.path.rstrip("/").rsplit("/", 1)[-1]
            fetch_server = f"{parsed.scheme}://{parsed.netloc}"

    if not token:
        return JSONResponse({"error": "Provide a url or token."}, status_code=400)

    # Security: restrict fetch to localhost unless explicitly allowed
    _allowed_prefixes = ["http://localhost", "http://127.0.0.1"]
    _extra = os.environ.get("EDUAGENT_IMPORT_ALLOW_URLS", "")
    if _extra:
        _allowed_prefixes.extend(u.strip() for u in _extra.split(",") if u.strip())
    if not any(fetch_server.startswith(prefix) for prefix in _allowed_prefixes):
        return JSONResponse(
            {"error": "Import URL not allowed. Only localhost or configured URLs are permitted."},
            status_code=403,
        )

    fetch_url = f"{fetch_server}/share/{token}"

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(fetch_url)
    except httpx.HTTPError as exc:
        return JSONResponse({"error": f"Network error: {exc}"}, status_code=502)

    if resp.status_code == 404:
        return JSONResponse({"error": "Lesson not found."}, status_code=404)
    if resp.status_code != 200:
        return JSONResponse(
            {"error": f"Upstream returned {resp.status_code}"},
            status_code=502,
        )

    try:
        data = resp.json()
    except (json.JSONDecodeError, ValueError):
        return JSONResponse({"error": "Invalid JSON from upstream."}, status_code=502)

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
