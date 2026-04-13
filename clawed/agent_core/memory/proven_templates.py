"""Proven Templates — template compounding for Ed's lesson generation.

When a teacher rates a lesson highly (4-5 stars), the generation prompt
and lesson structure are saved as a "proven template" that Ed references
for future generations of similar topics.

Competitive borrowing from Claw-STU's template compounding pattern,
adapted for the teacher-facing agent.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_TEMPLATES_DIR_NAME = "templates"


def _templates_dir() -> Path:
    """Resolve the templates directory, respecting EDUAGENT_DATA_DIR."""
    base = Path(os.environ.get("EDUAGENT_DATA_DIR", str(Path.home() / ".eduagent")))
    return base / _TEMPLATES_DIR_NAME


def save_proven_template(
    *,
    teacher_id: str,
    topic: str,
    grade_level: str,
    subject: str,
    rating: int,
    generation_prompt: str,
    lesson_structure: dict[str, Any],
) -> Path | None:
    """Save a highly-rated lesson as a proven template.

    Called when a teacher rates a lesson 4-5 stars. The prompt and
    structure are persisted so Ed can reference them for future
    generations of similar topics.

    Args:
        teacher_id: The teacher who rated this lesson.
        topic: Lesson topic (e.g., "French Revolution").
        grade_level: Grade level (e.g., "8").
        subject: Subject area (e.g., "History").
        rating: Teacher's rating (should be 4-5).
        generation_prompt: The prompt that produced this lesson.
        lesson_structure: Dict describing the lesson structure —
            section types, activity types, timing, etc.

    Returns:
        Path to the saved template file, or None if save failed.
    """
    if rating < 4:
        return None

    templates_dir = _templates_dir()
    templates_dir.mkdir(parents=True, exist_ok=True)

    template = {
        "teacher_id": teacher_id,
        "topic": topic,
        "grade_level": grade_level,
        "subject": subject,
        "rating": rating,
        "generation_prompt": generation_prompt,
        "lesson_structure": lesson_structure,
        "saved_at": datetime.now(UTC).isoformat(),
    }

    # Filename: teacher_subject_topic_timestamp.json
    safe_topic = "".join(c if c.isalnum() or c in "-_ " else "" for c in topic)
    safe_topic = safe_topic.strip().replace(" ", "_")[:40]
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    filename = f"{teacher_id}_{subject}_{safe_topic}_{timestamp}.json"

    filepath = templates_dir / filename
    try:
        filepath.write_text(json.dumps(template, indent=2), encoding="utf-8")
        logger.info("Saved proven template: %s (rating=%d)", filepath.name, rating)
        return filepath
    except OSError as exc:
        logger.warning("Failed to save proven template: %s", exc)
        return None


def get_proven_templates(
    *,
    teacher_id: str | None = None,
    subject: str | None = None,
    grade_level: str | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Retrieve proven templates, optionally filtered by teacher/subject/grade.

    Returns templates sorted by rating (descending), then by recency.
    """
    templates_dir = _templates_dir()
    if not templates_dir.exists():
        return []

    results: list[dict[str, Any]] = []
    for filepath in templates_dir.glob("*.json"):
        try:
            data = json.loads(filepath.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        # Apply filters
        if teacher_id and data.get("teacher_id") != teacher_id:
            continue
        if subject and data.get("subject", "").lower() != subject.lower():
            continue
        if grade_level and data.get("grade_level") != grade_level:
            continue

        results.append(data)

    # Sort by rating desc, then by saved_at desc
    results.sort(
        key=lambda t: (t.get("rating", 0), t.get("saved_at", "")),
        reverse=True,
    )
    return results[:limit]


def format_templates_for_prompt(
    templates: list[dict[str, Any]],
    max_templates: int = 3,
) -> str:
    """Format proven templates into a prompt-injectable string.

    Returns a compact summary Ed can reference when generating new
    lessons for similar topics.
    """
    if not templates:
        return ""

    lines = ["## Proven Templates (from highly-rated lessons)"]
    for tmpl in templates[:max_templates]:
        topic = tmpl.get("topic", "Unknown")
        grade = tmpl.get("grade_level", "?")
        rating = tmpl.get("rating", 0)
        structure = tmpl.get("lesson_structure", {})

        sections = structure.get("sections", [])
        activities = structure.get("activity_types", [])

        line = f"- {topic} (grade {grade}, {rating}-star)"
        if sections:
            line += f" | Sections: {', '.join(sections[:5])}"
        if activities:
            line += f" | Activities: {', '.join(activities[:5])}"
        lines.append(line)

    lines.append(
        "\nUse these proven structures as starting points for similar "
        "topics and grade levels. Adapt, don't copy blindly."
    )
    return "\n".join(lines)
