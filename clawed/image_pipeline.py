"""Parallel image fetching pipeline for MasterContent.

Collects all unique image_spec strings from a MasterContent object,
fetches them in parallel with timeout, and returns a mapping of
spec -> local Path.  Failures are logged but never block lesson generation.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from clawed.master_content import MasterContent
    from clawed.models import AppConfig

logger = logging.getLogger(__name__)

_CONCURRENT_LIMIT = 5

_VISION_QUALITY_PROMPT = (
    "You are an image quality filter for educational materials. "
    "A teacher is building a lesson and this image was fetched to illustrate "
    "the topic described below.\n\n"
    "Evaluate this image on three criteria:\n"
    "1. RELEVANT — Does it match the educational topic?\n"
    "2. CLEAR — Is it high resolution, not blurry, not mostly text/watermarks?\n"
    "3. APPROPRIATE — Is it suitable for a K-12 classroom?\n\n"
    "Respond with EXACTLY one word: GOOD, ACCEPTABLE, or REJECT.\n"
    "Then a brief reason (under 15 words).\n\n"
    "Examples:\n"
    "GOOD — Clear historical painting of the signing of the Declaration\n"
    "ACCEPTABLE — Low resolution but relevant diagram of photosynthesis\n"
    "REJECT — Stock photo with watermark, not educationally relevant\n"
    "REJECT — Blurry thumbnail, unreadable text\n\n"
    "Topic: {topic}\nSubject: {subject}"
)


async def check_image_quality(
    image_path: Path,
    spec: str,
    subject: str = "",
    config: "AppConfig | None" = None,
) -> bool:
    """Use a vision model to evaluate whether an image is good enough for a lesson.

    Returns True if the image passes (GOOD or ACCEPTABLE), False if REJECT.
    Always returns True if no vision-capable model is configured (permissive).
    """
    try:
        from clawed.llm import LLMClient
        from clawed.model_router import route as route_model

        cfg = config or AppConfig.load()
        cfg = route_model("image_quality", cfg)
        client = LLMClient(cfg)

        prompt = _VISION_QUALITY_PROMPT.format(topic=spec, subject=subject)
        result = await client.generate_with_image(
            prompt=prompt,
            image_path=image_path,
            temperature=0.1,
            max_tokens=50,
        )

        verdict = result.strip().split()[0].upper() if result.strip() else "GOOD"
        if verdict == "REJECT":
            logger.info("Image REJECTED by vision filter: %s — %s", spec[:60], result.strip())
            return False
        logger.debug("Image passed vision filter (%s): %s", verdict, spec[:60])
        return True
    except Exception as e:
        logger.debug("Vision quality check failed, permitting image: %s", e)
        return True  # Always permissive on failure


def _collect_image_specs(master: "MasterContent") -> dict[str, str]:
    """Collect image_spec strings with their content context.

    Returns {spec: context_text} — the context helps the image search
    find content-relevant images instead of generic skill-based ones.
    """
    specs: dict[str, str] = {}

    for entry in master.vocabulary:
        if entry.image_spec:
            specs[entry.image_spec] = f"{entry.term}: {entry.definition}"

    for ps in master.primary_sources:
        if ps.image_spec:
            specs[ps.image_spec] = getattr(ps, "title", "") or ps.image_spec

    for section in master.direct_instruction:
        if section.image_spec:
            content = getattr(section, "content", "") or getattr(section, "title", "")
            specs[section.image_spec] = content[:200] if content else section.image_spec

    for sq in master.exit_ticket:
        if sq.stimulus_image_spec:
            specs[sq.stimulus_image_spec] = getattr(sq, "question", "") or sq.stimulus_image_spec

    return specs


async def _fetch_one(
    spec: str, subject: str = "", context: str = "", timeout: int = 15,
) -> tuple[str, Path | None]:
    """Fetch a single image by spec. Returns (spec, path) or (spec, None).

    When context is provided, uses it to build a more content-specific
    search query instead of the generic topic-based one.
    """
    try:
        from clawed.slide_images import fetch_content_image, fetch_slide_image

        # Prefer content-aware search when context is available
        if context:
            try:
                path = await asyncio.wait_for(
                    fetch_content_image(context, subject=subject, fallback_topic=spec),
                    timeout=timeout,
                )
                if path and path.exists() and path.stat().st_size > 5000:
                    logger.info("Fetched content image for: %s", spec[:80])
                    return spec, path
            except Exception:
                pass  # Fall through to topic-based search

        path = await asyncio.wait_for(
            fetch_slide_image(spec, subject=subject),
            timeout=timeout,
        )
        if path and path.exists() and path.stat().st_size > 5000:
            logger.info("Fetched image for: %s", spec[:80])
            return spec, path
    except asyncio.TimeoutError:
        logger.warning("Image fetch timed out for: %s", spec[:80])
    except Exception as e:
        logger.debug("Image fetch failed for %s: %s", spec[:80], e)

    return spec, None


async def fetch_all_images(
    master: "MasterContent",
    config: "AppConfig | None" = None,
    teacher_id: str = "",
) -> dict[str, Path]:
    """Fetch all images referenced in a MasterContent in parallel.

    Priority: teacher's own extracted images first, then external sources.

    Args:
        master: The MasterContent object with image_spec fields.
        config: Optional config for timeout settings.
        teacher_id: Teacher ID for looking up their extracted images.

    Returns:
        A dict mapping image_spec strings to local file Paths.
        Only specs that were successfully fetched are included.
    """
    spec_map = _collect_image_specs(master)
    if not spec_map:
        return {}

    timeout = 15
    if config and hasattr(config, "image_fetch_timeout"):
        timeout = config.image_fetch_timeout

    subject = getattr(master, "subject", "")

    # Phase 1: Try teacher's own images first (instant, no network)
    images: dict[str, Path] = {}
    if teacher_id:
        images = _resolve_from_teacher_assets(spec_map, teacher_id)
        if images:
            logger.info(
                "Found %d/%d images from teacher's own materials",
                len(images), len(spec_map),
            )

    # Remove already-resolved specs from the fetch list
    remaining = {s: c for s, c in spec_map.items() if s not in images}

    # Phase 2: Fetch remaining images from external sources
    if remaining:
        logger.info(
            "Fetching %d images from external sources (timeout=%ds, subject=%s)",
            len(remaining), timeout, subject,
        )

        semaphore = asyncio.Semaphore(_CONCURRENT_LIMIT)

        async def _limited_fetch(spec: str, context: str) -> tuple[str, Path | None]:
            async with semaphore:
                return await _fetch_one(spec, subject=subject, context=context, timeout=timeout)

        tasks = [_limited_fetch(spec, ctx) for spec, ctx in remaining.items()]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                logger.debug("Image fetch raised: %s", result)
                continue
            spec, path = result
            if path is not None:
                images[spec] = path

    # Phase 3: Vision-model quality filter (reject bad images)
    if images:
        rejected: list[str] = []
        for spec, path in list(images.items()):
            passed = await check_image_quality(
                image_path=path,
                spec=spec,
                subject=subject,
                config=config,
            )
            if not passed:
                rejected.append(spec)
                del images[spec]

        if rejected:
            logger.info(
                "Vision filter rejected %d/%d images: %s",
                len(rejected),
                len(rejected) + len(images),
                ", ".join(s[:40] for s in rejected),
            )

    logger.info(
        "Image pipeline: %d/%d resolved (%d from teacher, %d from web)",
        len(images), len(spec_map),
        len(spec_map) - len(remaining), len(images) - (len(spec_map) - len(remaining)),
    )
    return images


def _resolve_from_teacher_assets(
    spec_map: dict[str, str],
    teacher_id: str,
) -> dict[str, Path]:
    """Try to resolve image specs from teacher's own extracted images.

    Instant — no network calls, just SQLite lookups.
    Tracks already-used paths to prevent the same image appearing
    on multiple slides.
    """
    try:
        from clawed.asset_registry import AssetRegistry
        registry = AssetRegistry()
    except Exception:
        return {}

    resolved: dict[str, Path] = {}
    used_paths: set[str] = set()  # Prevent same image on multiple slides

    for spec, context in spec_map.items():
        # Search using both the spec and context for better matching
        query = f"{spec} {context[:100]}"
        # Request extra candidates so we can skip already-used ones
        matches = registry.search_images_for_topic(teacher_id, query, limit=10)
        for match in matches:
            path = Path(match["path"])
            path_str = str(path)
            if path.exists() and path_str not in used_paths:
                resolved[spec] = path
                used_paths.add(path_str)
                logger.debug(
                    "Teacher image found for '%s': %s (score: %.1f)",
                    spec[:50], path.name, match.get("score", 0),
                )
                break  # Use first unused match

    return resolved
