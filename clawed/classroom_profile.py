"""Persistent classroom profile — remembers the physical and social context.

Stores information about the classroom environment, student demographics,
available technology, and recurring patterns so Ed can generate lessons
that fit THIS classroom, not a generic one.

Saved as JSON in ~/.eduagent/classroom_profile.json.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_BASE = Path(
    os.environ.get(
        "EDUAGENT_DATA_DIR",
        str(Path.home() / ".eduagent"),
    )
)
_PROFILE_PATH = _BASE / "classroom_profile.json"


class ClassroomProfile(BaseModel):
    """Persistent classroom context that shapes every generated lesson."""

    # Physical environment
    room_number: str = ""
    student_count: int = 0
    seating_arrangement: str = ""  # "rows", "clusters", "u-shape", "flexible"
    has_smartboard: bool = False
    has_projector: bool = False
    has_chromebooks: bool = False
    has_ipads: bool = False
    has_lab_access: bool = False
    other_tech: list[str] = Field(default_factory=list)  # ["document camera", "speakers"]

    # Student demographics
    ell_count: int = 0
    iep_count: int = 0
    plan_504_count: int = 0
    gifted_count: int = 0
    reading_level_range: str = ""  # "Grade 5-9" — spread in the room

    # Scheduling
    period_length_minutes: int = 40
    periods_per_day: list[str] = Field(default_factory=list)  # ["Period 1", "Period 3", "Period 6"]
    school_name: str = ""

    # Curriculum context
    textbook: str = ""  # "McGraw-Hill US History"
    lms_platform: str = ""  # "Google Classroom", "Canvas", "Schoology"
    standards_framework: str = ""  # "NYS", "Common Core", "NGSS"
    state: str = ""  # "NY", "CA", "TX"

    # Teacher preferences (learned over time)
    preferred_grouping: str = ""  # "pairs", "table groups of 4", "whole class"
    noise_tolerance: str = ""  # "quiet work", "structured talk", "lively discussion"
    preferred_activities: list[str] = Field(default_factory=list)
    avoided_activities: list[str] = Field(default_factory=list)

    # Notes
    notes: str = ""  # Free-text for anything else


def load_profile() -> ClassroomProfile:
    """Load the classroom profile from disk, or return defaults."""
    if _PROFILE_PATH.exists():
        try:
            data = json.loads(_PROFILE_PATH.read_text(encoding="utf-8"))
            return ClassroomProfile(**data)
        except Exception as exc:
            logger.warning("Failed to load classroom profile: %s", exc)
    return ClassroomProfile()


def save_profile(profile: ClassroomProfile) -> None:
    """Save the classroom profile to disk."""
    _PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _PROFILE_PATH.write_text(
        profile.model_dump_json(indent=2),
        encoding="utf-8",
    )
    logger.info("Classroom profile saved to %s", _PROFILE_PATH)


def update_profile(updates: dict[str, Any]) -> ClassroomProfile:
    """Update specific fields and save."""
    profile = load_profile()
    for key, value in updates.items():
        if hasattr(profile, key):
            setattr(profile, key, value)
    save_profile(profile)
    return profile


def profile_to_prompt_context() -> str:
    """Convert the classroom profile into prompt context for lesson generation.

    Returns a string to inject into the system prompt so the LLM knows
    about the physical classroom, student needs, and available resources.
    """
    profile = load_profile()

    # Skip if profile is essentially empty
    if not profile.student_count and not profile.school_name:
        return ""

    parts: list[str] = []

    if profile.school_name:
        parts.append(f"School: {profile.school_name}")
    if profile.student_count:
        parts.append(f"Class size: {profile.student_count} students")
    if profile.period_length_minutes:
        parts.append(f"Period length: {profile.period_length_minutes} minutes")

    # Technology
    tech: list[str] = []
    if profile.has_smartboard:
        tech.append("SmartBoard")
    if profile.has_projector:
        tech.append("projector")
    if profile.has_chromebooks:
        tech.append("Chromebooks (1:1)")
    if profile.has_ipads:
        tech.append("iPads")
    if profile.has_lab_access:
        tech.append("lab access")
    tech.extend(profile.other_tech)
    if tech:
        parts.append(f"Available tech: {', '.join(tech)}")

    # Student needs
    needs: list[str] = []
    if profile.ell_count:
        needs.append(f"{profile.ell_count} ELL students")
    if profile.iep_count:
        needs.append(f"{profile.iep_count} IEP students")
    if profile.plan_504_count:
        needs.append(f"{profile.plan_504_count} with 504 plans")
    if profile.gifted_count:
        needs.append(f"{profile.gifted_count} gifted/accelerated")
    if needs:
        parts.append(f"Student needs: {', '.join(needs)}")

    if profile.reading_level_range:
        parts.append(f"Reading level spread: {profile.reading_level_range}")

    if profile.seating_arrangement:
        parts.append(f"Seating: {profile.seating_arrangement}")

    if profile.preferred_grouping:
        parts.append(f"Preferred grouping: {profile.preferred_grouping}")

    if profile.lms_platform:
        parts.append(f"LMS: {profile.lms_platform}")

    if profile.textbook:
        parts.append(f"Textbook: {profile.textbook}")

    if not parts:
        return ""

    return (
        "## Classroom Context (from saved profile)\n" + "\n".join(f"- {p}" for p in parts) + "\n"
        "Design ALL activities to work in THIS specific classroom."
    )
