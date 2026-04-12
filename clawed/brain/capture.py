"""Originals capture — detect and save teacher's pedagogical insights.

When a teacher chats with Ed (via Telegram, CLI, or the web UI), some
messages contain original pedagogical thinking: observations about
their classroom, frameworks they've developed, insights about
student behavior, hot takes on curriculum.

These are the HIGHEST-VALUE content in the entire brain. They're the
teacher's unique intellectual contribution — not something any AI could
generate from scratch.

This module:
1. Detects whether a message contains original thinking
2. Captures the exact phrasing (NO paraphrasing — the language IS the insight)
3. Saves to `brain/originals/{slug}.md` with source attribution

Pattern inspired by gbrain's originals folder.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime

from clawed.brain.store import BrainPage, BrainStore

logger = logging.getLogger(__name__)


# Heuristic signals that a message contains original thinking
# (words/phrases teachers use when expressing an insight vs. issuing a command)
_INSIGHT_MARKERS = [
    r"\bi think\b",
    r"\bi believe\b",
    r"\bi've noticed\b",
    r"\bi find that\b",
    r"\bin my experience\b",
    r"\bthe key is\b",
    r"\bwhat works for me\b",
    r"\bmy theory\b",
    r"\bmy approach\b",
    r"\bthe real problem is\b",
    r"\bthe reason\b",
    r"\bwhat i actually do\b",
    r"\bover the years\b",
    r"\bstudents always\b",
    r"\bthe best way\b",
    r"\bthe worst thing\b",
    r"\bnever\b.*\bkids\b",
    r"\balways\b.*\bstudents\b",
    r"\bthe secret\b",
    r"\bthe trick\b",
]


# Phrases that indicate a routine operational message (NOT an insight)
_OPERATIONAL_MARKERS = [
    r"^(ok|okay|yes|no|sure|thanks|cool|nice|do it|go|stop|wait|please)\s*[\.\?\!]?$",
    r"^generate\b",
    r"^make\b",
    r"^create\b",
    r"^show\b",
    r"^send\b",
    r"^delete\b",
    r"^rerun\b",
    r"^run\b",
    r"^fix\b",
]


def looks_like_original_thinking(message: str) -> bool:
    """Heuristic: does this message contain pedagogical insight?

    Returns True if the message has insight markers and is NOT a routine
    operational command. Minimum length of 80 chars (to avoid false
    positives on tiny messages).
    """
    if len(message.strip()) < 80:
        return False

    msg_lower = message.lower().strip()

    # Reject pure operational messages
    for pattern in _OPERATIONAL_MARKERS:
        if re.match(pattern, msg_lower):
            return False

    # Accept if any insight marker fires
    return any(re.search(pattern, msg_lower) for pattern in _INSIGHT_MARKERS)


def extract_slug_from_message(message: str, max_len: int = 60) -> str:
    """Pull a short slug from the message for naming the originals file.

    Uses the first meaningful noun phrase or just the first words.
    """
    # Remove insight markers from the start
    clean = message.strip()
    for pattern in _INSIGHT_MARKERS:
        clean = re.sub(pattern, "", clean, count=1, flags=re.IGNORECASE).strip()

    # Take first sentence
    first_sentence = re.split(r"[.!?]", clean, maxsplit=1)[0].strip()

    # Slugify
    slug = first_sentence.lower()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"\s+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug[:max_len] or "untitled-insight"


def capture_original(
    message: str,
    context: str = "",
    source_channel: str = "chat",
    store: BrainStore | None = None,
    force: bool = False,
) -> BrainPage | None:
    """Capture an original pedagogical insight to the brain.

    Args:
        message: The teacher's exact message (will be preserved verbatim)
        context: Optional conversation context (what prompted this)
        source_channel: Where this came from (chat, telegram, cli, etc.)
        store: BrainStore (creates default if None)
        force: Skip the insight heuristic and always save

    Returns:
        The saved BrainPage, or None if the message wasn't an insight
        and force=False.
    """
    if store is None:
        store = BrainStore()

    if not force and not looks_like_original_thinking(message):
        return None

    slug = extract_slug_from_message(message)
    today = datetime.now().strftime("%Y-%m-%d")

    # Check if this exact insight already exists (avoid duplicates)
    existing = store.get("original", slug)
    if existing:
        # Append as new timeline entry instead of creating duplicate
        existing.add_timeline(
            body=f"Re-expressed: {message[:200]}",
            source=f"{source_channel} {today}",
            date=today,
        )
        store.save(existing)
        return existing

    # Create a new page — preserve EXACT phrasing in compiled_truth
    title = _extract_title(message)
    page = BrainPage(
        slug=slug,
        page_type="original",
        title=title,
        compiled_truth=(
            "## The Insight\n\n"
            f"> {message.strip()}\n\n"
            "## Context\n\n"
            f"{context if context else '_(captured in conversation)_'}"
        ),
        metadata={
            "tier": "1",  # Originals are always Tier 1 — highest value
            "source": source_channel,
            "created": today,
            "updated": today,
        },
    )
    page.add_timeline(
        body="Captured from conversation",
        source=f"{source_channel} {today}",
        date=today,
    )
    store.save(page)
    logger.info("Captured original insight: %s", slug)
    return page


def _extract_title(message: str, max_len: int = 80) -> str:
    """Pull a title from the message — first sentence, cleaned up."""
    clean = message.strip()
    # Remove insight markers from the start
    for pattern in _INSIGHT_MARKERS:
        clean = re.sub(pattern, "", clean, count=1, flags=re.IGNORECASE).strip()
    # Take first sentence or first line
    first = re.split(r"[.!?\n]", clean, maxsplit=1)[0].strip()
    # Capitalize first letter
    if first:
        first = first[0].upper() + first[1:]
    return first[:max_len] or "Untitled Insight"
