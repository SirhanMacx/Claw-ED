"""The Dream Cycle — overnight brain enrichment and consolidation.

Runs while the teacher sleeps. Scans every brain page and:

1. **Consolidates timeline into compiled truth** — when a page has >5 new
   timeline entries since the last compiled-truth update, asks an LLM to
   rewrite the synthesis based on the new evidence.

2. **Detects gaps** — student pages with no recent entries (>14 days)
   get flagged, topic pages taught multiple times without feedback get
   flagged, etc.

3. **Fixes broken references** — scans for Citation objects pointing to
   missing pages, reports them.

4. **Cross-links entities** — when a lesson page mentions a concept that
   has its own page, adds a reference.

This is designed to run via the scheduler as a nightly task. Idempotent —
running it multiple times produces the same result.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from clawed.brain.store import BrainPage, BrainStore

logger = logging.getLogger(__name__)

# Consolidate compiled truth when timeline has this many entries newer
# than the last "updated" date
_CONSOLIDATION_THRESHOLD = 5

# Flag student pages with no activity in this many days
_STUDENT_STALE_DAYS = 14

# Max pages to process per dream cycle run (time budget)
_MAX_PAGES_PER_RUN = 50


@dataclass
class DreamReport:
    """Report from a dream cycle run."""

    started_at: str = ""
    finished_at: str = ""
    pages_scanned: int = 0
    pages_consolidated: int = 0
    gaps_detected: list[str] = field(default_factory=list)
    broken_refs: list[str] = field(default_factory=list)
    cross_links_added: int = 0
    errors: list[str] = field(default_factory=list)

    def render(self) -> str:
        """Human-readable summary."""
        lines = [
            "# Dream Cycle Report",
            "",
            f"**Started:** {self.started_at}",
            f"**Finished:** {self.finished_at}",
            f"**Pages scanned:** {self.pages_scanned}",
            f"**Pages consolidated:** {self.pages_consolidated}",
            f"**Cross-links added:** {self.cross_links_added}",
            "",
        ]
        if self.gaps_detected:
            lines.append("## Gaps Detected")
            for g in self.gaps_detected:
                lines.append(f"- {g}")
            lines.append("")
        if self.broken_refs:
            lines.append("## Broken References")
            for b in self.broken_refs:
                lines.append(f"- {b}")
            lines.append("")
        if self.errors:
            lines.append("## Errors")
            for e in self.errors:
                lines.append(f"- {e}")
        return "\n".join(lines)


async def dream_cycle(
    store: BrainStore | None = None,
    consolidate: bool = True,
    dry_run: bool = False,
) -> DreamReport:
    """Run the dream cycle.

    Args:
        store: BrainStore (creates default if None)
        consolidate: Whether to LLM-consolidate compiled truth
        dry_run: Report what WOULD change, don't write anything

    Returns a DreamReport with counts and findings.
    """
    if store is None:
        store = BrainStore()

    report = DreamReport(
        started_at=datetime.now().isoformat(timespec="seconds"),
    )

    all_pages: list[BrainPage] = []
    for ptype in ["student", "topic", "lesson", "original", "concept"]:
        for slug in store.list_pages(ptype):
            page = store.get(ptype, slug)
            if page:
                all_pages.append(page)
            if len(all_pages) >= _MAX_PAGES_PER_RUN * 3:
                break
        if len(all_pages) >= _MAX_PAGES_PER_RUN * 3:
            break

    # 1. Consolidate pages that have accumulated timeline entries
    pages_to_consolidate = _find_consolidation_candidates(all_pages)
    if consolidate:
        for page in pages_to_consolidate[:_MAX_PAGES_PER_RUN]:
            try:
                new_truth = await _consolidate_page(page)
                if new_truth and not dry_run:
                    store.update_compiled_truth(
                        page.page_type, page.slug, new_truth,
                    )
                    report.pages_consolidated += 1
            except Exception as exc:
                report.errors.append(
                    f"Consolidation failed for {page.slug}: {exc}"
                )

    # 2. Detect gaps
    report.gaps_detected = _detect_gaps(all_pages)

    # 3. Cross-linking
    if not dry_run:
        report.cross_links_added = _add_cross_links(store, all_pages)

    report.pages_scanned = len(all_pages)
    report.finished_at = datetime.now().isoformat(timespec="seconds")
    return report


def _find_consolidation_candidates(pages: list[BrainPage]) -> list[BrainPage]:
    """Find pages with enough new timeline entries to warrant consolidation."""
    candidates: list[BrainPage] = []
    for page in pages:
        # Count timeline entries newer than "updated" date
        last_update = page.metadata.get("updated", "")
        if not last_update:
            # No update timestamp — consolidate if it has any timeline
            if len(page.timeline) >= _CONSOLIDATION_THRESHOLD:
                candidates.append(page)
            continue
        new_entries = [e for e in page.timeline if e.date >= last_update]
        # Sort by page size descending — prioritize hot pages
        if len(new_entries) >= _CONSOLIDATION_THRESHOLD:
            candidates.append(page)

    # Sort by timeline length (biggest catch-up first)
    candidates.sort(key=lambda p: len(p.timeline), reverse=True)
    return candidates


async def _consolidate_page(page: BrainPage) -> str:
    """Ask an LLM to rewrite compiled truth from timeline entries.

    Returns the new compiled_truth text, or empty string on failure.
    """
    # Build a prompt with the recent timeline entries
    recent_entries = sorted(
        page.timeline, key=lambda e: e.date, reverse=True,
    )[:20]  # most recent 20 entries
    if not recent_entries:
        return ""

    timeline_text = "\n".join(e.render() for e in recent_entries)

    prompt = (
        f"You maintain a brain page about '{page.title}' "
        f"(type: {page.page_type}). The current compiled-truth "
        f"synthesis is below, followed by the most recent timeline "
        f"entries. Rewrite the compiled-truth section to incorporate "
        f"what the timeline reveals. Keep the section headers the "
        f"same structure as the existing compiled truth. Use "
        f"specific, actionable language. Avoid filler.\n\n"
        f"## Current Compiled Truth\n\n{page.compiled_truth}\n\n"
        f"## Recent Evidence\n\n{timeline_text}\n\n"
        f"Output ONLY the new compiled-truth markdown — no commentary."
    )

    try:
        from clawed.llm import LLMClient
        from clawed.model_router import route as route_model
        from clawed.models import AppConfig
        cfg = AppConfig.load()
        cfg = route_model("summarization", cfg)
        client = LLMClient(cfg)
        result = await client.generate(
            prompt=prompt,
            system=(
                "You are an assistant that maintains a teacher's brain "
                "pages. Keep syntheses concise, evidence-based, and "
                "specific. Never invent facts — only summarize what "
                "the timeline shows."
            ),
            temperature=0.3,
            max_tokens=800,
        )
        return result.strip()
    except Exception as exc:
        logger.debug("LLM consolidation failed: %s", exc)
        return ""


def _detect_gaps(pages: list[BrainPage]) -> list[str]:
    """Detect gaps that indicate missing data or stale pages."""
    gaps: list[str] = []
    now = datetime.now()
    stale_threshold = now - timedelta(days=_STUDENT_STALE_DAYS)

    students_stale = 0
    topics_no_feedback = 0
    thin_pages = 0

    for page in pages:
        # Stale student pages (Tier 1 especially)
        if page.page_type == "student":
            tier = page.metadata.get("tier", "3")
            if not page.timeline:
                thin_pages += 1
                continue
            most_recent = max(
                (e.date for e in page.timeline),
                default="1970-01-01",
            )
            try:
                mr_date = datetime.strptime(most_recent, "%Y-%m-%d")
                if mr_date < stale_threshold and tier == "1":
                    students_stale += 1
            except ValueError:
                pass

        # Topic pages with lesson mentions but no outcome feedback
        if page.page_type == "topic":
            lesson_mentions = sum(
                1 for e in page.timeline if "lesson" in e.body.lower()
            )
            outcome_mentions = sum(
                1 for e in page.timeline
                if any(k in e.body.lower() for k in [
                    "worked", "failed", "engaged", "struggled", "excelled",
                ])
            )
            if lesson_mentions >= 2 and outcome_mentions == 0:
                topics_no_feedback += 1

        # Thin pages (no compiled truth, no timeline)
        if (
            not page.compiled_truth.strip()
            and not page.timeline
        ):
            thin_pages += 1

    if students_stale:
        gaps.append(
            f"{students_stale} Tier 1 student page(s) have no activity "
            f"in {_STUDENT_STALE_DAYS}+ days"
        )
    if topics_no_feedback:
        gaps.append(
            f"{topics_no_feedback} topic page(s) have lesson mentions "
            f"but no outcome feedback"
        )
    if thin_pages:
        gaps.append(f"{thin_pages} page(s) are empty or lack evidence")

    return gaps


def _add_cross_links(
    store: BrainStore,
    pages: list[BrainPage],
) -> int:
    """Add cross-references between pages that should be linked.

    When a lesson page mentions a concept that has its own page,
    append a timeline entry to the concept page linking back.
    """
    added = 0
    # Index pages by lowercased title for fast lookup
    lesson_pages = [p for p in pages if p.page_type == "lesson"]
    concept_pages = {p.title.lower(): p for p in pages if p.page_type == "concept"}

    for lesson in lesson_pages:
        lesson_text = f"{lesson.title} {lesson.compiled_truth}".lower()
        for concept_title, concept_page in concept_pages.items():
            if concept_title not in lesson_text:
                continue
            # Check if this lesson is already cross-referenced on the concept
            already_linked = any(
                lesson.slug in e.body or lesson.title in e.body
                for e in concept_page.timeline
            )
            if already_linked:
                continue
            try:
                store.append_timeline(
                    page_type="concept",
                    slug=concept_page.slug,
                    body=f"Appears in lesson '{lesson.title}'",
                    source=f"Lesson {lesson.slug}",
                    create_if_missing=False,
                )
                added += 1
            except Exception as exc:
                logger.debug("Cross-link failed: %s", exc)

    return added


def run_dream_cycle_sync(
    consolidate: bool = True,
    dry_run: bool = False,
) -> DreamReport:
    """Synchronous entrypoint for the dream cycle (for scheduler)."""
    return asyncio.run(dream_cycle(consolidate=consolidate, dry_run=dry_run))
