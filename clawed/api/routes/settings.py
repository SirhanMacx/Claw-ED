"""Settings and health check API routes."""

from __future__ import annotations

import json
import os

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from clawed import __version__
from clawed.api.deps import get_db, require_auth
from clawed.config import (
    get_api_key,
    mask_api_key,
    set_api_key,
    test_llm_connection,
)
from clawed.models import AppConfig, LLMProvider

router = APIRouter(tags=["settings"])


class SaveSettingsRequest(BaseModel):
    provider: str
    api_key: str | None = None
    anthropic_model: str = "claude-sonnet-4-6"
    openai_model: str = "gpt-4o"
    ollama_model: str = "llama3.2"
    ollama_base_url: str = "http://localhost:11434"
    default_grade: str = ""
    default_subject: str = ""
    include_homework: bool = True
    export_format: str = "markdown"


class PersonaFormRequest(BaseModel):
    name: str
    subject_area: str = ""
    grade_levels: str = ""
    teaching_style: str = "direct_instruction"
    preferred_lesson_format: str = ""


class OnboardingStepRequest(BaseModel):
    teacher_id: str
    step: int


@router.get("/health")
async def health_check():
    """Lightweight liveness check — no DB or LLM calls."""
    return {
        "status": "ok",
        "version": __version__,
    }


@router.get("/health/diagnostics", dependencies=[Depends(require_auth)])
async def health_diagnostics():
    """Full diagnostics endpoint with DB stats and LLM connection test."""
    cfg = AppConfig.load()
    db = get_db()
    teacher = db.get_default_teacher()
    stats = db.get_stats()

    connection = await test_llm_connection(cfg)

    return {
        "status": "ok",
        "llm_provider": cfg.provider.value,
        "llm_model": getattr(cfg, f"{cfg.provider.value}_model", ""),
        "llm_connected": connection.get("connected", False),
        "persona_loaded": teacher is not None and teacher.get("persona_json") is not None,
        "units_generated": stats["units"],
        "lessons_generated": stats["lessons"],
        "db_size_mb": round(db.db_size_mb(), 2),
        "version": __version__,
    }


@router.get("/settings", dependencies=[Depends(require_auth)])
async def get_settings():
    """Get current settings (API keys masked)."""
    cfg = AppConfig.load()
    anthropic_key = get_api_key("anthropic")
    openai_key = get_api_key("openai")

    return {
        "provider": cfg.provider.value,
        "anthropic_model": cfg.anthropic_model,
        "openai_model": cfg.openai_model,
        "ollama_model": cfg.ollama_model,
        "ollama_base_url": cfg.ollama_base_url,
        "anthropic_key_masked": mask_api_key(anthropic_key),
        "openai_key_masked": mask_api_key(openai_key),
        "has_anthropic_key": bool(anthropic_key),
        "has_openai_key": bool(openai_key),
        "include_homework": cfg.include_homework,
        "export_format": cfg.export_format,
    }


def _validate_ollama_url(raw: str) -> tuple[str | None, str | None]:
    """Return (normalized_url, error). None error means valid.

    v4.11.2026 SSRF protection. The previous version accepted any URL the
    caller supplied and fed it into httpx for test-connection. An authed
    user could aim it at internal endpoints like http://169.254.169.254
    (cloud metadata), http://10.x.y.z (internal LAN), or
    http://[::1]:<port> (loopback to another local service) and read the
    response via error messages.

    This validator enforces:
    - scheme must be http or https
    - hostname must not be empty
    - hostname must resolve to a loopback address OR be explicitly
      allowlisted via the EDUAGENT_OLLAMA_ALLOW_HOSTS env var
    """
    import ipaddress
    from urllib.parse import urlparse

    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"}:
        return None, "ollama_base_url must use http:// or https://"
    host = (parsed.hostname or "").lower()
    if not host:
        return None, "ollama_base_url is missing a host"

    allow_env = os.environ.get("EDUAGENT_OLLAMA_ALLOW_HOSTS", "")
    extra_allowed = {h.strip().lower() for h in allow_env.split(",") if h.strip()}

    # Loopback names are always allowed.
    if host in {"localhost", "127.0.0.1", "::1"}:
        pass
    elif host in extra_allowed:
        pass
    else:
        # Try parsing as an IP and require it to be loopback.
        try:
            ip = ipaddress.ip_address(host)
            if not ip.is_loopback:
                return None, (
                    "ollama_base_url must be a loopback address "
                    "or be listed in EDUAGENT_OLLAMA_ALLOW_HOSTS."
                )
        except ValueError:
            return None, (
                "ollama_base_url must target localhost or an explicitly "
                "allow-listed host (EDUAGENT_OLLAMA_ALLOW_HOSTS)."
            )

    normalized = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
    return normalized, None


@router.post("/settings", dependencies=[Depends(require_auth)])
async def save_settings(req: SaveSettingsRequest):
    """Save settings and optionally update API key."""
    cfg = AppConfig.load()
    cfg.provider = LLMProvider(req.provider)
    cfg.anthropic_model = req.anthropic_model
    cfg.openai_model = req.openai_model
    cfg.ollama_model = req.ollama_model

    # v4.11.2026 SSRF fix: validate and normalize ollama_base_url.
    normalized_url, err = _validate_ollama_url(req.ollama_base_url)
    if err:
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": err}, status_code=400)
    cfg.ollama_base_url = normalized_url

    cfg.include_homework = req.include_homework
    cfg.export_format = req.export_format
    cfg.save()

    if req.api_key and req.api_key.strip():
        set_api_key(req.provider, req.api_key.strip())

    return {"status": "saved"}


@router.get("/settings/test-connection", dependencies=[Depends(require_auth)])
async def test_connection():
    """Test the current LLM connection."""
    cfg = AppConfig.load()
    result = await test_llm_connection(cfg)
    return result


@router.post("/settings/clear-content", dependencies=[Depends(require_auth)])
async def clear_content():
    """Clear all generated content (danger zone)."""
    db = get_db()
    db.clear_all_generated()
    return {"status": "cleared"}


@router.post("/settings/reset", dependencies=[Depends(require_auth)])
async def reset_all():
    """Full reset — clear everything and restart onboarding."""
    db = get_db()
    db.reset_all()
    return {"status": "reset"}


@router.post("/onboarding/persona-form", dependencies=[Depends(require_auth)])
async def create_persona_from_form(req: PersonaFormRequest):
    """Create a persona from the quick form (no file upload needed)."""
    from clawed.models import TeacherPersona, TeachingStyle

    style_map = {
        "direct_instruction": TeachingStyle.DIRECT_INSTRUCTION,
        "socratic": TeachingStyle.SOCRATIC,
        "inquiry_based": TeachingStyle.INQUIRY_BASED,
        "project_based": TeachingStyle.PROJECT_BASED,
    }

    persona = TeacherPersona(
        name=req.name,
        teaching_style=style_map.get(req.teaching_style, TeachingStyle.DIRECT_INSTRUCTION),
        subject_area=req.subject_area,
        grade_levels=[g.strip() for g in req.grade_levels.split(",") if g.strip()],
        preferred_lesson_format=req.preferred_lesson_format or "I Do / We Do / You Do",
    )

    db = get_db()
    persona_json = persona.model_dump_json()
    teacher_id = db.upsert_teacher(persona.name, persona_json)

    return {"teacher_id": teacher_id, "persona": persona.model_dump()}


@router.post("/onboarding/step", dependencies=[Depends(require_auth)])
async def update_onboarding_step(req: OnboardingStepRequest):
    """Update onboarding progress for a teacher."""
    db = get_db()
    db.upsert_onboarding(req.teacher_id, req.step)
    return {"status": "ok", "step": req.step}


@router.get("/onboarding/state", dependencies=[Depends(require_auth)])
async def get_onboarding_state():
    """Get current onboarding state."""
    db = get_db()
    teacher = db.get_default_teacher()
    if not teacher:
        return {"has_persona": False, "step_completed": 0, "teacher_id": None}

    onboarding = db.get_onboarding(teacher["id"])
    persona_data = None
    if teacher.get("persona_json"):
        try:
            persona_data = json.loads(teacher["persona_json"])
        except (json.JSONDecodeError, TypeError):
            pass

    return {
        "has_persona": persona_data is not None,
        "step_completed": onboarding["step_completed"] if onboarding else 0,
        "teacher_id": teacher["id"],
        "persona": persona_data,
    }
