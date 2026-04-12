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

from clawed.models import AppConfig  # runtime import — needed for AppConfig.load()

if TYPE_CHECKING:
    from clawed.master_content import MasterContent

logger = logging.getLogger(__name__)

_CONCURRENT_LIMIT = 5

_VISION_QUALITY_PROMPT = (
    "You are an image quality filter for a K-12 lesson plan. "
    "This image was fetched to illustrate the educational topic below. "
    "Look carefully at the actual visual content.\n\n"
    "Evaluate on three criteria:\n"
    "1. RELEVANT — Does the ACTUAL VISUAL CONTENT match the topic? "
    "(Don't just judge by filename or caption — look at what's in the image.)\n"
    "2. CLEAR — Is it high resolution, not blurry, not mostly text/watermarks?\n"
    "3. APPROPRIATE — Is it suitable for a K-12 classroom?\n\n"
    "Respond with EXACTLY one word on the first line: GOOD, ACCEPTABLE, or REJECT.\n"
    "Then a brief reason (under 20 words).\n\n"
    "Be STRICT. If the image does not visually show the exact thing the topic "
    "describes, REJECT. Reject random slide templates, agenda slides, "
    "unrelated stock photos, or images of text.\n\n"
    "Examples:\n"
    "GOOD — Historical painting clearly showing the Declaration being signed\n"
    "ACCEPTABLE — Low-res photograph of Frederick Douglass, subject clearly visible\n"
    "REJECT — Classroom agenda slide with date, not the topic\n"
    "REJECT — Generic background of a flag, no specific historical content\n"
    "REJECT — Blurry thumbnail, unreadable, looks like a watermark\n\n"
    "Topic: {topic}\nSubject: {subject}"
)


async def check_image_quality(
    image_path: Path,
    spec: str,
    subject: str = "",
    config: AppConfig | None = None,
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


def _collect_image_specs(master: MasterContent) -> dict[str, str]:
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
    master: MasterContent,
    config: AppConfig | None = None,
    teacher_id: str = "",
) -> dict[str, Path]:
    """Fetch all images referenced in a MasterContent in parallel.

    Priority: teacher's own extracted images first, then external sources.

    Args:
        master: The MasterContent object with image_spec fields.
        config: Optional config for timeout settings.
        teacher_id: Teacher ID for looking up their extracted images.
            If empty, auto-detected via clawed.agent_core.identity.get_teacher_id()
            and falls back to "default" (which matches ingestion).

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

    # Auto-detect teacher_id if not provided
    if not teacher_id:
        try:
            from clawed.agent_core.identity import get_teacher_id
            teacher_id = get_teacher_id()
        except Exception:
            teacher_id = "default"

    # Phase 1: Try teacher's own images first with VISION re-ranking.
    # Get top 5 candidates for each spec (by text similarity), then let
    # the VLM pick the best-matching one visually. This prevents wrong
    # images from being selected based on tangential metadata.
    images: dict[str, Path] = {}
    used_paths: set[str] = set()
    for spec, context in spec_map.items():
        # Try configured teacher_id first, fall back to "default"
        candidates = _get_teacher_asset_candidates(
            spec, context, teacher_id, limit=5,
        )
        if not candidates and teacher_id != "default":
            candidates = _get_teacher_asset_candidates(
                spec, context, "default", limit=5,
            )
        # De-dupe already-used paths
        candidates = [c for c in candidates if str(c) not in used_paths]
        if not candidates:
            continue

        # Vision rerank: pick the best visual match
        best = await _vision_rerank_candidates(
            candidates=candidates,
            spec=spec,
            subject=subject,
            config=config,
        )
        if best is not None:
            images[spec] = best
            used_paths.add(str(best))
            logger.info(
                "VLM picked teacher image for '%s': %s",
                spec[:50], best.name,
            )
    if images:
        logger.info(
            "Vision-validated %d/%d images from teacher's materials",
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

    Returns candidate matches for each spec based on text-based search
    against image metadata. Caller should validate with vision model.

    Tracks already-used paths to prevent the same image appearing
    on multiple slides.
    """
    try:
        from clawed.asset_registry import AssetRegistry
        registry = AssetRegistry()
    except Exception:
        return {}

    resolved: dict[str, Path] = {}
    used_paths: set[str] = set()

    for spec, context in spec_map.items():
        query = f"{spec} {context[:100]}"
        matches = registry.search_images_for_topic(teacher_id, query, limit=10)
        for match in matches:
            path = Path(match["path"])
            path_str = str(path)
            if path.exists() and path_str not in used_paths:
                resolved[spec] = path
                used_paths.add(path_str)
                break

    return resolved


def _get_teacher_asset_candidates(
    spec: str,
    context: str,
    teacher_id: str,
    limit: int = 5,
) -> list[Path]:
    """Return up to `limit` candidate images for a spec, ordered by text match.

    Used for vision-model re-ranking — we get the top N text matches and
    then let the VLM pick the best visually-matching one.
    """
    try:
        from clawed.asset_registry import AssetRegistry
        registry = AssetRegistry()
    except Exception:
        return []

    query = f"{spec} {context[:100]}"
    matches = registry.search_images_for_topic(teacher_id, query, limit=limit)
    candidates: list[Path] = []
    for m in matches:
        p = Path(m["path"])
        if p.exists() and p.stat().st_size > 5000:
            candidates.append(p)
    return candidates


async def _vision_rerank_candidates(
    candidates: list[Path],
    spec: str,
    subject: str = "",
    config: AppConfig | None = None,
) -> Path | None:
    """Ask the VLM to score each candidate against the spec, return the best.

    Uses the same vision model as check_image_quality. Returns the first
    candidate that gets GOOD, or ACCEPTABLE if no GOOD exists, or None
    if all REJECT.
    """
    if not candidates:
        return None

    acceptable: Path | None = None
    for path in candidates:
        try:
            from clawed.llm import LLMClient
            from clawed.model_router import route as route_model

            cfg = config or AppConfig.load()
            cfg = route_model("image_quality", cfg)
            client = LLMClient(cfg)

            prompt = _VISION_QUALITY_PROMPT.format(topic=spec, subject=subject)
            result = await client.generate_with_image(
                prompt=prompt,
                image_path=path,
                temperature=0.1,
                max_tokens=80,
            )
            verdict = result.strip().split()[0].upper() if result.strip() else "GOOD"
            logger.debug(
                "Vision rerank %s -> %s (%s)",
                path.name, verdict, result.strip()[:80],
            )
            if verdict == "GOOD":
                return path
            if verdict == "ACCEPTABLE" and acceptable is None:
                acceptable = path
        except Exception as e:
            logger.debug("Vision rerank failed for %s: %s", path.name, e)
            continue

    return acceptable
