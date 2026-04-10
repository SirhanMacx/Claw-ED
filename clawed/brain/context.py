"""Build BrainContext for lesson generation — the brain-first lookup.

Before generating a lesson, the brain is consulted for:
- Topic teaching history (what worked before, misconceptions observed)
- Student pages with relevant needs (tier 1/2 students' accommodations)
- Teacher's original pedagogical insights relevant to the topic
- Past lesson outcomes on the same topic

The resulting BrainContext is rendered into the prompt so the LLM has
full teacher memory before generating.
"""
from __future__ import annotations

import logging
from typing import Optional

from clawed.brain.search import hybrid_search
from clawed.brain.store import BrainStore
from clawed.master_content import BrainContext, Citation

logger = logging.getLogger(__name__)

_MAX_STUDENTS_PER_LESSON = 5
_MAX_ORIGINALS_PER_LESSON = 3
_MAX_PAST_LESSONS = 3


def build_brain_context(
    topic: str,
    unit_title: str = "",
    store: Optional[BrainStore] = None,
) -> BrainContext:
    """Consult the brain for everything relevant to this lesson.

    Returns a BrainContext populated with topic history, student needs,
    originals, and citations pointing to every source consulted.
    """
    if store is None:
        store = BrainStore()

    context = BrainContext()

    # 1. Topic history — direct lookup + search
    topic_slug = store.slugify(topic)
    topic_page = store.get("topic", topic_slug)
    if topic_page is None and unit_title:
        # Try unit-title as fallback
        topic_page = store.get("topic", store.slugify(unit_title))

    if topic_page:
        context.topic_history = topic_page.compiled_truth
        context.citations.append(
            Citation(
                source_type="brain-topic",
                reference=topic_page.slug,
                date=topic_page.metadata.get("updated", ""),
            )
        )

    # 2. Related originals (Jon's pedagogical insights)
    try:
        original_results = hybrid_search(
            topic,
            store=store,
            page_type="original",
            limit=_MAX_ORIGINALS_PER_LESSON,
            include_corpus=False,
        )
        for r in original_results:
            if r.page and r.page.compiled_truth:
                # Take just the first paragraph of compiled truth
                snippet = r.page.compiled_truth.strip().split("\n\n")[0][:400]
                context.related_originals.append(
                    f"{r.page.title}: {snippet}"
                )
                context.citations.append(
                    Citation(
                        source_type="brain-original",
                        reference=r.slug,
                    )
                )
    except Exception as exc:
        logger.debug("Originals lookup failed: %s", exc)

    # 3. Past lesson results on this topic
    try:
        lesson_results = hybrid_search(
            topic,
            store=store,
            page_type="lesson",
            limit=_MAX_PAST_LESSONS,
            include_corpus=False,
        )
        for r in lesson_results:
            if r.page:
                # Grab any "what worked" or outcome note
                compiled = r.page.compiled_truth.strip().split("\n\n")[0][:300]
                if compiled:
                    context.past_lesson_results.append(
                        f"{r.page.title}: {compiled}"
                    )
                    context.citations.append(
                        Citation(
                            source_type="brain-lesson",
                            reference=r.slug,
                            date=r.page.metadata.get("updated", ""),
                        )
                    )
    except Exception as exc:
        logger.debug("Past lesson lookup failed: %s", exc)

    # 4. Students with specific needs for this topic
    # Load Tier 1 students (IEP, struggling readers) — they get context on
    # every lesson, not just topic-specific ones
    try:
        all_student_slugs = store.list_pages("student")
        for slug in all_student_slugs[:_MAX_STUDENTS_PER_LESSON * 2]:
            page = store.get("student", slug)
            if not page:
                continue
            tier = page.metadata.get("tier", "3")
            if tier == "1":
                # Always include Tier 1 students with their current truth
                summary = (
                    f"{page.title}: {page.compiled_truth[:200].strip()}"
                )
                context.relevant_students.append(summary)
                context.citations.append(
                    Citation(
                        source_type="brain-student",
                        reference=slug,
                        date=page.metadata.get("updated", ""),
                    )
                )
                if len(context.relevant_students) >= _MAX_STUDENTS_PER_LESSON:
                    break
    except Exception as exc:
        logger.debug("Student lookup failed: %s", exc)

    return context
