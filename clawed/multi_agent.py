"""Multi-agent orchestrator for lesson generation.

Three agents collaborate in sequence:
  1. RESEARCHER — finds primary sources, historical context, key facts
  2. WRITER — drafts MasterContent in the teacher's voice using persona
  3. REVIEWER — scores quality, sends back for revision if needed (max 1 retry)

Falls back gracefully: if multi-agent fails at any step, logs a warning
and returns None so the caller can fall back to single-agent generation.
"""

from __future__ import annotations

import logging
from pathlib import Path

from pydantic import BaseModel, Field

from clawed.lesson import _build_system_prompt
from clawed.llm import LLMClient
from clawed.master_content import MasterContent
from clawed.model_router import route as route_model
from clawed.models import AppConfig, TeacherPersona

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_PROMPTS_DIR = Path(__file__).parent / "prompts"
MASTER_PROMPT_PATH = _PROMPTS_DIR / "master_content.txt"
RESEARCHER_PROMPT_PATH = _PROMPTS_DIR / "multi_agent_researcher.txt"
REVIEWER_PROMPT_PATH = _PROMPTS_DIR / "multi_agent_reviewer.txt"

# Generous output budgets. Reasoning models (e.g. minimax-m3) spend a large,
# variable share of their token budget on hidden reasoning *before* emitting
# output, so a tight cap silently truncates the lesson JSON — the writer was
# previously capped at 6000 and its trailing sections (guided_notes /
# exit_ticket / differentiation) were getting cut off, failing validation and
# the whole lesson. Per product directive there are no artificial token caps:
# teachers may have large projects needing lots of tokens and full reasoning.
# Mirrors clawed/phases/pipeline.py:_PHASE_MAX_TOKENS.
_WRITER_MAX_TOKENS = 32000
_RESEARCHER_MAX_TOKENS = 16000
_REVIEWER_MAX_TOKENS = 8000

# ---------------------------------------------------------------------------
# Review result schema
# ---------------------------------------------------------------------------

class ReviewResult(BaseModel):
    """Structured output from the REVIEWER agent."""

    voice_score: int = Field(..., ge=1, le=10)
    pedagogy_score: int = Field(..., ge=1, le=10)
    differentiation_score: int = Field(..., ge=1, le=10)
    passed: bool
    revision_notes: str = ""


# ---------------------------------------------------------------------------
# Helper — load a prompt file
# ---------------------------------------------------------------------------

def _load_prompt(path: Path) -> str:
    """Read a prompt template from disk. Returns empty string on failure."""
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.error("Prompt file not found: %s", path)
        return ""


# ---------------------------------------------------------------------------
# Agent 1: RESEARCHER
# ---------------------------------------------------------------------------

async def _run_researcher(
    topic: str,
    grade: str,
    subject: str,
    unit_context: str,
    client: LLMClient,
) -> str | None:
    """Run the research agent and return a research brief (plain text)."""
    system_prompt = _load_prompt(RESEARCHER_PROMPT_PATH)
    if not system_prompt:
        logger.warning("Researcher system prompt missing — skipping research step")
        return None

    user_prompt = (
        f"Topic: {topic}\n"
        f"Grade Level: {grade}\n"
        f"Subject: {subject}\n"
    )
    if unit_context:
        user_prompt += f"\nUnit Context:\n{unit_context}\n"

    user_prompt += (
        "\nProvide a structured research brief (~500-800 words) that the "
        "lesson writer can use to craft an accurate, source-rich lesson."
    )

    try:
        brief = await client.generate(
            prompt=user_prompt,
            system=system_prompt,
            temperature=0.7,
            max_tokens=_RESEARCHER_MAX_TOKENS,
        )
        logger.info("Researcher produced %d-char brief", len(brief))
        return brief
    except Exception:
        logger.warning("Researcher agent failed", exc_info=True)
        return None


# ---------------------------------------------------------------------------
# Agent 2: WRITER
# ---------------------------------------------------------------------------

async def _run_writer(
    topic: str,
    grade: str,
    subject: str,
    persona: TeacherPersona,
    config: AppConfig,
    research_brief: str,
    revision_notes: str = "",
    client: LLMClient | None = None,
) -> MasterContent | None:
    """Run the writer agent and return structured MasterContent."""
    system_prompt = _build_system_prompt(persona, config)
    master_template = _load_prompt(MASTER_PROMPT_PATH)
    if not master_template:
        logger.warning("Master content template missing — cannot write")
        return None

    # Build the user prompt with research context prepended
    parts: list[str] = []
    if research_brief:
        parts.append(
            "## Research Brief (from Research Agent)\n\n"
            f"{research_brief}\n\n---\n"
        )
    if revision_notes:
        parts.append(
            "## Revision Notes (from Reviewer)\n\n"
            f"{revision_notes}\n\n"
            "Please address the above revision notes while regenerating.\n\n---\n"
        )
    parts.append(
        f"Topic: {topic}\nGrade Level: {grade}\nSubject: {subject}\n\n"
        f"{master_template}"
    )
    user_prompt = "\n".join(parts)

    if client is None:
        # Defensive: the default is None but callers always pass a client.
        logger.warning("Writer agent: no LLM client available")
        return None

    try:
        result = await client.safe_generate_json(
            prompt=user_prompt,
            model_class=MasterContent,
            system=system_prompt,
            temperature=0.5,
            max_tokens=_WRITER_MAX_TOKENS,
        )
        logger.info("Writer produced MasterContent for '%s'", topic)
        return result
    except Exception:
        logger.warning("Writer agent failed", exc_info=True)
        return None


# ---------------------------------------------------------------------------
# Agent 3: REVIEWER
# ---------------------------------------------------------------------------

async def _run_reviewer(
    master_content: MasterContent,
    persona: TeacherPersona,
    client: LLMClient,
) -> ReviewResult | None:
    """Score the MasterContent and decide whether it passes."""
    system_prompt = _load_prompt(REVIEWER_PROMPT_PATH)
    if not system_prompt:
        logger.warning("Reviewer system prompt missing — skipping review")
        return None

    persona_context = persona.to_prompt_context()
    content_json = master_content.model_dump_json(indent=2)

    user_prompt = (
        "## Teacher Persona\n\n"
        f"{persona_context}\n\n"
        "## MasterContent to Review\n\n"
        f"```json\n{content_json}\n```\n\n"
        "Score this lesson and return your review as valid JSON."
    )

    try:
        review = await client.safe_generate_json(
            prompt=user_prompt,
            model_class=ReviewResult,
            system=system_prompt,
            temperature=0.3,
            max_tokens=_REVIEWER_MAX_TOKENS,
        )
        logger.info(
            "Reviewer scores — voice: %d, pedagogy: %d, diff: %d, passed: %s",
            review.voice_score,
            review.pedagogy_score,
            review.differentiation_score,
            review.passed,
        )
        return review
    except Exception:
        logger.warning("Reviewer agent failed", exc_info=True)
        return None


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

async def multi_agent_generate_master_content(
    topic: str,
    grade: str,
    subject: str,
    persona: TeacherPersona,
    config: AppConfig,
    unit_context: str = "",
) -> MasterContent | None:
    """Run the full RESEARCHER -> WRITER -> REVIEWER pipeline.

    Returns a validated MasterContent on success, or None if the pipeline
    fails at any step (so the caller can fall back to single-agent).
    """
    routed_config = route_model("multi_agent", config)
    client = LLMClient(config=routed_config)

    # --- Step 1: Research ---------------------------------------------------
    logger.info("Multi-agent pipeline: starting RESEARCHER for '%s'", topic)
    research_brief = await _run_researcher(
        topic=topic,
        grade=grade,
        subject=subject,
        unit_context=unit_context,
        client=client,
    )
    # Research is optional — writer can proceed without it
    if research_brief is None:
        logger.warning("Proceeding without research brief")
        research_brief = ""

    # --- Step 2: Write ------------------------------------------------------
    logger.info("Multi-agent pipeline: starting WRITER for '%s'", topic)
    master_content = await _run_writer(
        topic=topic,
        grade=grade,
        subject=subject,
        persona=persona,
        config=config,
        research_brief=research_brief,
        client=client,
    )
    if master_content is None:
        logger.warning("Multi-agent pipeline: WRITER failed — returning None")
        return None

    # --- Step 3: Review -----------------------------------------------------
    logger.info("Multi-agent pipeline: starting REVIEWER for '%s'", topic)
    review = await _run_reviewer(master_content, persona, client)
    if review is None:
        # If reviewer fails, return what we have — better than nothing
        logger.warning("Reviewer unavailable — returning unreviewed content")
        return master_content

    if review.passed:
        logger.info("Multi-agent pipeline: PASSED review on first attempt")
        return master_content

    # --- Step 3b: One revision if review failed -----------------------------
    logger.info(
        "Multi-agent pipeline: review FAILED — attempting one revision. "
        "Notes: %s",
        review.revision_notes,
    )
    revised_content = await _run_writer(
        topic=topic,
        grade=grade,
        subject=subject,
        persona=persona,
        config=config,
        research_brief=research_brief,
        revision_notes=review.revision_notes,
        client=client,
    )
    if revised_content is None:
        logger.warning("Revision attempt failed — returning original content")
        return master_content

    # Re-review the revised content
    second_review = await _run_reviewer(revised_content, persona, client)
    if second_review is not None and second_review.passed:
        logger.info("Multi-agent pipeline: PASSED review after revision")
        return revised_content

    # Even if second review fails, return the revised content — it is likely
    # an improvement over the original
    logger.warning(
        "Multi-agent pipeline: still did not pass after revision — "
        "returning revised content anyway"
    )
    return revised_content
