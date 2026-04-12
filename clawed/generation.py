"""Generation service layer — LLM-calling functions for lessons, units, materials, etc.

Extracted from hermes_plugin.py so that gateway handlers can call these
directly without going through the hermes_plugin dispatch loop.

Every function takes a TeacherSession (or the pieces it needs) and returns a
plain string.  No routing, no intent parsing — that belongs in the gateway.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from clawed.model_router import route as route_model
from clawed.models import AppConfig, TeacherPersona
from clawed.router import ParsedIntent
from clawed.state import TeacherSession
from clawed.student_bot import StudentBot

logger = logging.getLogger(__name__)


# ── Response formatters ──────────────────────────────────────────────────────


def _fmt_unit_summary(unit) -> str:
    """Format a unit plan for Telegram (no markdown tables)."""
    lines = [
        f"\U0001f4da *{unit.title}*",
        f"Grade {unit.grade_level} {unit.subject} | {unit.duration_weeks} weeks | {len(unit.daily_lessons)} lessons",
        "",
        "\U0001f4cc *Essential Questions*",
    ]
    for q in unit.essential_questions[:3]:
        lines.append(f"\u2022 {q}")
    lines.append("")
    lines.append("\U0001f4c5 *Lesson Sequence*")
    for lesson in unit.daily_lessons[:5]:
        lines.append(f"  L{lesson.lesson_number}: {lesson.topic}")
    if len(unit.daily_lessons) > 5:
        lines.append(f"  ... +{len(unit.daily_lessons) - 5} more lessons")
    lines.append("")
    lines.append("_Reply with 'generate lesson 1' to get the full first lesson plan, or 'export PDF' to download._")
    return "\n".join(lines)


def _fmt_lesson_summary(lesson) -> str:
    """Format a lesson plan for Telegram."""
    lines = [
        f"\U0001f4dd *Lesson {lesson.lesson_number}: {lesson.title}*",
        "",
        f"\U0001f3af *Objective:* {lesson.objective}",
        "",
        f"\U0001f514 *Do-Now (5 min):* {lesson.do_now[:200]}...",
        "",
        "\U0001f4cb *Structure:*",
        f"\u2022 Direct Instruction ({lesson.time_estimates.get('direct_instruction', 20)} min)",
        f"\u2022 Guided Practice ({lesson.time_estimates.get('guided_practice', 15)} min)",
        f"\u2022 Independent Work ({lesson.time_estimates.get('independent_work', 10)} min)",
        f"\u2022 Exit Ticket ({len(lesson.exit_ticket)} questions)",
        "",
    ]
    if lesson.differentiation.struggling:
        lines.append("\u267f *Differentiation included* (struggling/advanced/ELL)")
    if lesson.homework:
        lines.append("\U0001f4da *Homework:* Yes")
    lines.append("")
    lines.append("_Reply 'generate materials' for the worksheet + assessment, or 'export PDF' to download._")
    return "\n".join(lines)


def _fmt_persona(persona: TeacherPersona) -> str:
    """Format a teacher persona for Telegram."""
    lines = [
        "\U0001f469\u200d\U0001f3eb *Your Teaching Profile*",
        "",
        f"\u2022 Style: {persona.teaching_style.value.replace('_', ' ').title()}",
        f"\u2022 Tone: {persona.tone}",
        f"\u2022 Format: {persona.preferred_lesson_format}",
    ]
    if persona.structural_preferences:
        lines.append(f"\u2022 Preferences: {', '.join(persona.structural_preferences[:4])}")
    if persona.subject_area:
        lines.append(f"\u2022 Subject: {persona.subject_area}")
    if persona.grade_levels:
        lines.append(f"\u2022 Grades: {', '.join(persona.grade_levels)}")
    lines.append("")
    lines.append("_Everything I generate will match this profile. Reply 'update my profile' to change anything._")
    return "\n".join(lines)


# ── Unit generation ──────────────────────────────────────────────────────────


async def generate_unit(parsed: ParsedIntent, session: TeacherSession) -> str:
    """Generate a multi-week unit plan and return formatted text."""
    from clawed.planner import plan_unit

    topic = parsed.topic or "the current topic"
    has_grades = session.persona and session.persona.grade_levels
    grade = parsed.grade or (session.persona.grade_levels[0] if has_grades else "8")
    subject = (session.persona.subject_area if session.persona and session.persona.subject_area else "General")
    weeks = parsed.weeks or 2
    persona = session.persona or TeacherPersona()

    try:
        config = route_model("unit_plan", AppConfig.load())
        unit = await plan_unit(
            subject=subject,
            grade_level=grade,
            topic=topic,
            duration_weeks=weeks,
            persona=persona,
            config=config,
        )
        session.save_unit(unit)
        return _fmt_unit_summary(unit)
    except (ConnectionError, TimeoutError) as e:
        logger.error("Network error generating unit plan: %s", e)
        return (
            "Couldn't reach the LLM provider. Check your internet connection "
            "and API key (`/setup` to check)."
        )
    except ValueError as e:
        logger.error("Validation error generating unit plan: %s", e)
        return f"The unit plan didn't pass validation: {str(e)[:200]}"
    except Exception as e:
        logger.exception("Unexpected error generating unit plan")
        return (
            f"Ran into an issue generating the unit plan: {str(e)[:200]}\n\n"
            "Make sure your API key is configured (`/setup` to check)."
        )


# ── Lesson generation ────────────────────────────────────────────────────────


async def generate_lesson(parsed: ParsedIntent, session: TeacherSession) -> str:
    """Generate a single lesson plan and return formatted text."""
    from clawed.lesson import generate_lesson as _gen_lesson
    from clawed.models import LessonBrief, UnitPlan

    # If we have a current unit, generate the next lesson in sequence
    if session.current_unit:
        unit = session.current_unit
        # Figure out which lesson number was requested
        lesson_num = 1
        if parsed.raw:
            m = re.search(r"lesson\s+(\d+)", parsed.raw, re.IGNORECASE)
            if m:
                lesson_num = int(m.group(1))
    else:
        # Create a minimal unit context for a standalone lesson
        topic = parsed.topic or "today's lesson"
        grade = parsed.grade or "8"
        subject = (session.persona.subject_area if session.persona else "General")
        unit = UnitPlan(
            title=f"{topic} Unit",
            subject=subject,
            grade_level=grade,
            topic=topic,
            duration_weeks=1,
            overview=f"A lesson on {topic}.",
            daily_lessons=[LessonBrief(lesson_number=1, topic=topic, description=f"Introduction to {topic}")],
        )
        lesson_num = 1

    persona = session.persona or TeacherPersona()

    # Resolve teacher's state for standards alignment
    teacher_state = ""
    try:
        cfg = AppConfig.load()
        teacher_state = cfg.teacher_profile.state or ""
    except Exception as exc:
        logger.debug("Could not load teacher state for standards: %s", exc)

    try:
        config = route_model("lesson_plan", AppConfig.load())
        lesson = await _gen_lesson(
            lesson_number=lesson_num,
            unit=unit,
            persona=persona,
            config=config,
            state=teacher_state,
        )
        lesson_id = session.save_lesson(lesson)
        session.config["last_lesson_id"] = lesson_id
        return _fmt_lesson_summary(lesson)
    except (ConnectionError, TimeoutError) as e:
        logger.error("Network error generating lesson: %s", e)
        return "Couldn't reach the LLM provider. Check your connection and API key (`/setup`)."
    except ValueError as e:
        logger.error("Validation error generating lesson: %s", e)
        return f"The lesson didn't pass validation: {str(e)[:200]}"
    except Exception as e:
        logger.exception("Unexpected error generating lesson")
        return f"Had trouble generating the lesson: {str(e)[:200]}"


# ── Materials generation ─────────────────────────────────────────────────────


async def generate_materials(parsed: ParsedIntent, session: TeacherSession) -> str:
    """Generate supplementary materials for the current lesson."""
    from clawed.materials import generate_materials as _gen_materials

    if not session.current_lesson:
        return "Which lesson should I make materials for? Generate a lesson plan first, or tell me the topic."

    lesson = session.current_lesson
    persona = session.persona or TeacherPersona()

    try:
        config = route_model("materials", AppConfig.load())
        materials = await _gen_materials(lesson=lesson, persona=persona, config=config)
        lines = [
            f"\U0001f4cb *Materials for: {lesson.title}*",
            "",
            f"\u2705 Worksheet: {len(materials.worksheet_items)} questions",
            f"\u2705 Assessment: {len(materials.assessment_questions)} questions",
        ]
        if materials.rubric:
            lines.append(f"\u2705 Rubric: {len(materials.rubric)} criteria")
        if materials.slide_outline:
            lines.append(f"\u2705 Slide outline: {len(materials.slide_outline)} slides")
        if materials.iep_notes:
            lines.append(f"\u2705 Differentiation notes: {len(materials.iep_notes)} accommodations")
        lines.append("")
        lines.append("_Reply 'export PDF' to download everything as a ready-to-print packet._")
        return "\n".join(lines)
    except (ConnectionError, TimeoutError) as e:
        logger.error("Network error generating materials: %s", e)
        return "Couldn't reach the LLM provider. Check your connection."
    except Exception as e:
        logger.exception("Unexpected error generating materials")
        return f"Trouble generating materials: {str(e)[:200]}"


# ── Assessment generation ────────────────────────────────────────────────────


async def generate_assessment(parsed: ParsedIntent, session: TeacherSession) -> str:
    """Return assessment type menu (actual generation happens on follow-up)."""
    topic = parsed.topic or (session.current_unit.topic if session.current_unit else "the current topic")
    return (
        f"\U0001f4dd Creating assessment for: *{topic}*\n\n"
        "What type?\n"
        "\u2022 'multiple choice' \u2014 10-15 MC questions\n"
        "\u2022 'short answer' \u2014 5-8 written response questions\n"
        "\u2022 'mixed' \u2014 combination of MC, short answer, and 1 essay\n"
        "\u2022 'exit ticket' \u2014 3 quick questions for end of class"
    )


# ── Bell ringer generation ───────────────────────────────────────────────────

# Prompt file for bell ringers / Do Nows.  We use lesson_plan.txt because it
# contains the richest Do Now specification (stimulus-based, never recall).
# A dedicated do_now.txt could replace this if created in the future.
_BELLRINGER_PROMPT_PATH = Path(__file__).parent / "prompts" / "lesson_plan.txt"


async def generate_bellringer(parsed: ParsedIntent, session: TeacherSession) -> str:
    """Generate 3 bell ringer / Do-Now prompts that sound like the specific teacher.

    Loads the full lesson_plan.txt prompt file for Do Now requirements and injects
    the complete teacher persona including do_now_style, voice_examples, and
    activity_patterns so the output matches this teacher's fingerprint, not a
    generic template.
    """
    from clawed.llm import LLMClient

    topic = parsed.topic or (session.current_unit.topic if session.current_unit else "today's topic")
    persona = session.persona or TeacherPersona()
    config = route_model("bellringer", AppConfig.load())

    # Pull the full persona context — critically includes do_now_style, voice_examples,
    # activity_patterns, and scaffolding_moves so Do Nows sound like THIS teacher.
    persona_context = persona.to_prompt_context()

    # Extract specific fingerprint fields explicitly for the system prompt so the
    # model cannot ignore them even if they appear later in a long context.
    do_now_style_hint = (
        f"\n\nDo Now Style for this teacher: {persona.do_now_style}"
        if persona.do_now_style else ""
    )
    activity_hint = (
        "\n\nThis teacher's activity patterns:\n" + "\n".join(f"- {p}" for p in persona.activity_patterns)
        if persona.activity_patterns else ""
    )
    voice_hint = (
        "\n\nVoice examples — write Do Nows that match this voice:\n"
        + "\n".join(f'  "{ex}"' for ex in persona.voice_examples[:3])
        if persona.voice_examples else ""
    )

    grade = persona.grade_levels[0] if persona.grade_levels else "8"
    subject = persona.subject_area or "General"

    system = (
        "You are an expert teacher who writes Do Now / bell ringer activities that "
        "exactly replicate a specific teacher's pedagogical fingerprint.\n\n"
        "CRITICAL RULES from lesson_plan.txt:\n"
        "- Do Nows must be STIMULUS-BASED — never a content recall question.\n"
        "- Use analogy, scenario, provocative question, or real-world hook.\n"
        "- BAD: 'What do you know about the Civil War?'\n"
        "- GOOD: 'Imagine two people who used to be business partners have a "
        "bitter falling-out. One takes half the inventory and leaves. The other "
        "says that inventory belongs to the whole company. What should happen? "
        "(3 min)' [metaphor for secession]\n"
        "- Students must be able to begin independently the moment they sit down.\n"
        "- Each Do Now takes 3-5 minutes — 1 or 2 focused questions max.\n\n"
        f"{persona_context}"
        f"{do_now_style_hint}"
        f"{activity_hint}"
        f"{voice_hint}"
    )

    prompt = (
        f"Generate 3 different Do Now / bell ringer options for a {subject} lesson "
        f"on '{topic}' for grade {grade}.\n\n"
        "Each option must:\n"
        "1. Be a complete, self-contained prompt a student can start immediately.\n"
        "2. Use this teacher's specific Do Now style (scenario, analogy, or "
        "provocative question — never recall).\n"
        "3. Match the teacher's voice, vocabulary, and tone exactly.\n"
        "4. Take 3-5 minutes.\n\n"
        "Format as a numbered list with a brief label (e.g., 'Option 1 — Analogy:') "
        "followed by the full student-facing prompt. No meta-commentary."
    )

    try:
        client = LLMClient(config)
        response = await client.generate(
            prompt=prompt,
            system=system,
            temperature=0.7,
            max_tokens=600,
        )
        return f"\U0001f514 *Bell Ringer Options for {topic}:*\n\n{response}"
    except (ConnectionError, TimeoutError) as e:
        logger.error("Network error generating bell ringers: %s", e)
        return "Couldn't reach the LLM provider. Check your connection."
    except Exception as e:
        logger.exception("Unexpected error generating bell ringers")
        return f"Trouble generating bell ringers: {str(e)[:200]}"


# ── Differentiation generation ───────────────────────────────────────────────

# Path to the dedicated differentiation prompt file.
_DIFFERENTIATION_PROMPT_PATH = Path(__file__).parent / "prompts" / "differentiation.txt"


async def generate_differentiation(parsed: ParsedIntent, session: TeacherSession) -> str:
    """Generate differentiation strategies for the current lesson.

    Loads differentiation.txt and passes the full teacher persona — including
    scaffolding_moves — so accommodations reflect HOW this teacher already
    scaffolds, not generic advice.

    Schema fix: differentiation.txt returns a flat string array.  We parse it
    and bucket items into {struggling, advanced, ell} to match the
    DifferentiationNotes model expected by lesson_plan.txt / DailyLesson.
    Items are categorised by prefix keyword (IEP → struggling, ELL → ell,
    Advanced/Gifted → advanced, remainder → struggling as a safe default).
    The formatted string returned to Telegram groups them for readability.
    """
    lesson = session.current_lesson
    if not lesson:
        topic = parsed.topic or "the current lesson"
        return (
            f"Tell me more about the lesson on *{topic}* first, or generate a"
            " lesson plan and I'll add differentiation notes to it."
        )

    from clawed.llm import LLMClient

    persona = session.persona or TeacherPersona()
    config = route_model("differentiation", AppConfig.load())
    client = LLMClient(config)

    # Build full persona context — scaffolding_moves is the critical field here
    # because it tells the model which tools (T-charts, sentence frames, writing
    # frames, etc.) this teacher ALREADY uses, so accommodations extend rather
    # than replace their practice.
    persona_context = persona.to_prompt_context()
    scaffolding_hint = (
        "\n\nThis teacher's scaffolding moves (accommodations MUST build on these):\n"
        + "\n".join(f"- {m}" for m in persona.scaffolding_moves)
        if persona.scaffolding_moves else ""
    )

    # Load differentiation.txt prompt template
    prompt_template = _DIFFERENTIATION_PROMPT_PATH.read_text(encoding="utf-8")

    # Derive lesson activity summary for the template
    activities_summary = getattr(lesson, "guided_practice", "") or getattr(lesson, "direct_instruction", "") or ""
    if isinstance(activities_summary, list):
        activities_summary = " ".join(str(a) for a in activities_summary)[:500]
    else:
        activities_summary = str(activities_summary)[:500]

    grade = persona.grade_levels[0] if persona.grade_levels else getattr(lesson, "grade_level", "8")
    subject = persona.subject_area or "General"

    prompt = (
        prompt_template
        .replace("{persona}", persona_context + scaffolding_hint)
        .replace("{lesson_title}", lesson.title)
        .replace("{objective}", lesson.objective)
        .replace("{grade_level}", str(grade))
        .replace("{subject}", subject)
        .replace("{lesson_activities}", activities_summary or "See lesson plan.")
    )

    system = (
        "You are an expert in differentiated instruction and inclusive education. "
        "You write accommodations that are specific to THIS lesson and THIS teacher's "
        "existing scaffolding practice.\n\n"
        f"{persona_context}"
        f"{scaffolding_hint}"
    )

    try:
        import json as _json

        raw = await client.generate(
            prompt=prompt,
            system=system,
            temperature=0.6,
            max_tokens=1200,
        )

        # --- Schema fix ---------------------------------------------------
        # differentiation.txt returns a flat JSON string array.
        # DailyLesson.differentiation expects {struggling: [], advanced: [], ell: []}.
        # Parse and bucket by prefix keyword so the lesson object stays consistent.
        items: list[str] = []
        try:
            # Strip any markdown fencing the model may have added
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = "\n".join(cleaned.split("\n")[1:])
                cleaned = cleaned.rstrip("`").strip()
            items = _json.loads(cleaned)
            if not isinstance(items, list):
                items = []
        except Exception:
            items = []

        struggling: list[str] = []
        advanced: list[str] = []
        ell: list[str] = []
        for item in items:
            low = item.lower()
            if low.startswith("ell") or "english language learner" in low:
                ell.append(item)
            elif low.startswith("advanced") or low.startswith("gifted") or "enrichment" in low[:30]:
                advanced.append(item)
            else:
                # IEP, UDL, SEL, and untagged items default to struggling bucket
                struggling.append(item)

        # Update the lesson's differentiation object in-place if it exists
        if hasattr(lesson, "differentiation") and lesson.differentiation is not None:
            if struggling:
                lesson.differentiation.struggling = struggling
            if advanced:
                lesson.differentiation.advanced = advanced
            if ell:
                lesson.differentiation.ell = ell

        # Build a readable Telegram response grouped by category
        lines = [f"\u267f *Differentiation for {lesson.title}:*", ""]
        if struggling:
            lines.append("*Struggling Learners / IEP:*")
            for s in struggling:
                lines.append(f"\u2022 {s}")
            lines.append("")
        if advanced:
            lines.append("*Advanced / Gifted:*")
            for a in advanced:
                lines.append(f"\u2022 {a}")
            lines.append("")
        if ell:
            lines.append("*ELL / Language Supports:*")
            for e in ell:
                lines.append(f"\u2022 {e}")
            lines.append("")
        if not lines[2:]:
            # Fallback: model returned prose rather than JSON — show raw
            lines.append(raw)

        return "\n".join(lines)
    except (ConnectionError, TimeoutError) as e:
        logger.error("Network error generating differentiation: %s", e)
        return "Couldn't reach the LLM provider. Check your connection."
    except Exception as e:
        logger.exception("Unexpected error generating differentiation")
        return f"Trouble generating differentiation notes: {str(e)[:200]}"


# ── Web search ───────────────────────────────────────────────────────────────


async def handle_web_search(parsed: ParsedIntent, session: TeacherSession) -> str:
    """Search the web for teaching resources."""
    try:
        from clawed.search import search_for_teacher
        results = await search_for_teacher(parsed.raw, session.persona)
        return results
    except Exception:
        return (
            "I'd like to search the web for that, but web search isn't configured yet.\n\n"
            "Set your Tavily API key to enable search:\n"
            "`/config tavily YOUR_KEY`\n\n"
            "Or I can generate content without current examples \u2014 just ask!"
        )


# ── Standards search ─────────────────────────────────────────────────────────


async def handle_search_standards(parsed: ParsedIntent, session: TeacherSession) -> str:
    """Look up educational standards."""
    from clawed.standards import get_standards

    has_grades = session.persona and session.persona.grade_levels
    grade = parsed.grade or (session.persona.grade_levels[0] if has_grades else None)
    subject = session.persona.subject_area if session.persona else None

    if not grade or not subject:
        return "Which grade and subject? (e.g., 'standards for 8th grade science')"

    standards = get_standards(grade=grade, subject=subject)
    if not standards:
        return (
            f"I don't have standards loaded for {subject} grade {grade}."
            f" Try 'search for NGSS {subject} grade {grade}'"
            " and I'll look it up online."
        )

    lines = [f"\U0001f4cb *Standards: Grade {grade} {subject}*", ""]
    for s in standards[:8]:
        lines.append(f"\u2022 *{s.get('code', '')}* \u2014 {s.get('description', '')[:100]}")
    if len(standards) > 8:
        lines.append(f"_... and {len(standards) - 8} more_")
    return "\n".join(lines)


# ── Export ───────────────────────────────────────────────────────────────────


async def handle_export(parsed: ParsedIntent, session: TeacherSession, fmt: str) -> str:
    """Return export instructions (actual export handled by ExportHandler)."""
    if not session.current_lesson:
        return "Generate a lesson first, then I can export it."
    return (
        f"\U0001f4c4 Export as *{fmt.upper()}*\n\n"
        "Export functionality is available via the web interface.\n"
        "Run `clawed serve` and visit http://localhost:8000 to download your materials."
    )


# ── Student bot ──────────────────────────────────────────────────────────────


async def handle_share_students(parsed: ParsedIntent, session: TeacherSession) -> str:
    """Return student chatbot sharing info."""
    if not session.current_lesson:
        return "Generate a lesson first, then I can create a student chatbot link for it."
    return (
        "\U0001f393 *Student Chatbot*\n\n"
        "Once you run `clawed serve`, your students can access a chatbot"
        " that answers questions about this lesson in your teaching voice.\n\n"
        "The embed code will be available at: http://localhost:8000"
    )


async def handle_start_student_bot(parsed: ParsedIntent, session: TeacherSession) -> str:
    """Activate student bot for the current lesson, returns class code."""
    if not session.current_lesson:
        return (
            "Generate a lesson first, then I can activate the student bot for it.\n\n"
            "Try: 'write a lesson on photosynthesis'"
        )

    bot = StudentBot()

    # Check if teacher already has a class code in config
    class_code = session.config.get("class_code")
    if not class_code:
        class_code = bot.create_class(session.teacher_id)
        session.config["class_code"] = class_code
        session.save()

    # Set the active lesson
    lesson_json = session.current_lesson.model_dump_json()
    lesson_id = session.current_lesson.title
    await bot.set_active_lesson(class_code, lesson_id, session.teacher_id, lesson_json)

    return (
        f"\U0001f393 *Student Bot Activated!*\n\n"
        f"\U0001f4cb Class Code: `{class_code}`\n"
        f"\U0001f4dd Active Lesson: {session.current_lesson.title}\n\n"
        f"*Share this with your students:*\n"
        f"Students can join using: `clawed student-chat --class-code {class_code}`\n\n"
        f"*Teacher commands:*\n"
        f"\u2022 'show me what students are asking' \u2014 see student questions\n"
        f"\u2022 'set homework hint mode' \u2014 bot gives hints only, no direct answers\n"
        f"\u2022 'start student bot for lesson N' \u2014 switch to a different lesson"
    )


async def handle_show_student_report(parsed: ParsedIntent, session: TeacherSession) -> str:
    """Display student question report."""
    class_code = session.config.get("class_code")
    if not class_code:
        return "You haven't activated the student bot yet. Try: 'start student bot'"

    bot = StudentBot()
    report = await bot.get_student_report(class_code)

    lines = [
        "\U0001f4ca *Student Activity Report*",
        f"Class Code: `{class_code}`",
        "",
        f"\U0001f465 Students: {report['student_count']}",
        f"\U0001f4ac Total Messages: {report['total_messages']}",
    ]

    if report["recent_questions"]:
        lines.append("")
        lines.append("\U0001f4dd *Recent Questions:*")
        for q in report["recent_questions"][:10]:
            lines.append(f"\u2022 _{q['student_id']}_: {q['question'][:100]}")
    else:
        lines.append("\nNo student questions yet.")

    return "\n".join(lines)


async def handle_set_hint_mode(parsed: ParsedIntent, session: TeacherSession) -> str:
    """Toggle hint-only mode for student bot."""
    class_code = session.config.get("class_code")
    if not class_code:
        return "You haven't activated the student bot yet. Try: 'start student bot'"

    # Detect if turning off
    turning_off = bool(re.search(r"(disable|turn\s+off|deactivate|remove)", parsed.raw, re.IGNORECASE))

    bot = StudentBot()
    bot.set_hint_mode(class_code, not turning_off)

    if turning_off:
        return (
            "\u2705 Hint mode *disabled*. The student bot will now give full explanations and answers."
        )
    return (
        "\u2705 Hint mode *enabled*! The student bot will now:\n"
        "\u2022 Give hints and guiding questions instead of direct answers\n"
        "\u2022 Encourage students to think through problems step by step\n"
        "\u2022 Never reveal homework or assessment answers directly\n\n"
        "To turn off: 'disable hint mode'"
    )


# ── Freeform chat ────────────────────────────────────────────────────────────


async def generate_freeform(message: str, session: TeacherSession) -> str:
    """Handle anything that didn't match a known intent -- use LLM directly."""
    from clawed.llm import LLMClient

    config = route_model("quick_answer", AppConfig.load())
    client = LLMClient(config)

    persona_context = session.persona.to_prompt_context() if session.persona else "Teacher persona not yet configured."
    recent_context = session.get_context_for_llm(max_turns=4)

    system = (
        "You are Claw-ED, a warm and friendly AI teaching assistant. "
        "You speak naturally and conversationally -- like a supportive colleague "
        "in the teacher's lounge, not a corporate chatbot. Use contractions, "
        "be personable, ask follow-up questions when helpful.\n\n"
        "Keep responses concise: 1-3 sentences for casual chat (greetings, "
        "small talk, simple questions). Only give longer responses when the "
        "teacher asks for actual content generation or detailed curriculum help.\n\n"
        "Match the teacher's energy -- if they say 'hey' keep it casual, "
        "if they ask a detailed curriculum question give a thorough answer.\n\n"
        f"{persona_context}"
    )

    messages = [*recent_context, {"role": "user", "content": message}]

    try:
        response = await client.generate(
            prompt="\n".join(f"{m['role'].upper()}: {m['content']}" for m in messages),
            system=system,
            temperature=0.7,
            max_tokens=800,
        )
        return response
    except (ConnectionError, TimeoutError) as e:
        logger.error("Network error in freeform chat: %s", e)
        return "Couldn't reach the LLM provider. Check your connection and API key (`/status`)."
    except Exception as e:
        logger.exception("Unexpected error in freeform chat")
        return f"I ran into an issue: {str(e)[:150]}. Check your API key with `/status`."


# ── Connect / Ingest ─────────────────────────────────────────────────────────


async def handle_connect_drive(parsed: ParsedIntent, session: TeacherSession) -> str:
    """Connect a Google Drive folder and ingest lesson materials."""
    if not parsed.url:
        return "Could you share the Google Drive folder link? Right-click the folder \u2192 Share \u2192 Copy link"

    session.config["drive_url"] = parsed.url
    session.save()

    # Trigger ingestion
    try:
        from clawed.drive import ingest_drive_folder
        docs = await ingest_drive_folder(parsed.url)
        if docs:
            from clawed.persona import extract_persona
            config = AppConfig.load()
            persona = await extract_persona(docs, config)
            session.persona = persona
            session.save()
            return (
                f"\u2705 Connected! I analyzed {len(docs)} documents from your Drive.\n\n"
                + _fmt_persona(persona)
            )
        else:
            return (
                "I connected to Drive but couldn't find any lesson plan files"
                " (PDF, DOCX, PPTX). Make sure the folder contains your lesson"
                " materials and try again."
            )
    except Exception as e:
        return (
            f"Connected to Drive at {parsed.url}\n\n"
            "I'll analyze your materials in the background. "
            "Reply 'what do you know about me' once I've had a chance to learn your style.\n\n"
            f"_(Technical note: {str(e)[:100]})_"
        )


async def handle_connect_local(
    parsed: ParsedIntent,
    session: TeacherSession,
    *,
    notify_callback=None,
) -> str:
    """Connect a local folder and ingest lesson materials."""
    path = parsed.url
    if not path:
        return "What's the path to your lesson plan folder? (e.g., ~/Documents/Teaching/)"

    resolved = Path(path).expanduser().resolve()
    if not resolved.exists():
        return f"I can't find the folder at `{path}`. Could you double-check the path?"

    # Count files first
    try:
        from clawed.ingestor import SUPPORTED_EXTENSIONS

        supported = [
            f for f in resolved.rglob("*")
            if f.is_file()
            and f.suffix.lower() in SUPPORTED_EXTENSIONS
            and not f.name.startswith(("~$", "._"))
        ]
    except Exception:
        supported = []

    if not supported:
        return (
            f"Found the folder but no lesson plan files (PDF, DOCX, PPTX, TXT)"
            f" inside `{resolved.name}/`. Try a different folder?"
        )

    total_found = len(supported)
    max_files = 500

    # Cap message for very large directories
    cap_msg = ""
    if total_found > max_files:
        cap_msg = (
            f"Found {total_found:,} files. I'll analyze the {max_files} most "
            f"recent to learn your style.\n\n"
        )

    file_count = min(total_found, max_files)

    session.config["materials_path"] = str(resolved)
    session.save()

    # If a notify_callback is provided we run in the background and send
    # progress updates.  Otherwise do it synchronously for backwards compat.
    if notify_callback is not None:
        import threading

        if cap_msg:
            notify_callback(cap_msg)

        def _bg_ingest():
            try:
                from clawed.ingestor import ingest_path

                batch_size = 50

                def _progress(current, total):
                    if current % batch_size == 0 or current == total:
                        notify_callback(
                            f"Processing files {current - batch_size + 1}-"
                            f"{current} of {total}..."
                        )

                docs = ingest_path(
                    resolved,
                    max_files=max_files,
                    progress_callback=_progress,
                )
                if docs:
                    from clawed.async_utils import run_async_safe
                    from clawed.persona import extract_persona

                    persona_cfg = AppConfig.load()
                    persona = run_async_safe(extract_persona(docs, persona_cfg))
                    session.persona = persona
                    session.save()
                    notify_callback(
                        f"Analyzed {len(docs)} files from {resolved.name}/\n\n"
                        + _fmt_persona(persona)
                    )
                else:
                    notify_callback(
                        f"Found the folder but couldn't extract text from the files"
                        f" in `{resolved.name}/`. Try a different folder?"
                    )
            except Exception as e:
                notify_callback(
                    f"Had trouble reading files from {path}: {str(e)[:150]}"
                )

        t = threading.Thread(target=_bg_ingest, daemon=True)
        t.start()
        return (
            f"Scanning {resolved.name}/ ({file_count} files)... "
            f"I'll message you when I'm done."
        )

    # Synchronous path (no callback)
    try:
        from clawed.ingestor import ingest_path
        from clawed.persona import extract_persona

        docs = ingest_path(resolved, max_files=max_files)
        if docs:
            config = AppConfig.load()
            persona = await extract_persona(docs, config)
            session.persona = persona
            session.save()
            return (
                cap_msg
                + f"Analyzed {len(docs)} files from {resolved.name}/\n\n"
                + _fmt_persona(persona)
            )
        else:
            return (
                f"Found the folder but couldn't extract text from the files"
                f" in `{resolved.name}/`. Try a different folder?"
            )
    except Exception as e:
        return f"Had trouble reading files from {path}: {str(e)[:150]}"


# ── Setup ────────────────────────────────────────────────────────────────────


def _extract_subject_from_text(text: str) -> str:
    """Try to extract the subject from freeform text like 'I teach 8th grade science'."""

    subjects = [
        "math", "mathematics", "algebra", "geometry", "calculus", "statistics",
        "science", "biology", "chemistry", "physics", "earth science",
        "english", "ela", "language arts", "reading", "writing", "literature",
        "history", "social studies", "civics", "government", "geography", "economics",
        "art", "music", "drama", "theater", "theatre",
        "spanish", "french", "german", "chinese", "latin",
        "computer science", "coding", "programming",
        "pe", "physical education", "health",
    ]
    lower = text.lower()
    for subj in subjects:
        if subj in lower:
            return subj.title()
    return ""


def create_default_persona(parsed: ParsedIntent, session: TeacherSession) -> None:
    """Create a minimal default persona from whatever info we have."""
    from clawed.router import _extract_grade

    grade = parsed.grade or _extract_grade(parsed.raw) or ""
    subject = parsed.subject or _extract_subject_from_text(parsed.raw) or ""

    session.persona = TeacherPersona(
        name="My Teaching Persona",
        subject_area=subject,
        grade_levels=[grade] if grade else [],
    )
    session.save()


def handle_setup(parsed: ParsedIntent, session: TeacherSession) -> str:
    """Handle SETUP intent -- create a persona from the teacher's self-description."""
    from clawed.router import _extract_grade

    grade = parsed.grade or _extract_grade(parsed.raw) or ""
    subject = parsed.subject or _extract_subject_from_text(parsed.raw) or ""

    if subject or grade:
        # Create persona from what we know
        grade_str = f"Grade {grade} " if grade else ""
        subject_str = subject if subject else "General"
        session.persona = TeacherPersona(
            name="My Teaching Persona",
            subject_area=subject,
            grade_levels=[grade] if grade else [],
        )
        session.save()
        return (
            f"Got it \u2014 {grade_str}{subject_str}! I've set up your teaching profile. \U0001f393\n\n"
            f"You can personalize further anytime by sharing your lesson plans "
            f"(just give me a folder path or Google Drive link).\n\n"
            f"Ready to go! Try:\n"
            f"\u2022 'Generate a lesson on [topic]'\n"
            f"\u2022 'Plan a unit on [topic]'\n"
            f"\u2022 'Create a worksheet on [topic]'"
        )

    return setup_guide()


def setup_guide() -> str:
    """Return the setup guide text."""
    return (
        "\u2699\ufe0f *Getting Set Up*\n\n"
        "*Step 1: Connect your materials* (pick one)\n"
        "\u2022 Share a Google Drive folder link with your lesson plans\n"
        "\u2022 Tell me a local folder path: '~/Documents/Teaching/'\n"
        "\u2022 Or skip this and describe your teaching style directly\n\n"
        "*Step 2: Choose your AI provider*\n"
        "\u2022 Anthropic (Claude) \u2014 best quality\n"
        "  Set key: send 'my anthropic key is sk-...'\n"
        "\u2022 OpenAI (GPT-4o) \u2014 solid alternative\n"
        "  Set key: send 'my openai key is sk-...'\n"
        "\u2022 Ollama Cloud \u2014 free, no key needed\n"
        "  Send: 'use ollama at https://your-ollama-url.com'\n\n"
        "*Step 3: Generate something!*\n"
        "Once connected, just tell me what you need.\n\n"
        "What subject and grade do you teach?"
    )


# ── Help text ────────────────────────────────────────────────────────────────


def help_text() -> str:
    """Return the help message."""
    return (
        "\U0001f393 *Claw-ED \u2014 Your AI Teaching Assistant*\n\n"
        "*What I can do:*\n"
        "\u2022 Plan units and lessons in your teaching voice\n"
        "\u2022 Generate worksheets, assessments, and rubrics\n"
        "\u2022 Write differentiation notes (IEP accommodations, enrichment)\n"
        "\u2022 Find current news stories and resources for your lessons\n"
        "\u2022 Look up NGSS, Common Core, and other standards\n"
        "\u2022 Export to PDF, Google Classroom, or shareable links\n\n"
        "*Just talk to me naturally:*\n"
        "\u2022 'Plan a 3-week unit on the American Revolution for 8th grade'\n"
        "\u2022 'Write a lesson on photosynthesis'\n"
        "\u2022 'Find a current news story about climate change'\n"
        "\u2022 'Make a worksheet for today\u2019s lesson'\n\n"
        "*Setup:*\n"
        "\u2022 Share a Google Drive link to your lesson plans\n"
        "\u2022 Or tell me your local folder path\n"
        "\u2022 Or just describe your teaching style and we\u2019ll start fresh\n\n"
        "Reply `/status` to see your current setup."
    )


# ── Welcome ──────────────────────────────────────────────────────────────────


def welcome_text() -> str:
    """Return the first-time welcome message."""
    return (
        "Hey there! Welcome \u2014 I'm so glad you're here. \U0001f393\n\n"
        "I'm Claw-ED, and I'm basically going to become your lesson-planning "
        "partner. Think of me like that colleague down the hall who always has "
        "a great activity idea \u2014 except I'm available at midnight when you're "
        "prepping for tomorrow.\n\n"
        "Here's how we get started (pick whichever feels easiest):\n\n"
        "1\ufe0f\u20e3 *Share some of your existing lessons* and I'll learn your style:\n"
        "   Just tell me the folder \u2014 like `my materials are in ~/Documents/Lessons/`\n\n"
        "2\ufe0f\u20e3 *Or just tell me about yourself* and we'll build from scratch:\n"
        '   Something like "I teach 8th grade science" works great.\n\n'
        "Either way, once I know your vibe, everything I create will sound like *you* "
        "wrote it \u2014 your vocabulary, your structure, your approach.\n\n"
        "So \u2014 what do you teach? I'd love to hear about your classroom."
    )
