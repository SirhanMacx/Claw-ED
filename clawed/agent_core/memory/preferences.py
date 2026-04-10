"""Teacher preference learning — extract signals from feedback, ratings, and approvals."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def extract_preferences(teacher_id: str) -> dict[str, Any]:
    """Extract teacher preferences from feedback history and approval patterns.

    Returns a dict with preference signals for the system prompt.
    """
    preferences: dict[str, Any] = {
        "positive_patterns": [],
        "negative_patterns": [],
        "structural_prefs": [],
        "summary": "",
    }

    # From feedback/ratings
    try:
        from clawed.database import Database
        from clawed.feedback import analyze_feedback

        db = Database()
        analysis = analyze_feedback(db)
        if analysis.get("most_edited_sections"):
            for section in analysis["most_edited_sections"][:3]:
                preferences["structural_prefs"].append(f"Teacher often edits '{section}' — adjust this section")
    except Exception as e:
        logger.debug("Feedback analysis failed: %s", e)

    # From memory engine patterns
    try:
        from clawed.memory_engine import build_improvement_context

        ctx = build_improvement_context()
        if ctx:
            preferences["summary"] = ctx
    except Exception as e:
        logger.debug("Memory engine context failed: %s", e)

    # From approval patterns
    try:
        from clawed.agent_core.autonomy import ApprovalTracker

        tracker = ApprovalTracker()
        autonomy_summary = tracker.summarize_for_prompt()
        if autonomy_summary:
            preferences["autonomy_summary"] = autonomy_summary
    except Exception as e:
        logger.debug("Approval tracking failed: %s", e)

    return preferences


def summarize_preferences(prefs: dict[str, Any]) -> str:
    """Render preferences as a prompt section."""
    parts = []
    if prefs.get("structural_prefs"):
        parts.append("Structural preferences:")
        for p in prefs["structural_prefs"]:
            parts.append(f"  - {p}")
    if prefs.get("positive_patterns"):
        parts.append("What works well:")
        for p in prefs["positive_patterns"]:
            parts.append(f"  - {p}")
    if prefs.get("negative_patterns"):
        parts.append("What to avoid:")
        for p in prefs["negative_patterns"]:
            parts.append(f"  - {p}")
    return "\n".join(parts) if parts else ""
