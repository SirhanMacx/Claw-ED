"""Style profile routes — the "Your Materials" surface in the Mac app.

The teacher picks a folder; we ingest it (read-only, home-bounded,
secrets-denied — same policy as the ingest_materials tool, which this
reuses), build a STYLE PROFILE, and let the UI activate/deactivate or
remove profiles. Picking the folder in the app IS the approval — these
routes are only reachable from the authed local UI.

Privacy: profiles and analysis caches live on this Mac under the agent's
data dir. Only short excerpts go to the teacher's configured LLM during
analysis. Nothing is uploaded anywhere else.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from clawed.api.deps import limiter, require_auth

logger = logging.getLogger(__name__)

router = APIRouter(tags=["style"], dependencies=[Depends(require_auth)])


# ── Background ingest job (one at a time — it's a single teacher) ────

_job_lock = threading.Lock()
_job: dict[str, Any] = {"status": "idle"}


def _job_snapshot() -> dict[str, Any]:
    with _job_lock:
        return dict(_job)


def _job_update(**fields: Any) -> None:
    with _job_lock:
        _job.update(fields)


def _profile_payload(profile: Any, active_id: str | None) -> dict[str, Any]:
    data: dict[str, Any] = profile.model_dump()
    data["active"] = profile.profile_id == active_id
    return data


def _run_ingest_job(path: str, profile_name: str) -> None:
    """Worker thread: run the ingest tool end-to-end with its own loop."""
    from clawed.agent_core.context import AgentContext
    from clawed.agent_core.tools.ingest_materials import IngestMaterialsTool
    from clawed.models import AppConfig

    def progress(message: str) -> None:
        _job_update(progress=message)

    try:
        config = AppConfig.load()
        try:
            from clawed.agent_core.identity import get_teacher_id
            teacher_id = get_teacher_id()
        except Exception:
            teacher_id = "default"

        context = AgentContext(
            teacher_id=teacher_id,
            config=config,
            teacher_profile={},
            persona=None,
            session_history=[],
            improvement_context="",
            transport="mac_app",
            progress_callback=progress,
        )
        tool = IngestMaterialsTool()
        result = asyncio.run(
            tool.execute({"path": path, "profile_name": profile_name}, context)
        )
        ok = bool(result.data.get("style_profile_id"))
        _job_update(
            status="done" if ok else "error",
            result_text=result.text[:4000],
            files_ingested=result.data.get("files_ingested", 0),
            files_skipped=result.data.get("files_skipped", 0),
            profile_id=result.data.get("style_profile_id"),
            progress="",
        )
    except Exception as exc:
        logger.error("Style ingest job failed", exc_info=True)
        _job_update(status="error", result_text=f"Ingest failed: {exc}", progress="")


class StyleIngestRequest(BaseModel):
    path: str = Field(..., min_length=1, max_length=1000)
    profile_name: str = Field("", max_length=120)


@router.post("/style/ingest")
@limiter.limit("6/minute")
async def start_style_ingest(request: Request, req: StyleIngestRequest) -> Any:
    """Start ingesting a folder of the teacher's materials (background)."""
    resolved = Path(req.path).expanduser()
    if not resolved.exists():
        return JSONResponse({"error": f"Path not found: {req.path}"}, status_code=400)

    # Same home/secrets policy the tool enforces — fail fast with a clear message.
    from clawed.agent_core.tools.ingest_materials import IngestMaterialsTool
    deny = IngestMaterialsTool._deny_reason(resolved.resolve())
    if deny:
        return JSONResponse({"error": deny}, status_code=403)

    with _job_lock:
        if _job.get("status") == "running":
            return JSONResponse(
                {"error": "An ingest is already running — let it finish first."},
                status_code=409,
            )
        _job.clear()
        _job.update({
            "status": "running",
            "path": str(resolved),
            "progress": "Scanning folder…",
        })

    name = req.profile_name.strip() or resolved.name
    threading.Thread(
        target=_run_ingest_job, args=(str(resolved), name), daemon=True,
    ).start()
    return {"status": "running", "path": str(resolved), "profile_name": name}


@router.get("/style/ingest/status")
async def style_ingest_status(request: Request) -> Any:
    """Poll the running (or last) ingest job."""
    return _job_snapshot()


@router.get("/style/profiles")
async def list_style_profiles(request: Request) -> Any:
    """All learned style profiles + which one is active."""
    from clawed import style_profile as sp

    active_id = sp.get_active_profile_id()
    return {
        "active": active_id,
        "profiles": [
            _profile_payload(p, active_id) for p in sp.list_profiles()
        ],
    }


@router.post("/style/profiles/{profile_id}/activate")
async def activate_style_profile(request: Request, profile_id: str) -> Any:
    from clawed import style_profile as sp

    if sp.load_profile(profile_id) is None:
        return JSONResponse({"error": "No such profile"}, status_code=404)
    sp.set_active_profile(profile_id)
    return {"active": profile_id}


@router.post("/style/deactivate")
async def deactivate_style_profile(request: Request) -> Any:
    """Off-switch: back to the default MacxLabs style."""
    from clawed import style_profile as sp

    sp.set_active_profile(None)
    return {"active": None}


@router.delete("/style/profiles/{profile_id}")
async def remove_style_profile(request: Request, profile_id: str) -> Any:
    from clawed import style_profile as sp

    if not sp.delete_profile(profile_id):
        return JSONResponse({"error": "No such profile"}, status_code=404)
    return {"deleted": profile_id, "active": sp.get_active_profile_id()}
