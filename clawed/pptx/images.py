"""Image fetching and placement for PPTX slides.

Handles topic-based and content-based image fetching with timeouts,
plus placement helpers for background, sidebar, and accent positions.

Extracted from the monolithic export_pptx.py for maintainability.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from clawed.async_utils import run_async_safe

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


def try_fetch_images(
    topics: list[tuple[str, str]],
    subject: str,
) -> dict[str, Optional[Path]]:
    """Attempt to fetch images for multiple topics. Non-blocking, short timeout.

    Args:
        topics: List of (search_query, result_key) tuples.
        subject: Subject area for search context.

    Returns:
        Dict mapping key -> Path | None.
    """
    from clawed.slide_images import fetch_slide_image

    results: dict[str, Optional[Path]] = {}

    async def _fetch_all():
        for topic, key in topics:
            try:
                path = await asyncio.wait_for(
                    fetch_slide_image(topic, subject=subject),
                    timeout=5.0,
                )
                results[key] = path
            except Exception:
                results[key] = None

    try:
        run_async_safe(_fetch_all())
    except Exception as e:
        logger.debug("Image fetching failed: %s", e)

    return results


def try_fetch_content_images(
    items: list[tuple[str, str, str]],
    subject: str,
    max_images: int = 4,
) -> dict[str, Optional[Path]]:
    """Fetch images based on slide content text, not just the lesson title.

    Args:
        items: List of (content_text, fallback_topic, key) tuples.
        subject: Subject area for search context.
        max_images: Stop after this many successful fetches.

    Returns:
        Dict mapping key -> Path | None.
    """
    from clawed.slide_images import fetch_content_image, fetch_slide_image

    results: dict[str, Optional[Path]] = {}

    async def _fetch_all():
        found = 0
        for content_text, fallback_topic, key in items:
            if found >= max_images:
                results[key] = None
                continue
            try:
                if content_text:
                    path = await asyncio.wait_for(
                        fetch_content_image(
                            content_text,
                            subject=subject,
                            fallback_topic=fallback_topic,
                        ),
                        timeout=5.0,
                    )
                else:
                    path = await asyncio.wait_for(
                        fetch_slide_image(fallback_topic, subject=subject),
                        timeout=5.0,
                    )
                results[key] = path
                if path:
                    found += 1
            except Exception:
                results[key] = None

    try:
        run_async_safe(_fetch_all())
    except Exception as e:
        logger.debug("Content image fetching failed: %s", e)

    return results
