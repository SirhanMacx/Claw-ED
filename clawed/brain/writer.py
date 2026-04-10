"""Post-generation brain writes — capture learnings from each lesson.

After a lesson is generated, this module writes pages to the brain so
future lessons can learn from it:

- **Lesson page** (`brain/lessons/{date}-{slug}.md`): what was generated,
  what primary sources were used, what the creative activity was. Timeline
  entries track future feedback about this lesson.

- **Topic page update** (`brain/topics/{slug}.md`): append timeline entry
  noting this lesson, optionally refresh compiled truth if the topic page
  is stale.

- **Concept pages**: any new vocabulary terms become concept pages so
  they're searchable across units.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from clawed.brain.store import BrainPage, BrainStore

if TYPE_CHECKING:
    from clawed.master_content import MasterContent

logger = logging.getLogger(__name__)


def write_lesson_to_brain(
    master: "MasterContent",
    unit_title: str,
    lesson_number: int,
    store: Optional[BrainStore] = None,
) -> dict:
    """Write a lesson record to the brain after generation.

    Creates/updates:
    - `brain/lessons/{date}-{slug}.md` — full lesson record
    - `brain/topics/{slug}.md` — timeline entry
    - `brain/concepts/{slug}.md` — one per vocabulary term (lightweight)

    Returns a dict summarizing what was written.
    """
    if store is None:
        store = BrainStore()

    today = datetime.now().strftime("%Y-%m-%d")
    written: dict[str, list[str]] = {
        "lessons": [],
        "topics": [],
        "concepts": [],
    }

    # 1. Lesson page
    lesson_slug = f"{today}-{store.slugify(master.title)}"
    lesson_page = BrainPage(
        slug=lesson_slug,
        page_type="lesson",
        title=master.title,
        compiled_truth=_build_lesson_compiled_truth(master, unit_title, lesson_number),
        metadata={
            "tier": "2",
            "subject": master.subject,
            "grade_level": master.grade_level,
            "topic": master.topic,
            "unit": unit_title,
            "lesson_number": str(lesson_number),
            "lesson_format": master.lesson_format,
            "created": today,
            "updated": today,
        },
    )
    # Seed timeline with generation event
    source_count = len(master.primary_sources)
    notes_count = len(master.guided_notes)
    lesson_page.add_timeline(
        f"Generated: {source_count} primary sources, "
        f"{notes_count} guided notes, format={master.lesson_format}",
        source="Ed auto-generation",
        date=today,
    )
    store.save(lesson_page)
    written["lessons"].append(lesson_slug)

    # 2. Topic page — append timeline entry, create if missing
    topic_slug = store.slugify(master.topic)
    if not topic_slug:
        topic_slug = store.slugify(master.title)
    try:
        topic_body = (
            f"Generated lesson '{master.title}' for {master.grade_level} "
            f"{master.subject}"
        )
        store.append_timeline(
            page_type="topic",
            slug=topic_slug,
            body=topic_body,
            source=f"Lesson {lesson_slug}",
            date=today,
            title=master.topic,
        )
        written["topics"].append(topic_slug)
    except Exception as exc:
        logger.debug("Topic page write failed: %s", exc)

    # 3. Concept pages — one per vocabulary term (lightweight)
    for vocab in master.vocabulary[:10]:  # cap at 10 per lesson
        try:
            concept_slug = store.slugify(vocab.term)
            if not concept_slug:
                continue
            # Only create if missing; don't overwrite rich concept pages
            if not store.exists("concept", concept_slug):
                page = BrainPage(
                    slug=concept_slug,
                    page_type="concept",
                    title=vocab.term,
                    compiled_truth=(
                        f"## Definition\n\n{vocab.definition}\n\n"
                        f"## In Context\n\n{vocab.context_sentence}"
                    ),
                    metadata={
                        "tier": "3",
                        "first_seen_in": lesson_slug,
                        "subject": master.subject,
                        "created": today,
                        "updated": today,
                    },
                )
                store.save(page)
            # Always append a timeline entry so we know when this concept
            # appeared in a lesson
            store.append_timeline(
                page_type="concept",
                slug=concept_slug,
                body=f"Taught in lesson '{master.title}'",
                source=f"Lesson {lesson_slug}",
                date=today,
            )
            written["concepts"].append(concept_slug)
        except Exception as exc:
            logger.debug("Concept page write failed for %s: %s", vocab.term, exc)

    return written


def _build_lesson_compiled_truth(
    master: "MasterContent",
    unit_title: str,
    lesson_number: int,
) -> str:
    """Render the compiled-truth zone for a lesson page."""
    lines = ["## Summary", ""]
    lines.append(f"**Unit:** {unit_title}")
    lines.append(f"**Lesson:** {lesson_number}")
    lines.append(f"**Format:** {master.lesson_format}")
    lines.append(f"**Duration:** {master.duration_minutes} min")
    lines.append("")
    lines.append(f"**Objective:** {master.objective}")
    lines.append("")

    if master.lesson_personality:
        lines.append("## Hook")
        lines.append(master.lesson_personality)
        lines.append("")

    if master.primary_sources:
        lines.append("## Primary Sources Used")
        for ps in master.primary_sources:
            lines.append(f"- **{ps.title}** — {ps.attribution}")
        lines.append("")

    if master.creative_activity:
        lines.append("## Creative Activity")
        lines.append(f"**{master.creative_activity.title}** ({master.creative_activity.activity_type})")
        lines.append("")

    if master.standards:
        lines.append("## Standards")
        for s in master.standards:
            lines.append(f"- {s}")
        lines.append("")

    if master.misconceptions:
        lines.append("## Watch For")
        for m in master.misconceptions:
            lines.append(f"- {m}")
        lines.append("")

    return "\n".join(lines)
