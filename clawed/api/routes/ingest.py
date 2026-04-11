"""Ingest routes — file upload and persona extraction."""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import JSONResponse

from clawed.api.deps import get_db, limiter, require_auth
from clawed.ingestor import ingest_path
from clawed.persona import extract_persona

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ingest"], dependencies=[Depends(require_auth)])


# F9 audit fix: per-file and per-request size limits
_MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB per file
_MAX_REQUEST_SIZE = 500 * 1024 * 1024  # 500 MB total
_MAX_FILES = 200


@router.post("/ingest")
@limiter.limit("3/minute")
async def ingest_files(
    request: Request,  # required by rate limiter
    files: list[UploadFile] = File(...),
):
    """Upload teaching materials and extract a teacher persona.

    v4.11.2026: rate-limited at 3 requests per minute per client IP.
    The previous version had no limit, so an authed client could push
    500 MB per call repeatedly and exhaust disk + LLM credits.
    """
    if not files:
        return JSONResponse({"error": "No files uploaded"}, status_code=400)
    if len(files) > _MAX_FILES:
        return JSONResponse(
            {"error": f"Too many files ({len(files)}). Maximum is {_MAX_FILES}."},
            status_code=400,
        )

    # Save uploaded files to a temp directory with size enforcement
    total_size = 0
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        for f in files:
            # Sanitize filename to prevent path traversal
            raw_name = os.path.basename(f.filename or "upload")
            safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", raw_name) or "upload"
            dest = tmp_path / safe_name

            # Stream to disk in chunks instead of reading all into memory
            file_size = 0
            with open(dest, "wb") as out:
                while True:
                    chunk = await f.read(1024 * 1024)  # 1MB chunks
                    if not chunk:
                        break
                    file_size += len(chunk)
                    if file_size > _MAX_FILE_SIZE:
                        dest.unlink(missing_ok=True)
                        return JSONResponse(
                            {"error": f"File '{raw_name}' exceeds {_MAX_FILE_SIZE // (1024*1024)}MB limit."},
                            status_code=413,
                        )
                    total_size += len(chunk)
                    if total_size > _MAX_REQUEST_SIZE:
                        return JSONResponse(
                            {"error": f"Total upload exceeds {_MAX_REQUEST_SIZE // (1024*1024)}MB limit."},
                            status_code=413,
                        )
                    out.write(chunk)

        # Ingest all files
        documents = ingest_path(tmp_path)

    if not documents:
        return JSONResponse({"error": "No supported documents found in upload"}, status_code=400)

    # Extract persona
    try:
        persona = await extract_persona(documents)
    except Exception:
        logger.error("Persona extraction failed", exc_info=True)
        return JSONResponse({"error": "Persona extraction failed. Please try again."}, status_code=500)

    # Save to database
    db = get_db()
    persona_json = persona.model_dump_json()
    teacher_id = db.upsert_teacher(persona.name, persona_json)

    return {
        "teacher_id": teacher_id,
        "persona": persona.model_dump(),
        "documents_ingested": len(documents),
    }


@router.get("/persona")
async def get_persona():
    """Get the current teacher persona."""
    db = get_db()
    teacher = db.get_default_teacher()
    if not teacher or not teacher.get("persona_json"):
        return JSONResponse({"error": "No persona found. Upload teaching materials first."}, status_code=404)

    try:
        persona_data = json.loads(teacher["persona_json"])
    except (json.JSONDecodeError, TypeError) as exc:
        logger.warning("Failed to parse persona_json: %s", exc)
        return JSONResponse({"error": "Persona data is corrupted."}, status_code=500)
    return {"teacher_id": teacher["id"], "persona": persona_data}
