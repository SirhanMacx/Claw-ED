"""Unified teacher identity — one Ed, one teacher, everywhere.

All transports (CLI, Telegram, MCP, scheduled tasks) resolve to
the same teacher_id so Ed's memory, KB, episodes, and sessions
are shared across every interaction surface.
"""

from __future__ import annotations

import hashlib
import logging
import os

logger = logging.getLogger(__name__)

_cached_id: str | None = None


def get_teacher_id() -> str:
    """Return a consistent teacher ID regardless of transport.

    Resolution order:
      1. EDUAGENT_TEACHER_ID env var (explicit override)
      2. Hash of teacher_profile.name from config.json
      3. "default" (fallback for unconfigured installs)

    Only caches when a real profile-derived ID is found. The "default"
    fallback is NEVER cached so that when the teacher completes
    onboarding in a different process (e.g., CLI), the Telegram bot
    picks up the new profile on the next message.
    """
    global _cached_id
    if _cached_id is not None:
        return _cached_id

    # 1. Explicit override
    env_id = os.environ.get("EDUAGENT_TEACHER_ID")
    if env_id:
        _cached_id = env_id
        return _cached_id

    # 2. Derive from teacher profile
    try:
        from clawed.models import AppConfig

        config = AppConfig.load()
        tp = config.teacher_profile
        if tp and tp.name:
            # Stable hash so the ID survives config edits to other fields
            raw = f"{tp.name.lower().strip()}"
            _cached_id = f"teacher-{hashlib.sha256(raw.encode()).hexdigest()[:12]}"
            return _cached_id
    except Exception as e:
        logger.debug("Could not derive teacher_id from config: %s", e)

    # 3. Fallback — NOT cached so we re-check config.json next time
    # (teacher may complete onboarding in another process)
    return "default"


def get_teacher_name() -> str:
    """Return the teacher's display name from config, or 'Teacher'."""
    try:
        from clawed.models import AppConfig

        config = AppConfig.load()
        tp = config.teacher_profile
        if tp and tp.name:
            return tp.name
    except Exception:
        pass
    return "Teacher"


def reset_cache() -> None:
    """Clear the cached teacher_id (useful for tests)."""
    global _cached_id
    _cached_id = None
