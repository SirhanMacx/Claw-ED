# clawed/agent_core/memory/curriculum.py
"""Layer 2: Curriculum state — projections from canonical database."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def load_curriculum_state(teacher_id: str) -> dict[str, Any]:
    """Load curriculum state from the canonical database.

    This is a read-only projection — the database is the source of truth.
    """
    state: dict[str, Any] = {
        "units_generated": 0,
        "lessons_generated": 0,
        "recent_topics": [],
        "standards_covered": [],
        "avg_rating": 0.0,
        "recent_feedback": [],
    }
    try:
        from clawed.database import Database

        db = Database()
        stats = db.get_stats()
        state["units_generated"] = stats.get("units", 0)
        state["lessons_generated"] = stats.get("lessons", 0)

        units = db.list_units()
        state["recent_topics"] = [u.get("title", "") for u in units[:5] if u.get("title")]
    except Exception as e:
        logger.debug("Could not load curriculum state: %s", e)
    return state


def summarize_curriculum_state(state: dict[str, Any]) -> str:
    """Summarize curriculum state for the system prompt."""
    parts = []
    if state["units_generated"]:
        parts.append(
            f"You've generated {state['units_generated']} units and {state['lessons_generated']} lessons together."
        )
    if state["recent_topics"]:
        parts.append(f"Recent topics: {', '.join(state['recent_topics'][:5])}.")
    if state["standards_covered"]:
        parts.append(f"Standards covered so far: {', '.join(state['standards_covered'][:10])}.")
    if state["avg_rating"]:
        parts.append(f"Average lesson rating: {state['avg_rating']:.1f}/5.")
    if state["recent_feedback"]:
        parts.append(f"Recent feedback: {'; '.join(state['recent_feedback'][:3])}.")
    return " ".join(parts) if parts else ""
