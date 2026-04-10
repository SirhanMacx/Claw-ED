"""4-phase pipeline orchestrator for MasterContent generation.

Sequentially runs Phase 1 → Phase 4, piping context forward. Each phase
has 2 retries on its own before the whole pipeline falls back to the
legacy single-call generation.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from clawed.master_content import MasterContent
from clawed.phases.models import (
    Phase1Skeleton,
    Phase2Instruction,
    Phase3Activities,
    Phase4Assessment,
)
from clawed.standards import format_standards_for_prompt, get_standards_for_lesson

if TYPE_CHECKING:
    from clawed.models import LessonBrief, TeacherPersona, UnitPlan

logger = logging.getLogger(__name__)

_PROMPT_DIR = Path(__file__).parent / "prompts"
_PHASE_TIMEOUT_SEC = 240  # 4 minutes per phase (5x shorter than monolith)
_PHASE_MAX_RETRIES = 2


# ══════════════════════════════════════════════════════════════════════
# Prompt rendering helpers
# ══════════════════════════════════════════════════════════════════════


def _load_prompt(name: str) -> str:
    """Load a phase prompt template from disk."""
    return (_PROMPT_DIR / name).read_text(encoding="utf-8")


def _render_vocabulary_list(vocab: list) -> str:
    """Render Phase 1 vocabulary as a bullet list for Phase 2 context."""
    if not vocab:
        return "_(no vocabulary in this lesson)_"
    lines = []
    for v in vocab:
        lines.append(f"- **{v.term}**: {v.definition}")
    return "\n".join(lines)


def _render_primary_sources_block(sources: list) -> str:
    """Render Phase 1 primary sources as a block for downstream phases."""
    if not sources:
        return "_(no primary sources — this is a problem)_"
    lines = []
    for ps in sources:
        lines.append(f"### {ps.id}: {ps.title}")
        lines.append(f"- **Attribution:** {ps.attribution}")
        # Truncate content to avoid bloating the downstream prompt
        content = ps.content_text[:500]
        if len(ps.content_text) > 500:
            content += "..."
        lines.append(f"- **Content:** {content}")
        lines.append("")
    return "\n".join(lines)


def _render_direct_instruction_block(sections: list) -> str:
    """Render Phase 2 direct instruction headings for Phase 3/4 context."""
    if not sections:
        return "_(no direct instruction)_"
    lines = []
    for i, sec in enumerate(sections, start=1):
        lines.append(f"{i}. **{sec.heading}**: {sec.content[:200]}...")
    return "\n".join(lines)


def _render_direct_instruction_headings(sections: list) -> str:
    """Render just the section headings for Phase 4."""
    return ", ".join(sec.heading for sec in sections) or "_(none)_"


def _render_misconceptions_list(miscs: list) -> str:
    if not miscs:
        return "_(none identified)_"
    return "\n".join(f"- {m}" for m in miscs)


def _render_vocabulary_terms(vocab: list) -> str:
    """Render vocabulary as a comma-separated list of terms."""
    return ", ".join(v.term for v in vocab) if vocab else "_(none)_"


def _render_persona_voice_hint(persona) -> str:
    """Render a short persona voice reminder for phase prompts."""
    if not persona:
        return ""
    voice_sample = getattr(persona, "voice_sample", "") or ""
    if voice_sample:
        return (
            f"\n## Voice Note — Match this teacher's style:\n\n"
            f"Voice sample: \"{voice_sample[:300]}...\"\n"
        )
    return ""


# ══════════════════════════════════════════════════════════════════════
# Phase execution
# ══════════════════════════════════════════════════════════════════════


async def _run_phase(
    phase_name: str,
    prompt: str,
    system: str,
    model_class,
    client,
    task_type: str,
):
    """Run a single phase with retries and timeout."""
    import asyncio

    last_error = None
    for attempt in range(_PHASE_MAX_RETRIES):
        try:
            logger.info(
                "Phase %s attempt %d/%d",
                phase_name, attempt + 1, _PHASE_MAX_RETRIES,
            )
            result = await asyncio.wait_for(
                client.safe_generate_json(
                    prompt=prompt,
                    model_class=model_class,
                    system=system,
                    temperature=0.6,
                    max_tokens=4000,  # ~3K tokens per phase
                ),
                timeout=_PHASE_TIMEOUT_SEC,
            )
            return result
        except asyncio.TimeoutError:
            last_error = f"Phase {phase_name} timed out after {_PHASE_TIMEOUT_SEC}s"
            logger.warning(last_error)
        except Exception as e:
            last_error = f"Phase {phase_name} failed: {type(e).__name__}: {e}"
            logger.warning(last_error)
            if attempt < _PHASE_MAX_RETRIES - 1:
                await asyncio.sleep(2 ** attempt)

    raise RuntimeError(last_error)


# ══════════════════════════════════════════════════════════════════════
# Phase 1: Skeleton + Primary Sources
# ══════════════════════════════════════════════════════════════════════


async def _phase1_skeleton(
    unit: "UnitPlan",
    lesson_brief: "LessonBrief",
    total_lessons: int,
    persona: "TeacherPersona",
    standards_text: str,
    standards_framework: str,
    teacher_materials: str,
    few_shot_context: str,
    system: str,
    client,
    task_type: str,
    brain_prompt: str = "",
) -> Phase1Skeleton:
    """Generate Phase 1: skeleton + primary sources."""
    template = _load_prompt("phase1_skeleton.txt")
    prompt = template.format(
        unit_title=unit.title,
        unit_overview=unit.overview,
        subject=unit.subject,
        grade_level=unit.grade_level,
        topic=lesson_brief.topic,
        objective=lesson_brief.description or unit.overview,
        lesson_number=lesson_brief.lesson_number,
        total_lessons=total_lessons,
        duration_minutes=45,  # Default; Phase 1 can override in its output
        standards=standards_text,
        standards_framework=standards_framework,
        few_shot_context=few_shot_context,
        teacher_materials=teacher_materials,
    )
    if brain_prompt:
        prompt = brain_prompt + "\n\n" + prompt

    return await _run_phase(
        "1-skeleton",
        prompt,
        system,
        Phase1Skeleton,
        client,
        task_type,
    )


# ══════════════════════════════════════════════════════════════════════
# Phase 2: Instruction + Guided Notes
# ══════════════════════════════════════════════════════════════════════


async def _phase2_instruction(
    phase1: Phase1Skeleton,
    persona: "TeacherPersona",
    system: str,
    client,
    task_type: str,
) -> Phase2Instruction:
    """Generate Phase 2 using Phase 1 as context."""
    template = _load_prompt("phase2_instruction.txt")
    prompt = template.format(
        title=phase1.title,
        subject=phase1.subject,
        grade_level=phase1.grade_level,
        duration_minutes=phase1.duration_minutes,
        topic=phase1.topic,
        objective=phase1.objective,
        lesson_personality=phase1.lesson_personality,
        lesson_format=phase1.lesson_format,
        vocabulary_list=_render_vocabulary_list(phase1.vocabulary),
        primary_sources_block=_render_primary_sources_block(phase1.primary_sources),
        misconceptions_list=_render_misconceptions_list(phase1.misconceptions),
        persona_voice_hint=_render_persona_voice_hint(persona),
    )

    return await _run_phase(
        "2-instruction",
        prompt,
        system,
        Phase2Instruction,
        client,
        task_type,
    )


# ══════════════════════════════════════════════════════════════════════
# Phase 3: Activities
# ══════════════════════════════════════════════════════════════════════


async def _phase3_activities(
    phase1: Phase1Skeleton,
    phase2: Phase2Instruction,
    system: str,
    client,
    task_type: str,
) -> Phase3Activities:
    """Generate Phase 3 using Phase 1+2 context."""
    template = _load_prompt("phase3_activities.txt")
    prompt = template.format(
        title=phase1.title,
        duration_minutes=phase1.duration_minutes,
        lesson_format=phase1.lesson_format,
        lesson_personality=phase1.lesson_personality,
        primary_sources_block=_render_primary_sources_block(phase1.primary_sources),
        direct_instruction_block=_render_direct_instruction_block(phase2.direct_instruction),
    )

    return await _run_phase(
        "3-activities",
        prompt,
        system,
        Phase3Activities,
        client,
        task_type,
    )


# ══════════════════════════════════════════════════════════════════════
# Phase 4: Assessment + Differentiation
# ══════════════════════════════════════════════════════════════════════


async def _phase4_assessment(
    phase1: Phase1Skeleton,
    phase2: Phase2Instruction,
    persona: "TeacherPersona",
    system: str,
    client,
    task_type: str,
) -> Phase4Assessment:
    """Generate Phase 4 using Phase 1+2 context."""
    writing_framework = getattr(persona, "writing_framework", "") or "Claim and Evidence"
    template = _load_prompt("phase4_assessment.txt")
    prompt = template.format(
        title=phase1.title,
        subject=phase1.subject,
        grade_level=phase1.grade_level,
        objective=phase1.objective,
        writing_framework=writing_framework,
        primary_sources_block=_render_primary_sources_block(phase1.primary_sources),
        vocabulary_terms=_render_vocabulary_terms(phase1.vocabulary),
        direct_instruction_headings=_render_direct_instruction_headings(phase2.direct_instruction),
    )

    return await _run_phase(
        "4-assessment",
        prompt,
        system,
        Phase4Assessment,
        client,
        task_type,
    )


# ══════════════════════════════════════════════════════════════════════
# Merge
# ══════════════════════════════════════════════════════════════════════


def merge_phases(
    phase1: Phase1Skeleton,
    phase2: Phase2Instruction,
    phase3: Phase3Activities,
    phase4: Phase4Assessment,
    brain_context=None,
    citations=None,
) -> MasterContent:
    """Merge 4 phase outputs into a complete MasterContent."""
    return MasterContent(
        # Phase 1 — skeleton
        title=phase1.title,
        subject=phase1.subject,
        grade_level=phase1.grade_level,
        topic=phase1.topic,
        standards=phase1.standards,
        objective=phase1.objective,
        duration_minutes=phase1.duration_minutes,
        vocabulary=phase1.vocabulary,
        primary_sources=phase1.primary_sources,
        misconceptions=phase1.misconceptions,
        prerequisite_skills=phase1.prerequisite_skills,
        lesson_format=phase1.lesson_format,
        lesson_personality=phase1.lesson_personality,
        materials_needed=phase1.materials_needed,
        # Phase 2 — instruction
        direct_instruction=phase2.direct_instruction,
        guided_notes=phase2.guided_notes,
        formative_checks=phase2.formative_checks,
        # Phase 3 — activities
        do_now=phase3.do_now,
        stations=phase3.stations,
        jigsaw=phase3.jigsaw,
        creative_activity=phase3.creative_activity,
        independent_work=phase3.independent_work,
        minute_by_minute=phase3.minute_by_minute,
        # Phase 4 — assessment
        exit_ticket=phase4.exit_ticket,
        differentiation=phase4.differentiation,
        homework=phase4.homework,
        # Brain integration
        brain_context=brain_context,
        source_attributions=citations or [],
    )


# ══════════════════════════════════════════════════════════════════════
# Top-level pipeline entrypoint
# ══════════════════════════════════════════════════════════════════════


async def generate_master_content_phased(
    lesson_number: int,
    unit,
    persona,
    include_homework: bool = True,
    config=None,
    task_type: str = "master_content",
    state: str = "",
    teacher_materials: str = "",
) -> MasterContent:
    """Generate a MasterContent via the 4-phase pipeline.

    This is the NEW entry point that replaces the single-call monolith.
    If any phase fails after retries, the exception propagates and the
    caller can fall back to `generate_master_content` (single-call).

    Benefits over single-call:
    - Smaller per-call output → reliable on slow/flaky models
    - Per-phase retry — don't waste 10min regenerating whole lesson
    - Sequential context flow — downstream phases reference upstream output
    - Smaller prompts per phase → less token pressure
    """
    from clawed.corpus import get_few_shot_context
    from clawed.lesson import _build_system_prompt
    from clawed.llm import LLMClient
    from clawed.model_router import route as route_model

    # Resolve lesson_brief
    if lesson_number < 1 or lesson_number > len(unit.daily_lessons):
        raise ValueError(
            f"lesson_number {lesson_number} out of range "
            f"(1..{len(unit.daily_lessons)})"
        )
    lesson_brief = unit.daily_lessons[lesson_number - 1]

    # Standards lookup
    try:
        standards_list = get_standards_for_lesson(
            subject=unit.subject,
            grade=unit.grade_level,
            state=state,
            topic=lesson_brief.topic,
        )
        standards_text = format_standards_for_prompt(standards_list)
    except Exception:
        standards_text = "\n".join(f"- {s}" for s in unit.standards)

    # Few-shot context (smaller than single-call — just 1-2 best examples)
    try:
        few_shot_context = get_few_shot_context(
            content_type="lesson_plan",
            subject=unit.subject.lower(),
            grade_level=unit.grade_level,
        )
    except Exception:
        few_shot_context = ""

    # Build brain context (for Phase 1 prompt injection)
    brain_prompt = ""
    brain_ctx_obj = None
    try:
        from clawed.brain.context import build_brain_context
        from clawed.brain.store import BrainStore
        brain_store = BrainStore()
        brain_ctx_obj = build_brain_context(
            topic=lesson_brief.topic,
            unit_title=unit.title,
            store=brain_store,
        )
        brain_prompt = brain_ctx_obj.render_for_prompt()
    except Exception as exc:
        logger.debug("Brain context lookup skipped: %s", exc)

    # System prompt + LLM client
    system = _build_system_prompt(persona, config, subject=unit.subject)
    if task_type and config:
        config = route_model(task_type, config)
    client = LLMClient(config)

    # Warmup: send a trivial ping to wake up the cloud model
    try:
        import asyncio
        await asyncio.wait_for(
            client.generate(
                prompt="ok",
                system="Respond with only: ok",
                temperature=0.1,
                max_tokens=5,
            ),
            timeout=45,
        )
        logger.info("LLM warmup ping successful")
    except Exception as exc:
        logger.debug("Warmup ping failed (non-blocking): %s", exc)

    # ── Phase 1: Skeleton ─────────────────────────────────────────
    standards_framework = getattr(
        getattr(config, "teacher_profile", None),
        "standards_framework", "",
    ) if config else ""

    phase1 = await _phase1_skeleton(
        unit=unit,
        lesson_brief=lesson_brief,
        total_lessons=len(unit.daily_lessons),
        persona=persona,
        standards_text=standards_text,
        standards_framework=standards_framework,
        teacher_materials=teacher_materials,
        few_shot_context=few_shot_context,
        system=system,
        client=client,
        task_type=task_type,
        brain_prompt=brain_prompt,
    )
    logger.info(
        "Phase 1 complete: %d sources, %d vocab",
        len(phase1.primary_sources), len(phase1.vocabulary),
    )

    # ── Phase 2: Instruction ──────────────────────────────────────
    phase2 = await _phase2_instruction(
        phase1=phase1,
        persona=persona,
        system=system,
        client=client,
        task_type=task_type,
    )
    logger.info(
        "Phase 2 complete: %d sections, %d guided notes",
        len(phase2.direct_instruction), len(phase2.guided_notes),
    )

    # ── Phase 3: Activities ───────────────────────────────────────
    phase3 = await _phase3_activities(
        phase1=phase1,
        phase2=phase2,
        system=system,
        client=client,
        task_type=task_type,
    )
    logger.info(
        "Phase 3 complete: %d stations, creative=%s, jigsaw=%s",
        len(phase3.stations),
        bool(phase3.creative_activity),
        bool(phase3.jigsaw),
    )

    # ── Phase 4: Assessment ───────────────────────────────────────
    phase4 = await _phase4_assessment(
        phase1=phase1,
        phase2=phase2,
        persona=persona,
        system=system,
        client=client,
        task_type=task_type,
    )
    logger.info(
        "Phase 4 complete: %d exit questions, diff=%s/%s/%s",
        len(phase4.exit_ticket),
        len(phase4.differentiation.struggling),
        len(phase4.differentiation.advanced),
        len(phase4.differentiation.ell),
    )

    # ── Merge ─────────────────────────────────────────────────────
    master = merge_phases(
        phase1, phase2, phase3, phase4,
        brain_context=brain_ctx_obj,
        citations=list(brain_ctx_obj.citations) if brain_ctx_obj else [],
    )
    logger.info("4-phase generation complete: %s", master.title)
    return master
