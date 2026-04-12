"""Multi-teacher school deployment — roster management and shared curriculum library.

Schools group teachers so they can share units and lessons with their
department or the whole building.  A school coordinator (role='admin')
can manage the roster and moderate the shared library.
"""

from __future__ import annotations

from typing import Any

from clawed.database import Database

# ── School lifecycle ──────────────────────────────────────────────────


def setup_school(
    db: Database,
    name: str,
    state: str = "",
    district: str = "",
    grade_levels: list[str] | None = None,
) -> str:
    """Create a new school and return its ID."""
    return db.create_school(name=name, district=district, state=state, grade_levels=grade_levels)


def get_school(db: Database, school_id: str) -> dict[str, Any] | None:
    """Look up a school by ID."""
    return db.get_school(school_id)


# ── Roster management ────────────────────────────────────────────────


def add_teacher(
    db: Database,
    school_id: str,
    teacher_id: str,
    role: str = "teacher",
    department: str = "",
) -> None:
    """Add a teacher to the school roster (or update their role/department)."""
    db.add_teacher_to_school(school_id, teacher_id, role=role, department=department)


def remove_teacher(db: Database, school_id: str, teacher_id: str) -> None:
    """Remove a teacher from the school roster."""
    db.remove_teacher_from_school(school_id, teacher_id)


def list_teachers(db: Database, school_id: str) -> list[dict[str, Any]]:
    """Return all teachers on the roster with their roles and departments."""
    return db.list_school_teachers(school_id)


# ── Shared curriculum library ────────────────────────────────────────


def share_unit(
    db: Database,
    school_id: str,
    teacher_id: str,
    unit_id: str,
    department: str = "",
) -> str | None:
    """Share a unit with the school (or a specific department).

    Returns the shared-content ID, or None if the unit doesn't exist.
    """
    unit = db.get_unit(unit_id)
    if not unit:
        return None
    return db.share_content(
        school_id=school_id,
        teacher_id=teacher_id,
        content_type="unit",
        content_id=unit_id,
        title=unit["title"],
        subject=unit.get("subject", ""),
        grade_level=unit.get("grade_level", ""),
        department=department,
    )


def share_lesson(
    db: Database,
    school_id: str,
    teacher_id: str,
    lesson_id: str,
    department: str = "",
) -> str | None:
    """Share a lesson with the school (or a specific department).

    Returns the shared-content ID, or None if the lesson doesn't exist.
    """
    lesson = db.get_lesson(lesson_id)
    if not lesson:
        return None
    return db.share_content(
        school_id=school_id,
        teacher_id=teacher_id,
        content_type="lesson",
        content_id=lesson_id,
        title=lesson["title"],
        subject="",
        grade_level="",
        department=department,
    )


def get_shared_library(
    db: Database,
    school_id: str,
    department: str = "",
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Return shared content from the school's curriculum library.

    Results are sorted by rating (highest first), then by most-recently shared.
    Optionally filtered by department.
    """
    return db.get_shared_library(school_id, department=department, limit=limit)


def rate_shared(db: Database, shared_id: str, rating: int) -> None:
    """Rate a piece of shared content (1-5)."""
    db.rate_shared_content(shared_id, rating)
