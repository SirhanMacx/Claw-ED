"""Lesson plan generator — creates detailed daily lesson plans via LLM."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from clawed.corpus import get_few_shot_context
from clawed.llm import LLMClient
from clawed.master_content import MasterContent
from clawed.model_router import route as route_model
from clawed.models import AppConfig, DailyLesson, ProjectArc, TeacherPersona, UnitPlan

logger = logging.getLogger(__name__)

# ── Quality gate ──────────────────────────────────────────────────────────
# Phrases that indicate lazy, generic differentiation. If any differentiation
# item contains one of these, the quality gate rejects the lesson for retry.

_GENERIC_DIFF_PHRASES = frozenset({
    "provide extra time", "provide extra support", "provide additional support",
    "modify as needed", "adjust as necessary", "provide accommodations",
    "offer assistance", "give extra help", "provide scaffolding",
    "allow extra time", "provide support", "offer support",
    "simplify the task", "reduce complexity", "provide modifications",
    "additional practice", "extra practice", "more time",
    "work at their own pace", "extended time", "preferential seating",
    "check for understanding", "monitor progress", "provide feedback",
    "modify assessment", "reduce number of", "shorten the assignment",
})


def _validate_quality(master: MasterContent) -> list[str]:
    """Check MasterContent against pedagogical quality rules.

    Returns a list of human-readable issue strings. An empty list means the
    lesson passed all checks.
    """
    issues: list[str] = []

    # ── Primary sources ───────────────────────────────────────────────
    for ps in master.primary_sources:
        if len(ps.content_text.strip()) < 100:
            issues.append(
                f"Primary source '{ps.title}' content_text is only "
                f"{len(ps.content_text.strip())} chars — include the ACTUAL "
                "SOURCE TEXT (minimum 100 characters), not a summary"
            )
        if not ps.image_spec.strip():
            issues.append(
                f"Primary source '{ps.title}' has empty image_spec — provide "
                "a specific image search query (e.g. 'Thomas Nast Boss Tweed "
                "political cartoon 1871')"
            )
        elif len(ps.image_spec.strip()) < 10:
            issues.append(
                f"Primary source '{ps.title}' image_spec is too vague "
                f"({len(ps.image_spec.strip())} chars) — be more specific"
            )

    # ── Direct instruction ────────────────────────────────────────────
    for di in master.direct_instruction:
        if not di.image_spec.strip():
            issues.append(
                f"Direct instruction '{di.heading}' has empty image_spec — "
                "visual aids are required for every section"
            )
        if "?" not in di.teacher_script:
            issues.append(
                f"Direct instruction '{di.heading}' teacher_script contains no "
                "question marks — must include checks for understanding"
            )

    # ── Exit ticket stimuli ───────────────────────────────────────────
    for i, et in enumerate(master.exit_ticket):
        if len(et.stimulus.strip()) < 50:
            issues.append(
                f"Exit ticket Q{i + 1} stimulus is only "
                f"{len(et.stimulus.strip())} chars — must include substantive "
                "stimulus text (>= 50 characters)"
            )

    # ── Guided notes minimum (Jon's lessons have 8-12) ─────────────────
    if len(master.guided_notes) < 8:
        issues.append(
            f"Only {len(master.guided_notes)} guided notes — minimum 8 required "
            f"(aim for 10-12)"
        )

    # ── Differentiation ban list ──────────────────────────────────────
    for field_name in ("struggling", "advanced", "ell"):
        items = getattr(master.differentiation, field_name, [])
        for item in items:
            lower = item.lower().strip()
            for phrase in _GENERIC_DIFF_PHRASES:
                if phrase in lower:
                    issues.append(
                        f"Differentiation '{field_name}' contains generic "
                        f"phrase '{phrase}' — use SPECIFIC scaffolds"
                    )
                    break

    # ── Self-contained check ──────────────────────────────────────────
    banned_phrases = [
        "teacher will provide", "refer to textbook", "see page",
        "open your book", "use the handout", "worksheet attached",
        "see attached", "distribute the provided", "refer to class notes",
    ]
    all_text = " ".join([
        master.do_now.stimulus,
        *[di.content for di in master.direct_instruction],
        *[ps.content_text for ps in master.primary_sources],
        *[s.student_directions for s in master.stations],
    ]).lower()
    for phrase in banned_phrases:
        if phrase in all_text:
            issues.append(
                f"Lesson contains banned phrase '{phrase}' — all materials "
                "must be self-contained"
            )

    # ── Station answer keys ─────────────────────────────────────────
    for station in master.stations:
        if not station.teacher_answer_key.strip():
            issues.append(
                f"Station '{station.title}' missing teacher_answer_key — "
                "provide complete expected responses"
            )
        elif len(station.teacher_answer_key.strip()) < 20:
            issues.append(
                f"Station '{station.title}' answer key is only "
                f"{len(station.teacher_answer_key.strip())} chars — be specific"
            )

    # ── Bloom's Enforcer ─────────────────────────────────────────────
    # Research: 98% of AI lessons stuck at recall. Require cognitive progression.
    if len(master.exit_ticket) >= 3:
        levels = [
            getattr(et, "cognitive_level", "").lower()
            for et in master.exit_ticket
        ]
        has_recall = any(lv in ("recall", "remember", "identify") for lv in levels)
        has_apply = any(lv in ("application", "apply", "explain") for lv in levels)
        has_analyze = any(lv in ("analysis", "analyze", "evaluate", "create") for lv in levels)
        if not (has_recall and has_apply and has_analyze):
            issues.append(
                "Exit ticket must have Bloom's progression: recall → "
                "application → analysis. Current levels: "
                + ", ".join(levels or ["none set"])
            )

    # ── Voice & personality checks ───────────────────────────────────
    personality = getattr(master, "lesson_personality", "")
    if not personality:
        issues.append(
            "lesson_personality is empty — every lesson needs a theme "
            "or hook (e.g. 'Today we're putting Hammurabi on trial')"
        )
    first_di = master.direct_instruction[0] if master.direct_instruction else None
    if first_di:
        hook = getattr(first_di, "hook", "")
        if not hook:
            issues.append(
                "First direct_instruction section has no hook — "
                "open with an analogy, mystery, or provocative question"
            )

    # ── Creative activity enforcement ──────────────────────────────────
    creative = getattr(master, "creative_activity", None)
    if not creative or not getattr(creative, "title", ""):
        issues.append(
            "No creative_activity — every lesson needs a memorable activity "
            "(role play, debate, podcast, gallery walk, mock trial, etc.)"
        )

    # ── Jigsaw structure enforcement ─────────────────────────────────
    fmt = getattr(master, "lesson_format", "")
    jigsaw = getattr(master, "jigsaw", None)
    if fmt == "jigsaw" and not jigsaw:
        issues.append(
            "lesson_format is 'jigsaw' but jigsaw field is empty — "
            "must include expert groups, timing, and graphic organizer"
        )

    # ── Diversity & inclusion check ──────────────────────────────────
    # Scan for stereotypical or exclusionary patterns in ORIGINAL content.
    # Exclude primary source quotes — historical documents contain period
    # language by design (e.g. "all men" in the Declaration of Sentiments).
    _bias_flags = [
        "the orient", "third world", "primitive",
        "savage", "uncivilized",
    ]
    lesson_text = " ".join([
        master.objective,
        *[di.content for di in master.direct_instruction],
        *[di.teacher_script for di in master.direct_instruction],
    ]).lower()
    # Strip out quoted text (anything between single or double quotes)
    # so we don't flag historical primary source language
    import re as _re
    cleaned_text = _re.sub(r"['\"].*?['\"]", "", lesson_text)
    for flag in _bias_flags:
        if flag in cleaned_text:
            issues.append(
                f"Diversity check: lesson contains '{flag}' — consider "
                "more inclusive language"
            )

    return issues


_MAX_QUALITY_RETRIES = 2

# NOTE: lesson_plan.txt is kept for reference / backward compatibility but is
# NOT used for primary lesson generation.  All lesson generation goes through
# generate_lesson() → generate_master_content() which uses master_content.txt.
#
# ⚠️  master_content.txt IS SUPERIOR to lesson_plan.txt — it requires:
#   - Stimulus-based Do Nows (never recall)
#   - Mandatory image_spec fields for every direct-instruction section
#   - Full primary-source excerpts with scaffolding questions
#   - Guided notes with fill-in-the-blank entries
#   - Station tasks referencing primary sources
#   - Richer exit-ticket schema (StimulusQuestion with cognitive_level)
#
# If you are debugging generation quality, edit master_content.txt — changes to
# lesson_plan.txt will NOT affect the live output.
PROMPT_PATH = Path(__file__).parent / "prompts" / "lesson_plan.txt"
MASTER_PROMPT_PATH = Path(__file__).parent / "prompts" / "master_content.txt"
PROJECT_ARC_PROMPT_PATH = Path(__file__).parent / "prompts" / "project_arc.txt"


def _build_system_prompt(
    persona: TeacherPersona,
    config: AppConfig | None,
    subject: str = "",
) -> str:
    """Build the rich system prompt shared by both generation paths.

    The prompt is subject-aware: it loads the appropriate SubjectSkill
    for the lesson's subject (not just the persona's default subject),
    preventing Social Studies patterns from bleeding into Math lessons.
    """
    persona_context = persona.to_prompt_context() if persona else ""
    soul_context = ""
    try:
        import os
        data_dir = os.environ.get(
            "EDUAGENT_DATA_DIR", str(Path.home() / ".eduagent")
        )
        soul_path = Path(data_dir) / "workspace" / "soul.md"
        if soul_path.exists():
            soul_context = soul_path.read_text(encoding="utf-8")[:2000]
    except (FileNotFoundError, OSError):
        pass

    # Base prompt — subject-neutral. Specific pedagogy comes from skills.
    system_parts = [
        "You are an expert lesson plan writer who EXACTLY replicates "
        "this teacher's pedagogical fingerprint in EVERY lesson. "
        "Match their voice, tone, scaffolding patterns, activity structures, "
        "Do Now format, and signature teaching moves. If the persona describes "
        "specific techniques, use those EXACT techniques — not generic alternatives.",
    ]

    # Load subject-specific skill for THIS lesson's subject
    effective_subject = subject or (persona.subject_area if persona else "")
    if effective_subject:
        try:
            from clawed.skills import SkillLibrary
            library = SkillLibrary()
            skill = library.get(effective_subject)
            if skill:
                system_parts.append(skill.to_system_context())
        except ImportError:
            pass

    if persona_context:
        system_parts.append(persona_context)
    if soul_context:
        system_parts.append(soul_context)
    system_parts.append(
        "Respond only with valid JSON matching the specified format. "
        "Do NOT use XML tags, angle brackets, or markdown formatting "
        "in the JSON values."
    )

    # NYS Regents assessment format for Social Studies
    if (config and hasattr(config, "teacher_profile") and config.teacher_profile
            and getattr(config.teacher_profile, "state", "") == "NY"
            and "social studies" in effective_subject.lower()):
        system_parts.append(
            "NYS Regents Assessment Format Requirements:\n"
            "- Exit ticket questions MUST use Stimulus-Based Multiple "
            "Choice Question (SBMCQ) format:\n"
            "  Each question includes a stimulus (primary source excerpt, "
            "map, chart, or political cartoon) followed by 4 answer choices.\n"
            "- Include at least one Constructed Response Question (CRQ):\n"
            "  Context → Source → Questions (identify, explain, "
            "analyze/evaluate).\n"
            "- All assessment items must reference specific historical "
            "evidence from the sources provided."
        )

    return "\n\n".join(system_parts)


async def generate_master_content(
    lesson_number: int,
    unit: UnitPlan,
    persona: TeacherPersona,
    include_homework: bool = True,
    config: AppConfig | None = None,
    task_type: str = "master_content",
    state: str = "",
    teacher_materials: str = "",
    objective: str = "",
) -> MasterContent:
    """Generate a MasterContent object — single source-of-truth for a lesson.

    As of v4.10.2026.1, uses the 4-phase split pipeline by default for
    smaller per-call output tokens and much higher reliability on slow
    cloud models (GLM 5.1, etc.). Falls back to the legacy single-call
    path if any phase fails after retries.

    Set ``CLAWED_SINGLE_CALL_GEN=1`` to force legacy single-call behavior.

    All output documents (teacher plan, student packet, slides) are compiled
    as views of the returned ``MasterContent``.

    Args:
        lesson_number: Which lesson in the unit (1-indexed).
        unit: The parent unit plan for context.
        persona: Teacher persona to match.
        include_homework: Whether to generate a homework assignment.
        config: Optional app config override.
        task_type: Model-routing hint.
        state: US state code for standards lookup.
        teacher_materials: Pre-formatted teacher materials context.
        objective: Explicit lesson objective (derived from brief if empty).

    Returns:
        A fully populated MasterContent.
    """
    # v4.10.2026.1: Try the 4-phase split pipeline first
    if not os.environ.get("CLAWED_SINGLE_CALL_GEN"):
        try:
            from clawed.phases.pipeline import generate_master_content_phased
            logger.info("Using 4-phase split generation pipeline")
            master = await generate_master_content_phased(
                lesson_number=lesson_number,
                unit=unit,
                persona=persona,
                include_homework=include_homework,
                config=config,
                task_type=task_type,
                state=state,
                teacher_materials=teacher_materials,
            )
            # Run post-generation brain writes (same as single-call path)
            try:
                from clawed.brain.store import BrainStore
                from clawed.brain.writer import write_lesson_to_brain
                written = write_lesson_to_brain(
                    master=master,
                    unit_title=unit.title,
                    lesson_number=lesson_number,
                    store=BrainStore(),
                )
                logger.info(
                    "Brain updated: %d lesson, %d topic, %d concept pages",
                    len(written.get("lessons", [])),
                    len(written.get("topics", [])),
                    len(written.get("concepts", [])),
                )
            except Exception as exc:
                logger.debug("Brain writer skipped: %s", exc)
            return master
        except Exception as phased_error:
            logger.warning(
                "4-phase pipeline failed (%s: %s). Falling back to single-call.",
                type(phased_error).__name__, phased_error,
            )

    # Legacy single-call path (fallback)
    # Find the matching lesson brief from the unit plan
    lesson_brief = None
    for brief in unit.daily_lessons:
        if brief.lesson_number == lesson_number:
            lesson_brief = brief
            break

    if lesson_brief is None:
        raise ValueError(
            f"Lesson {lesson_number} not found in unit plan. "
            f"Unit has {len(unit.daily_lessons)} lessons."
        )

    # Auto-populate unit standards from teacher profile if missing
    if not unit.standards:
        try:
            config = config or AppConfig.load()
            if config.teacher_profile and config.teacher_profile.state:
                from clawed.standards import get_standards
                results = get_standards(unit.subject, unit.grade_level)
                unit.standards = [
                    f"{code}: {desc}" for code, desc, _ in results[:5]
                ]
        except ImportError:
            pass

    # Pull few-shot examples from the corpus for this subject/grade
    few_shot_context = get_few_shot_context(
        content_type="lesson_plan",
        subject=unit.subject.lower(),
        grade_level=unit.grade_level,
    )

    # Look up applicable standards for this lesson
    from clawed.standards import format_standards_for_prompt, get_standards_for_lesson

    effective_state = state
    if not effective_state and config:
        effective_state = (getattr(config, "teacher_profile", None) and config.teacher_profile.state) or ""
    standards_list = get_standards_for_lesson(
        subject=unit.subject,
        grade=unit.grade_level,
        state=effective_state,
        topic=lesson_brief.topic,
    )
    standards_text = format_standards_for_prompt(standards_list)

    # Derive objective from lesson brief if not explicitly provided
    effective_objective = objective or getattr(lesson_brief, "description", "")

    prompt_template = MASTER_PROMPT_PATH.read_text(encoding="utf-8")
    prompt = (
        prompt_template
        .replace("{unit_title}", unit.title)
        .replace("{unit_overview}", unit.overview[:1500])
        .replace("{subject}", unit.subject)
        .replace("{grade_level}", unit.grade_level)
        .replace("{topic}", lesson_brief.topic)
        .replace("{objective}", effective_objective)
        .replace("{lesson_number}", str(lesson_number))
        .replace("{total_lessons}", str(len(unit.daily_lessons)))
        .replace("{duration_minutes}", "45")
        .replace("{standards}", standards_text)
        .replace("{few_shot_context}", few_shot_context)
        .replace("{teacher_materials}", teacher_materials)
        .replace("{standards_framework}", (
            config.teacher_profile.standards_framework
            if config and config.teacher_profile
            else "state standards"
        ))
        .replace("{state}", (
            config.teacher_profile.state
            if config and config.teacher_profile
            else ""
        ))
    )

    # Inject classroom profile context into system prompt
    try:
        from clawed.classroom_profile import profile_to_prompt_context
        classroom_ctx = profile_to_prompt_context()
        if classroom_ctx:
            prompt = classroom_ctx + "\n\n" + prompt
    except ImportError:
        pass

    # Inject knowledge graph connections into prompt
    try:
        from clawed.agent_core.identity import get_teacher_id
        from clawed.lesson_connections import inject_connections_into_prompt
        _tid = get_teacher_id()
        kg_ctx = inject_connections_into_prompt(
            lesson_brief.topic,
            teacher_id=_tid,
        )
        if kg_ctx:
            prompt = kg_ctx + "\n\n" + prompt
    except ImportError:
        pass

    # v4.10: Brain-first lookup — inject brain context before generation
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
        if brain_prompt:
            prompt = brain_prompt + "\n\n" + prompt
            logger.info(
                "Brain context injected: %d students, %d originals, %d past lessons",
                len(brain_ctx_obj.relevant_students),
                len(brain_ctx_obj.related_originals),
                len(brain_ctx_obj.past_lesson_results),
            )
    except Exception as exc:
        logger.debug("Brain context lookup skipped: %s", exc)

    system = _build_system_prompt(persona, config, subject=unit.subject)

    if task_type and config:
        config = route_model(task_type, config)
    client = LLMClient(config)

    master = await client.safe_generate_json(
        prompt=prompt,
        model_class=MasterContent,
        system=system,
        temperature=0.6,
        max_tokens=12000,
    )

    # v4.10: Attach brain context and citations to the generated master
    if brain_ctx_obj is not None:
        master.brain_context = brain_ctx_obj
        master.source_attributions = list(brain_ctx_obj.citations)

    # ── Quality gate with auto-retry ──────────────────────────────────
    for attempt in range(_MAX_QUALITY_RETRIES):
        issues = _validate_quality(master)
        if not issues:
            break
        logger.warning(
            "Quality gate failed (attempt %d/%d) with %d issues:\n%s",
            attempt + 1,
            _MAX_QUALITY_RETRIES,
            len(issues),
            "\n".join(f"  - {i}" for i in issues),
        )
        retry_feedback = (
            "\n\n---\n## QUALITY FEEDBACK — FIX THESE ISSUES\n\n"
            "Your previous attempt had these problems:\n"
            + "\n".join(f"- {i}" for i in issues)
            + "\n\nFix ALL of the above in your next attempt. "
            "Do NOT repeat the same mistakes."
        )
        master = await client.safe_generate_json(
            prompt=prompt + retry_feedback,
            model_class=MasterContent,
            system=system,
            temperature=0.5,  # slightly lower for more compliance
            max_tokens=12000,
        )

    # Log any remaining issues after retries (deliver with warnings)
    remaining = _validate_quality(master)
    if remaining:
        logger.warning(
            "Delivering lesson with %d quality warnings after %d retries:\n%s",
            len(remaining),
            _MAX_QUALITY_RETRIES,
            "\n".join(f"  - {i}" for i in remaining),
        )

    # ── Stage 2: LLM-based critic (Teaching Constitution) ─────────
    # Separate model call reviews the lesson against pedagogical principles.
    # Non-blocking — if the critic fails, the lesson still ships.
    try:
        critic_path = Path(__file__).parent / "prompts" / "teaching_constitution.txt"
        if critic_path.exists():
            critic_prompt = critic_path.read_text(encoding="utf-8")
            lesson_json = master.model_dump_json(indent=2)
            # Truncate to avoid token limits
            if len(lesson_json) > 6000:
                lesson_json = lesson_json[:6000] + "\n... (truncated)"

            critic_response = await client.generate(
                prompt=(
                    f"Review this lesson plan:\n\n{lesson_json}\n\n"
                    "Apply the Teaching Constitution above."
                ),
                system=critic_prompt,
                temperature=0.2,
                max_tokens=500,
            )
            if "NEEDS_REVISION" in critic_response:
                logger.info("Teaching Constitution critic flagged issues:\n%s", critic_response[:500])
    except Exception as exc:
        logger.debug("Teaching Constitution critic skipped: %s", exc)

    # v4.10: Post-generation brain writes — capture learnings
    try:
        from clawed.brain.store import BrainStore
        from clawed.brain.writer import write_lesson_to_brain
        written = write_lesson_to_brain(
            master=master,
            unit_title=unit.title,
            lesson_number=lesson_number,
            store=BrainStore(),
        )
        logger.info(
            "Brain updated: %d lesson, %d topic, %d concept pages",
            len(written.get("lessons", [])),
            len(written.get("topics", [])),
            len(written.get("concepts", [])),
        )
    except Exception as exc:
        logger.debug("Brain writer skipped: %s", exc)

    return master


async def generate_and_compile(
    lesson_number: int,
    unit: UnitPlan,
    persona: TeacherPersona,
    output_dir: str | Path,
    include_homework: bool = True,
    config: AppConfig | None = None,
    state: str = "",
    teacher_materials: str = "",
    fetch_images: bool = True,
) -> dict:
    """Generate a lesson AND compile all output files in one call.

    This is the recommended entry point for batch generation. It:
    1. Generates MasterContent via LLM
    2. Fetches images from teacher assets + web (if fetch_images=True)
    3. Compiles teacher DOCX, student DOCX, and classroom PPTX deck
    4. Records the generation in state.db

    Returns a dict with keys: master, teacher_path, student_path,
    slides_path (may be None if PPTX compile failed), images.
    """
    from pathlib import Path as _Path

    from clawed.compile_student import compile_student_view
    from clawed.compile_teacher import compile_teacher_view

    output_dir = _Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Step 1: Generate MasterContent
    master = await generate_master_content(
        lesson_number=lesson_number,
        unit=unit,
        persona=persona,
        include_homework=include_homework,
        config=config,
        state=state,
        teacher_materials=teacher_materials,
    )

    # Step 2: Fetch images (teacher assets first, then web)
    images: dict[str, Path] = {}
    if fetch_images:
        try:
            from clawed.agent_core.identity import get_teacher_id
            from clawed.image_pipeline import fetch_all_images

            cfg = config or AppConfig.load()
            tid = get_teacher_id()
            images = await fetch_all_images(master, cfg, teacher_id=tid)
            logger.info("Images resolved: %d", len(images))
        except Exception as exc:
            logger.debug("Image fetching skipped: %s", exc)

    # Step 3: Compile DOCX outputs
    teacher_path = await compile_teacher_view(master, images, output_dir)
    student_path = await compile_student_view(master, images, output_dir)

    # Step 3b: Compile classroom-ready PPTX deck (non-fatal if it fails)
    slides_path: Path | None = None
    try:
        from clawed.compile_slides import compile_slides

        slides_path = await compile_slides(master, images, output_dir)
        logger.info("PPTX slides compiled: %s", slides_path)
    except Exception as exc:
        logger.warning("PPTX compile failed, skipping: %s", exc)

    # Step 4: Record in state DB
    try:
        _record_generation(master, unit, lesson_number)
    except Exception as exc:
        logger.debug("State recording failed: %s", exc)

    return {
        "master": master,
        "teacher_path": teacher_path,
        "student_path": student_path,
        "slides_path": slides_path,
        "images": images,
    }


def _record_generation(
    master: MasterContent,
    unit: UnitPlan,
    lesson_number: int,
) -> None:
    """Record a generated lesson in state.db for tracking.

    v4.11.2026 fix: the previous INSERT referenced columns that do not
    exist in the ``generated_lessons`` schema (subject, grade_level, topic,
    unit_title) and omitted the NOT NULL columns (id, teacher_id,
    lesson_json). Every batch lesson silently failed to record. This
    rewrite uses the real schema defined in ``clawed/state.py:95``.
    """
    import hashlib
    import sqlite3
    import uuid

    from clawed.config import _BASE_DIR

    db_path = _BASE_DIR / "state.db"
    if not db_path.exists():
        return

    # Resolve teacher_id from the identity module; fall back to "default"
    # so this function never raises on a fresh install.
    try:
        from clawed.agent_core.identity import get_teacher_id
        teacher_id = get_teacher_id() or "default"
    except ImportError:
        teacher_id = "default"

    # Synthesize a stable unit_id from the unit title so repeated
    # generations of the same unit share the same parent row.
    unit_id = hashlib.md5(
        f"{teacher_id}:{unit.title}".encode()
    ).hexdigest()[:16]

    lesson_id = str(uuid.uuid4())

    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO generated_lessons "
            "(id, unit_id, teacher_id, lesson_number, title, lesson_json) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                lesson_id,
                unit_id,
                teacher_id,
                lesson_number,
                master.title,
                master.model_dump_json(),
            ),
        )


async def generate_lesson(
    lesson_number: int,
    unit: UnitPlan,
    persona: TeacherPersona,
    include_homework: bool = True,
    config: AppConfig | None = None,
    task_type: str = "master_content",
    state: str = "",
    teacher_materials: str = "",
) -> DailyLesson:
    """Generate a complete daily lesson plan for a specific lesson in a unit.

    Internally generates a ``MasterContent`` object and converts it to a
    ``DailyLesson`` for backward compatibility with all existing callers.

    Args:
        lesson_number: Which lesson in the unit (1-indexed).
        unit: The parent unit plan for context.
        persona: Teacher persona to match.
        include_homework: Whether to generate a homework assignment.
        config: Optional app config override.
        task_type: Model-routing hint.
        state: US state code for standards lookup.
        teacher_materials: Pre-formatted teacher materials context.

    Returns:
        A fully populated DailyLesson.
    """
    master = await generate_master_content(
        lesson_number=lesson_number,
        unit=unit,
        persona=persona,
        include_homework=include_homework,
        config=config,
        task_type=task_type,
        state=state,
        teacher_materials=teacher_materials,
    )
    daily = master.to_daily_lesson()
    daily.lesson_number = lesson_number
    return daily


async def generate_all_lessons(
    unit: UnitPlan,
    persona: TeacherPersona,
    include_homework: bool = True,
    config: AppConfig | None = None,
    teacher_materials: str = "",
) -> list[DailyLesson]:
    """Generate lesson plans for every lesson in a unit sequentially.

    Lessons are generated in order so that each lesson receives context about
    what came before — vocabulary already introduced, sources already used,
    and objectives already covered.  This prevents Day 3 from re-explaining
    Day 1 vocabulary and lets the unit build progressively.
    """
    lessons: list[DailyLesson] = []
    prior_context = ""

    for brief in unit.daily_lessons:
        # Build cumulative context from prior lessons
        materials_with_context = teacher_materials
        if prior_context:
            materials_with_context = (
                "## Prior Lessons in This Unit\n"
                "The following lessons have already been taught. Build on this "
                "foundation — do NOT re-introduce vocabulary or sources that "
                "students have already worked with. Reference prior learning "
                "where appropriate.\n\n"
                + prior_context
                + "\n---\n\n"
                + teacher_materials
            )

        master = await generate_master_content(
            lesson_number=brief.lesson_number,
            unit=unit,
            persona=persona,
            include_homework=include_homework,
            config=config,
            teacher_materials=materials_with_context,
        )

        daily = master.to_daily_lesson()
        daily.lesson_number = brief.lesson_number
        lessons.append(daily)

        # Accumulate context for the next lesson
        vocab_terms = ", ".join(v.term for v in master.vocabulary) if master.vocabulary else "none"
        source_titles = ", ".join(ps.title for ps in master.primary_sources) if master.primary_sources else "none"
        prior_context += (
            f"### Lesson {brief.lesson_number}: {master.title}\n"
            f"- Objective: {master.objective}\n"
            f"- Vocabulary introduced: {vocab_terms}\n"
            f"- Primary sources used: {source_titles}\n"
            f"- Format: {master.lesson_format}\n\n"
        )

    return lessons


async def generate_project_arc(
    unit: UnitPlan,
    persona: TeacherPersona,
    config: AppConfig | None = None,
    duration_days: int = 5,
    teacher_materials: str = "",
) -> ProjectArc:
    """Generate a multi-day project arc for the culminating week of a unit.

    Returns a ProjectArc with phases, rubric, debate prep, and culminating
    performance. Modeled on master teacher project packets (choice boards,
    curated databases, 4-point rubrics, gallery walks, debates).
    """

    topics_covered = ", ".join(
        brief.topic for brief in unit.daily_lessons
    ) if unit.daily_lessons else unit.topic

    essential_question = (
        unit.essential_questions[0]
        if unit.essential_questions
        else f"How did {unit.topic} shape the world we live in today?"
    )

    prompt_template = PROJECT_ARC_PROMPT_PATH.read_text(encoding="utf-8")
    prompt = (
        prompt_template
        .replace("{unit_title}", unit.title)
        .replace("{subject}", unit.subject)
        .replace("{grade_level}", unit.grade_level)
        .replace("{duration_days}", str(duration_days))
        .replace("{essential_question}", essential_question)
        .replace("{topics_covered}", topics_covered)
        .replace("{teacher_materials}", teacher_materials)
    )

    system = _build_system_prompt(persona, config, subject=unit.subject)

    cfg = config or AppConfig.load()
    cfg = route_model("master_content", cfg)
    client = LLMClient(cfg)

    return await client.safe_generate_json(
        prompt=prompt,
        model_class=ProjectArc,
        system=system,
        temperature=0.7,
        max_tokens=8000,
    )


def save_lesson(lesson: DailyLesson, output_dir: Path) -> Path:
    """Save a lesson plan to disk as JSON."""
    from clawed.io import write_text

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"lesson_{lesson.lesson_number:02d}.json"
    write_text(path, lesson.model_dump_json(indent=2))
    return path


def load_lesson(path: Path) -> DailyLesson:
    """Load a lesson plan from a JSON file."""
    if not path.exists():
        raise FileNotFoundError(f"Lesson file not found: {path}")
    return DailyLesson.model_validate_json(path.read_text(encoding="utf-8"))
