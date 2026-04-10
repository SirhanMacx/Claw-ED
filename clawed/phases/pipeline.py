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
    Phase2aDirectInstruction,
    Phase2bGuidedNotes,
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

# Ollama Cloud model fallback chain. When a phase fails repeatedly on the
# configured model, we rotate through these alternatives automatically.
# Override with CLAWED_PHASE_MODELS env var (comma-separated).
_FALLBACK_MODEL_CHAIN = [
    "glm-5.1:cloud",
    "minimax-m2.7:cloud",
]


# ══════════════════════════════════════════════════════════════════════
# Prompt rendering helpers
# ══════════════════════════════════════════════════════════════════════


def _load_prompt(name: str) -> str:
    """Load a phase prompt template from disk."""
    return (_PROMPT_DIR / name).read_text(encoding="utf-8")


def _fill_template(template: str, **kwargs) -> str:
    """Replace {variable} placeholders in a template.

    Unlike str.format(), this does NOT interpret unrelated braces (like
    the literal JSON braces in the output-format examples) as format
    specifiers. It only replaces exact matches of {key} for each key
    in kwargs.
    """
    result = template
    for key, value in kwargs.items():
        result = result.replace("{" + key + "}", str(value))
    return result


def _render_vocabulary_list(vocab: list) -> str:
    """Render Phase 1 vocabulary as a bullet list for Phase 2 context."""
    if not vocab:
        return "_(no vocabulary in this lesson)_"
    lines = []
    for v in vocab:
        lines.append(f"- **{v.term}**: {v.definition}")
    return "\n".join(lines)


def _render_primary_sources_block(sources: list, content_chars: int = 150) -> str:
    """Render Phase 1 primary sources for downstream phases.

    Aggressively trimmed to keep downstream prompts <3KB. Downstream
    phases mostly need to REFERENCE sources by id+title; full content
    is rarely needed and bloats the input.
    """
    if not sources:
        return "_(no primary sources)_"
    lines = []
    for ps in sources:
        content = ps.content_text[:content_chars].replace("\n", " ")
        if len(ps.content_text) > content_chars:
            content += "..."
        lines.append(f"- {ps.id} | {ps.title} — {content}")
    return "\n".join(lines)


def _render_primary_sources_mini(sources: list) -> str:
    """Ultra-compact source list for Phase 3 (stations just need id+title)."""
    if not sources:
        return "_(none)_"
    return "\n".join(f"- {ps.id}: {ps.title}" for ps in sources)


def _render_direct_instruction_block(sections: list) -> str:
    """Render Phase 2 direct instruction headings for Phase 3/4 context.

    Compact: heading + 100 chars of content. Phases 3/4 mostly need
    to know WHAT was taught to align their activities and assessments.
    """
    if not sections:
        return "_(no direct instruction)_"
    lines = []
    for i, sec in enumerate(sections, start=1):
        snippet = sec.content[:100].replace("\n", " ")
        lines.append(f"{i}. {sec.heading} — {snippet}...")
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


def _build_slim_system_prompt(persona, subject: str, rich: bool = False) -> str:
    """Build a system prompt for phase calls.

    Two modes:
    - slim (rich=False): ~500-800 chars. For Phase 3/4 where the
      persona influence matters less.
    - rich (rich=True): ~1500-2000 chars. Includes voice_sample,
      signature_moves, scaffolding_moves, and pedagogical fingerprint.
      For Phase 1 (skeleton sets the voice) and Phase 2 (direct
      instruction needs the teacher's actual scripted style).

    Both fit within GLM 5.1 Cloud's reliable input range (<3KB total
    after prompt is added).
    """
    if persona is None:
        return (
            f"You are a master {subject} teacher generating high-quality "
            "lesson plans. Write in a warm, direct tone with exact scripted "
            "dialogue. Respond with ONLY valid JSON — no markdown, no "
            "commentary, no XML tags."
        )

    style = getattr(persona, "teaching_style", None)
    style_str = str(style).split(".")[-1].lower().replace("_", " ") if style else "direct instruction"

    tone = (getattr(persona, "tone", "") or "")[:150]
    framework = (getattr(persona, "writing_framework", "") or "").split(":")[0][:60]

    parts = [
        f"You are a master {subject} teacher generating high-quality "
        f"lesson plans with a {style_str} style.",
    ]
    if tone:
        parts.append(f"Tone: {tone}.")
    if framework:
        parts.append(f"Writing framework: {framework}.")

    if rich:
        # Voice sample — the teacher's actual writing
        voice = (getattr(persona, "voice_sample", "") or "").strip()
        if voice:
            parts.append(
                f"\n\nYour voice sounds like this — match this exact style: "
                f'"{voice[:400]}"'
            )

        # Signature moves — distinctive patterns
        sig_moves = getattr(persona, "signature_moves", []) or []
        if sig_moves:
            parts.append("\nSignature moves you ALWAYS use:")
            for m in sig_moves[:3]:
                parts.append(f"- {m[:200]}")

        # Scaffolding moves
        scaffold = getattr(persona, "scaffolding_moves", []) or []
        if scaffold:
            parts.append("\nScaffolding strategies you favor:")
            for s in scaffold[:2]:
                parts.append(f"- {s[:200]}")

        # Do Now style preference
        do_now_style = getattr(persona, "do_now_style", "") or ""
        if do_now_style:
            parts.append(f"\nYour Do Nows: {do_now_style[:200]}")

        # Activity patterns
        activity = getattr(persona, "activity_patterns", []) or []
        if activity:
            parts.append(f"\nActivity pattern you use: {activity[0][:200]}")

    parts.append(
        "\n\nRespond with ONLY valid JSON — no markdown, no commentary, "
        "no XML tags. Never truncate output."
    )
    return " ".join(parts)


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
    """Run a single phase with multi-model fallback.

    Tries the configured model first. If it times out or returns empty,
    automatically rotates through _FALLBACK_MODEL_CHAIN (or the
    CLAWED_PHASE_MODELS env override). This handles Ollama Cloud
    flakiness gracefully — when GLM 5.1 is down, minimax picks up.
    """
    import asyncio
    import os as _os

    # Build the model chain: configured model first, then fallbacks
    configured_model = getattr(client.config, "ollama_model", "") or ""
    env_chain = _os.environ.get("CLAWED_PHASE_MODELS", "")
    if env_chain:
        chain = [m.strip() for m in env_chain.split(",") if m.strip()]
    else:
        chain = list(_FALLBACK_MODEL_CHAIN)
        # Move the configured model to the front if it's in the list,
        # otherwise prepend it
        if configured_model in chain:
            chain.remove(configured_model)
        if configured_model:
            chain.insert(0, configured_model)

    last_error = None
    for model_idx, model_name in enumerate(chain):
        # Swap the client's model for this attempt
        original_model = client.config.ollama_model
        client.config.ollama_model = model_name

        try:
            for attempt in range(_PHASE_MAX_RETRIES):
                try:
                    logger.info(
                        "Phase %s model=%s attempt %d/%d",
                        phase_name, model_name, attempt + 1, _PHASE_MAX_RETRIES,
                    )
                    result = await asyncio.wait_for(
                        client.safe_generate_json(
                            prompt=prompt,
                            model_class=model_class,
                            system=system,
                            temperature=0.6,
                            max_tokens=4000,
                        ),
                        timeout=_PHASE_TIMEOUT_SEC,
                    )
                    if model_idx > 0:
                        logger.info(
                            "Phase %s succeeded on fallback model %s",
                            phase_name, model_name,
                        )
                    return result
                except asyncio.TimeoutError:
                    last_error = (
                        f"Phase {phase_name} timed out on {model_name} "
                        f"after {_PHASE_TIMEOUT_SEC}s"
                    )
                    logger.warning(last_error)
                    # On timeout, move to next model immediately (no retry)
                    break
                except Exception as e:
                    last_error = (
                        f"Phase {phase_name} failed on {model_name}: "
                        f"{type(e).__name__}: {e}"
                    )
                    logger.warning(last_error)
                    if attempt < _PHASE_MAX_RETRIES - 1:
                        await asyncio.sleep(2 ** attempt)
        finally:
            client.config.ollama_model = original_model

        if model_idx < len(chain) - 1:
            logger.info(
                "Phase %s: falling back from %s to %s",
                phase_name, model_name, chain[model_idx + 1],
            )

    raise RuntimeError(last_error or f"Phase {phase_name} exhausted all models")


# ══════════════════════════════════════════════════════════════════════
# Phase 1: Skeleton + Primary Sources
# ══════════════════════════════════════════════════════════════════════


def _validate_phase1(phase1: Phase1Skeleton) -> list[str]:
    """Quality validator for Phase 1 output."""
    issues: list[str] = []
    if len(phase1.primary_sources) < 3:
        issues.append(
            f"Only {len(phase1.primary_sources)} primary sources — need 3-4"
        )
    for i, ps in enumerate(phase1.primary_sources):
        if not ps.content_text or len(ps.content_text) < 100:
            issues.append(
                f"Primary source {i+1} '{ps.title}' content_text too short "
                f"({len(ps.content_text or '')} chars) — need 100+ for real quote"
            )
    if len(phase1.vocabulary) < 6:
        issues.append(
            f"Only {len(phase1.vocabulary)} vocabulary terms — need 6-8"
        )
    if not phase1.lesson_personality or len(phase1.lesson_personality) < 20:
        issues.append("lesson_personality missing or too short — need 20+ chars")
    if not phase1.title or len(phase1.title) < 10:
        issues.append("title missing or too short")
    return issues


async def _phase1_skeleton(
    unit: "UnitPlan",
    lesson_brief: "LessonBrief",
    standards_text: str,
    teacher_materials: str,
    system: str,
    client,
    task_type: str,
    brain_prompt: str = "",
) -> Phase1Skeleton:
    """Generate Phase 1 with quality validation and retry."""
    template = _load_prompt("phase1_skeleton.txt")
    tm = teacher_materials[:800] if teacher_materials else ""
    base_prompt = _fill_template(
        template,
        unit_title=unit.title[:200],
        subject=unit.subject,
        grade_level=unit.grade_level,
        topic=lesson_brief.topic,
        objective=(lesson_brief.description or unit.overview)[:300],
        duration_minutes=45,
        standards=standards_text[:500],
        teacher_materials=tm,
    )

    quality_header = (
        "## STRICT MINIMUMS\n"
        "- primary_sources: 3-4 entries, each with content_text 100+ chars "
        "(REAL historical quote with attribution)\n"
        "- vocabulary: 4-8 terms with definition + context_sentence\n"
        "- lesson_personality: 20+ chars (the lesson's hook theme)\n"
        "- title: descriptive (10+ chars)\n\n"
    )
    prompt = quality_header + base_prompt
    if brain_prompt:
        prompt = brain_prompt[:800] + "\n\n" + prompt
    logger.info("Phase 1 prompt size: %d chars", len(prompt))

    phase1 = await _run_phase(
        "1-skeleton",
        prompt,
        system,
        Phase1Skeleton,
        client,
        task_type,
    )

    # Validate and retry once if needed
    issues = _validate_phase1(phase1)
    if issues:
        logger.warning(
            "Phase 1 quality issues — retrying:\n%s",
            "\n".join(f"- {i}" for i in issues),
        )
        retry_prompt = (
            quality_header
            + "## YOUR PREVIOUS ATTEMPT FAILED:\n"
            + "\n".join(f"- {i}" for i in issues)
            + "\n\nFix ALL issues. Use REAL historical documents with full text quotes.\n\n"
            + base_prompt
        )
        if brain_prompt:
            retry_prompt = brain_prompt[:800] + "\n\n" + retry_prompt
        phase1_retry = await _run_phase(
            "1-skeleton-retry",
            retry_prompt,
            system,
            Phase1Skeleton,
            client,
            task_type,
        )
        retry_issues = _validate_phase1(phase1_retry)
        if not retry_issues or len(retry_issues) < len(issues):
            logger.info("Phase 1 retry improved quality")
            return phase1_retry

    return phase1


# ══════════════════════════════════════════════════════════════════════
# Phase 2: Instruction + Guided Notes
# ══════════════════════════════════════════════════════════════════════


_DIALOGUE_VERBS = (
    "ask:", "say:", "tell ", "show ", "wait", "call on", "have students",
    "raise your", "thumbs up", "turn to your partner", "think-pair-share",
    "display", "read aloud", "model",
)


def _count_dialogue_verbs(script: str) -> int:
    """Count how many directing verbs appear in a teacher_script."""
    if not script:
        return 0
    lower = script.lower()
    return sum(lower.count(v) for v in _DIALOGUE_VERBS)


def _validate_phase2a(phase2a: Phase2aDirectInstruction) -> list[str]:
    """Quality validator for Phase 2a (direct_instruction only)."""
    issues: list[str] = []
    if len(phase2a.direct_instruction) < 3:
        issues.append(
            f"Only {len(phase2a.direct_instruction)} direct_instruction "
            f"sections — need EXACTLY 3"
        )
    for i, section in enumerate(phase2a.direct_instruction):
        script = section.teacher_script or ""
        script_len = len(script)
        if script_len < 200:
            issues.append(
                f"Section {i+1} '{section.heading}' teacher_script is only "
                f"{script_len} chars — need 250+"
            )
        questions = script.count("?")
        if questions < 3:
            issues.append(
                f"Section {i+1} '{section.heading}' has only {questions} "
                f"question marks — need 3+"
            )
        verbs = _count_dialogue_verbs(script)
        if verbs < 3:
            issues.append(
                f"Section {i+1} '{section.heading}' has only {verbs} "
                f"directing verbs — need 3+"
            )
    for i, section in enumerate(phase2a.direct_instruction):
        if not section.hook or len(section.hook) < 20:
            issues.append(
                f"Section {i+1} '{section.heading}' missing hook"
            )
        if not section.transition or len(section.transition) < 20:
            issues.append(
                f"Section {i+1} '{section.heading}' missing transition"
            )
    return issues


def _validate_phase2b(phase2b: Phase2bGuidedNotes) -> list[str]:
    """Quality validator for Phase 2b (guided_notes + formative_checks)."""
    issues: list[str] = []
    if len(phase2b.guided_notes) < 10:
        issues.append(
            f"Only {len(phase2b.guided_notes)} guided_notes — need 10-12"
        )
    if len(phase2b.formative_checks) < 2:
        issues.append(
            f"Only {len(phase2b.formative_checks)} formative_checks — need 2-3"
        )
    return issues


def _render_section_headings_block(sections: list) -> str:
    """Render section headings as a numbered list for Phase 2b."""
    if not sections:
        return "_(no sections)_"
    return "\n".join(
        f'{i+1}. "{sec.heading}"' for i, sec in enumerate(sections)
    )


def _render_section_content_block(sections: list) -> str:
    """Render section content summaries for Phase 2b."""
    if not sections:
        return "_(no content)_"
    lines = []
    for sec in sections:
        snippet = (sec.content or "")[:150].replace("\n", " ")
        lines.append(f"- {sec.heading}: {snippet}...")
    return "\n".join(lines)


async def _phase2a_direct_instruction(
    phase1: Phase1Skeleton,
    system: str,
    client,
    task_type: str,
) -> Phase2aDirectInstruction:
    """Generate Phase 2a — direct_instruction sections only."""
    template = _load_prompt("phase2a_instruction.txt")
    prompt = _fill_template(
        template,
        title=phase1.title,
        grade_level=phase1.grade_level,
        duration_minutes=phase1.duration_minutes,
        topic=phase1.topic,
        lesson_format=phase1.lesson_format,
        lesson_personality=phase1.lesson_personality,
        vocabulary_list=_render_vocabulary_list(phase1.vocabulary),
        primary_sources_block=_render_primary_sources_block(phase1.primary_sources),
        misconceptions_list=_render_misconceptions_list(phase1.misconceptions),
    )
    logger.info("Phase 2a prompt size: %d chars", len(prompt))

    phase2a = await _run_phase(
        "2a-instruction",
        prompt,
        system,
        Phase2aDirectInstruction,
        client,
        task_type,
    )

    issues = _validate_phase2a(phase2a)
    if issues:
        logger.warning(
            "Phase 2a quality issues — retrying:\n%s",
            "\n".join(f"- {i}" for i in issues),
        )
        retry_prompt = (
            "## YOUR PREVIOUS ATTEMPT FAILED:\n"
            + "\n".join(f"- {i}" for i in issues)
            + "\n\nFix ALL issues. Use EXACT scripted dialogue with directing verbs.\n\n"
            + prompt
        )
        phase2a_retry = await _run_phase(
            "2a-instruction-retry",
            retry_prompt,
            system,
            Phase2aDirectInstruction,
            client,
            task_type,
        )
        retry_issues = _validate_phase2a(phase2a_retry)
        if not retry_issues or len(retry_issues) < len(issues):
            return phase2a_retry

    return phase2a


async def _phase2b_guided_notes(
    phase1: Phase1Skeleton,
    phase2a: Phase2aDirectInstruction,
    system: str,
    client,
    task_type: str,
) -> Phase2bGuidedNotes:
    """Generate Phase 2b — guided_notes + formative_checks."""
    template = _load_prompt("phase2b_guided_notes.txt")
    prompt = _fill_template(
        template,
        title=phase1.title,
        topic=phase1.topic,
        vocabulary_list=_render_vocabulary_list(phase1.vocabulary),
        section_headings_block=_render_section_headings_block(
            phase2a.direct_instruction
        ),
        section_content_block=_render_section_content_block(
            phase2a.direct_instruction
        ),
    )
    logger.info("Phase 2b prompt size: %d chars", len(prompt))

    phase2b = await _run_phase(
        "2b-guided-notes",
        prompt,
        system,
        Phase2bGuidedNotes,
        client,
        task_type,
    )

    issues = _validate_phase2b(phase2b)
    if issues:
        logger.warning(
            "Phase 2b quality issues — retrying:\n%s",
            "\n".join(f"- {i}" for i in issues),
        )
        retry_prompt = (
            "## YOUR PREVIOUS ATTEMPT FAILED:\n"
            + "\n".join(f"- {i}" for i in issues)
            + "\n\nFix ALL issues. Produce 10-12 guided notes distributed across sections.\n\n"
            + prompt
        )
        phase2b_retry = await _run_phase(
            "2b-guided-notes-retry",
            retry_prompt,
            system,
            Phase2bGuidedNotes,
            client,
            task_type,
        )
        retry_issues = _validate_phase2b(phase2b_retry)
        if not retry_issues or len(retry_issues) < len(issues):
            return phase2b_retry

    return phase2b


async def _phase2_instruction(
    phase1: Phase1Skeleton,
    persona: "TeacherPersona",
    system: str,
    client,
    task_type: str,
) -> Phase2Instruction:
    """Generate Phase 2 by calling 2a + 2b sequentially.

    Splitting prevents token exhaustion. Phase 2a focuses entirely on
    direct_instruction (long teacher_scripts), Phase 2b focuses entirely
    on guided_notes (lots of small entries). Each gets the model's full
    output budget for its task.
    """
    phase2a = await _phase2a_direct_instruction(
        phase1=phase1, system=system, client=client, task_type=task_type,
    )
    logger.info(
        "Phase 2a complete: %d sections", len(phase2a.direct_instruction),
    )

    phase2b = await _phase2b_guided_notes(
        phase1=phase1, phase2a=phase2a, system=system,
        client=client, task_type=task_type,
    )
    logger.info(
        "Phase 2b complete: %d guided notes, %d formative checks",
        len(phase2b.guided_notes), len(phase2b.formative_checks),
    )

    # Merge into combined Phase2Instruction
    return Phase2Instruction(
        direct_instruction=phase2a.direct_instruction,
        guided_notes=phase2b.guided_notes,
        formative_checks=phase2b.formative_checks,
    )


# ══════════════════════════════════════════════════════════════════════
# Phase 3: Activities
# ══════════════════════════════════════════════════════════════════════


def _validate_phase3(phase3: Phase3Activities, num_sources: int) -> list[str]:
    """Quality validator for Phase 3 output. Returns list of issues."""
    issues: list[str] = []
    # Stations: should match number of sources (3-4 typical)
    expected_stations = max(3, min(num_sources, 4))
    if len(phase3.stations) < expected_stations:
        issues.append(
            f"Only {len(phase3.stations)} stations — need {expected_stations}+ "
            f"(one per primary source)"
        )
    # Creative activity is REQUIRED
    if phase3.creative_activity is None:
        issues.append("creative_activity is null — REQUIRED for every lesson")
    elif not phase3.creative_activity.title or not phase3.creative_activity.scenario:
        issues.append("creative_activity missing title or scenario")
    # Minute-by-minute must be populated
    if not phase3.minute_by_minute or len(phase3.minute_by_minute) < 4:
        issues.append(
            f"minute_by_minute has {len(phase3.minute_by_minute)} blocks — "
            f"need 5+ (Do Now, Direct Instruction, Activity, Exit Ticket, Closing)"
        )
    # Independent work
    if phase3.independent_work is None:
        issues.append("independent_work is null — should be set")
    return issues


async def _phase3_activities(
    phase1: Phase1Skeleton,
    phase2: Phase2Instruction,
    system: str,
    client,
    task_type: str,
) -> Phase3Activities:
    """Generate Phase 3 with quality validation and retry.

    If validation fails, retries once with an enhanced prompt that
    explicitly enumerates the missing/insufficient fields.
    """
    template = _load_prompt("phase3_activities.txt")
    base_prompt = _fill_template(template,
        title=phase1.title,
        duration_minutes=phase1.duration_minutes,
        lesson_format=phase1.lesson_format,
        lesson_personality=phase1.lesson_personality,
        primary_sources_block=_render_primary_sources_mini(phase1.primary_sources),
        direct_instruction_block=_render_direct_instruction_block(phase2.direct_instruction),
    )
    num_sources = len(phase1.primary_sources)
    expected_stations = max(3, min(num_sources, 4))

    # Add explicit minimum requirements at the top
    quality_header = (
        f"## STRICT MINIMUMS (must be met or output will be rejected)\n"
        f"- stations: EXACTLY {expected_stations} entries "
        f"(one per primary source, source_ref must match a Phase 1 id)\n"
        f"- creative_activity: REQUIRED, must have title + scenario + roles + "
        f"deliverable. NEVER null.\n"
        f"- minute_by_minute: AT LEAST 5 time blocks summing to "
        f"{phase1.duration_minutes} min\n"
        f"- independent_work: REQUIRED with task + rubric_snippet + exemplar\n"
        f"\n"
    )
    prompt = quality_header + base_prompt
    logger.info("Phase 3 prompt size: %d chars", len(prompt))

    phase3 = await _run_phase(
        "3-activities",
        prompt,
        system,
        Phase3Activities,
        client,
        task_type,
    )

    # Validate and retry if quality is insufficient
    issues = _validate_phase3(phase3, num_sources)
    if issues:
        logger.warning(
            "Phase 3 quality issues — retrying:\n%s",
            "\n".join(f"- {i}" for i in issues),
        )
        # Build a stricter retry prompt that lists exact issues
        retry_prompt = (
            quality_header
            + "## YOUR PREVIOUS ATTEMPT FAILED THESE CHECKS:\n"
            + "\n".join(f"- {i}" for i in issues)
            + "\n\nFix ALL of these issues. Do not omit ANY required field.\n\n"
            + base_prompt
        )
        logger.info("Phase 3 retry prompt size: %d chars", len(retry_prompt))
        phase3_retry = await _run_phase(
            "3-activities-retry",
            retry_prompt,
            system,
            Phase3Activities,
            client,
            task_type,
        )
        retry_issues = _validate_phase3(phase3_retry, num_sources)
        if not retry_issues:
            logger.info("Phase 3 retry succeeded — quality issues resolved")
            return phase3_retry
        # Retry still failed — merge: use retry's better fields where available
        logger.warning(
            "Phase 3 retry still has issues, merging best of both attempts",
        )
        return _merge_phase3_attempts(phase3, phase3_retry)

    return phase3


def _merge_phase3_attempts(
    a: Phase3Activities,
    b: Phase3Activities,
) -> Phase3Activities:
    """Take the better-populated version of each field across two attempts."""
    return Phase3Activities(
        do_now=a.do_now if a.do_now else b.do_now,
        stations=a.stations if len(a.stations) >= len(b.stations) else b.stations,
        jigsaw=a.jigsaw or b.jigsaw,
        creative_activity=a.creative_activity or b.creative_activity,
        independent_work=a.independent_work or b.independent_work,
        minute_by_minute=(
            a.minute_by_minute
            if len(a.minute_by_minute) >= len(b.minute_by_minute)
            else b.minute_by_minute
        ),
    )


# ══════════════════════════════════════════════════════════════════════
# Phase 4: Assessment + Differentiation
# ══════════════════════════════════════════════════════════════════════


def _validate_phase4(phase4: Phase4Assessment) -> list[str]:
    """Quality validator for Phase 4 output."""
    issues: list[str] = []
    if len(phase4.exit_ticket) != 3:
        issues.append(
            f"exit_ticket has {len(phase4.exit_ticket)} questions — need EXACTLY 3"
        )
    for i, q in enumerate(phase4.exit_ticket):
        if not q.stimulus or len(q.stimulus) < 30:
            issues.append(
                f"exit_ticket Q{i+1} stimulus too short ({len(q.stimulus or '')} chars)"
            )
    # Bloom progression
    if len(phase4.exit_ticket) >= 3:
        levels = [q.cognitive_level for q in phase4.exit_ticket]
        expected = ["recall", "application", "analysis"]
        if levels[:3] != expected:
            issues.append(
                f"exit_ticket cognitive levels are {levels} — need {expected}"
            )
    # Differentiation
    diff = phase4.differentiation
    for group, items in [("struggling", diff.struggling), ("advanced", diff.advanced), ("ell", diff.ell)]:
        if len(items) < 3:
            issues.append(f"differentiation.{group} has only {len(items)} items — need 3+")
        # Generic phrases ban
        banned = [
            "extra time", "additional support",
            "modify as needed", "as needed",
        ]
        for item in items:
            item_lower = item.lower()
            if any(phrase in item_lower for phrase in banned):
                issues.append(
                    f"differentiation.{group} contains generic phrase: "
                    f"'{item[:60]}'"
                )
                break
    return issues


async def _phase4_assessment(
    phase1: Phase1Skeleton,
    phase2: Phase2Instruction,
    persona: "TeacherPersona",
    system: str,
    client,
    task_type: str,
) -> Phase4Assessment:
    """Generate Phase 4 with quality validation and retry."""
    writing_framework = getattr(persona, "writing_framework", "") or "Claim and Evidence"
    template = _load_prompt("phase4_assessment.txt")
    base_prompt = _fill_template(template,
        title=phase1.title,
        subject=phase1.subject,
        grade_level=phase1.grade_level,
        objective=phase1.objective,
        writing_framework=writing_framework,
        primary_sources_block=_render_primary_sources_block(phase1.primary_sources),
        vocabulary_terms=_render_vocabulary_terms(phase1.vocabulary),
        direct_instruction_headings=_render_direct_instruction_headings(phase2.direct_instruction),
    )
    quality_header = (
        "## STRICT MINIMUMS\n"
        "- exit_ticket: EXACTLY 3 questions in recall → application → analysis order\n"
        "- Each question stimulus: 30+ chars (real text/data/scenario)\n"
        "- differentiation: 3+ SPECIFIC items in EACH of struggling/advanced/ell\n"
        "- BANNED phrases in differentiation: 'extra time', 'additional support', "
        "'modify as needed', 'as needed'\n\n"
    )
    prompt = quality_header + base_prompt
    logger.info("Phase 4 prompt size: %d chars", len(prompt))

    phase4 = await _run_phase(
        "4-assessment",
        prompt,
        system,
        Phase4Assessment,
        client,
        task_type,
    )

    issues = _validate_phase4(phase4)
    if issues:
        logger.warning(
            "Phase 4 quality issues — retrying:\n%s",
            "\n".join(f"- {i}" for i in issues),
        )
        retry_prompt = (
            quality_header
            + "## YOUR PREVIOUS ATTEMPT FAILED:\n"
            + "\n".join(f"- {i}" for i in issues)
            + "\n\nFix ALL issues. Use SPECIFIC scaffolds (named tools, "
            "sentence frames, graphic organizers).\n\n"
            + base_prompt
        )
        phase4_retry = await _run_phase(
            "4-assessment-retry",
            retry_prompt,
            system,
            Phase4Assessment,
            client,
            task_type,
        )
        retry_issues = _validate_phase4(phase4_retry)
        if not retry_issues or len(retry_issues) < len(issues):
            return phase4_retry

    return phase4


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

    # Phase calls skip few-shot context entirely — the phase prompts have
    # concrete examples baked in, and GLM 5.1 Cloud chokes on prompts > ~3KB.
    # This keeps Phase 1 input at ~3-4KB instead of 10KB+.

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

    # Two system prompts:
    # - RICH for Phase 1-2 (sets the lesson voice with full pedagogical fingerprint)
    # - SLIM for Phase 3-4 (tasks where voice matters less, keeping latency low)
    system_rich = _build_slim_system_prompt(persona, unit.subject, rich=True)
    system_slim = _build_slim_system_prompt(persona, unit.subject, rich=False)
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

    # ── Phase 1: Skeleton (RICH system prompt — sets the voice) ──
    phase1 = await _phase1_skeleton(
        unit=unit,
        lesson_brief=lesson_brief,
        standards_text=standards_text,
        teacher_materials=teacher_materials,
        system=system_rich,
        client=client,
        task_type=task_type,
        brain_prompt=brain_prompt,
    )
    logger.info(
        "Phase 1 complete: %d sources, %d vocab",
        len(phase1.primary_sources), len(phase1.vocabulary),
    )

    # ── Phase 2: Instruction (RICH system prompt — teacher_script needs voice) ──
    phase2 = await _phase2_instruction(
        phase1=phase1,
        persona=persona,
        system=system_rich,
        client=client,
        task_type=task_type,
    )
    logger.info(
        "Phase 2 complete: %d sections, %d guided notes",
        len(phase2.direct_instruction), len(phase2.guided_notes),
    )

    # ── Phase 3: Activities (SLIM system prompt — structured tasks) ──
    phase3 = await _phase3_activities(
        phase1=phase1,
        phase2=phase2,
        system=system_slim,
        client=client,
        task_type=task_type,
    )
    logger.info(
        "Phase 3 complete: %d stations, creative=%s, jigsaw=%s",
        len(phase3.stations),
        bool(phase3.creative_activity),
        bool(phase3.jigsaw),
    )

    # ── Phase 4: Assessment (SLIM system prompt — exit ticket structure) ──
    phase4 = await _phase4_assessment(
        phase1=phase1,
        phase2=phase2,
        persona=persona,
        system=system_slim,
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
