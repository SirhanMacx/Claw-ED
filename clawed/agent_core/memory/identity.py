"""Layer 1: Teacher identity — slow-changing profile and persona."""

from __future__ import annotations

import json
import logging
from typing import Any

from clawed.workspace import IDENTITY_PATH

logger = logging.getLogger(__name__)


def load_identity() -> dict[str, Any]:
    """Load teacher identity from workspace identity.md file."""
    result: dict[str, Any] = {"name": "", "raw": ""}
    try:
        if IDENTITY_PATH.exists():
            raw = IDENTITY_PATH.read_text(encoding="utf-8")
            result["raw"] = raw
            for line in raw.splitlines():
                if line.startswith("# "):
                    result["name"] = line[2:].strip()
                    break
    except Exception as e:
        logger.debug("Could not load identity: %s", e)
    return result


def load_identity_from_db(teacher_id: str) -> dict[str, Any]:
    """Load teacher profile and persona from canonical database."""
    result: dict[str, Any] = {"name": "", "persona": None, "profile": {}}
    try:
        from clawed.database import Database

        db = Database()
        teacher = db.get_default_teacher()
        if teacher:
            result["profile"] = dict(teacher)
            if teacher.get("persona_json"):
                result["persona"] = json.loads(teacher["persona_json"])
                result["name"] = result["persona"].get("name", "")
    except Exception as e:
        logger.debug("Could not load teacher from DB: %s", e)
    return result
