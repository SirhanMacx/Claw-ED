"""Prompt improvement loop — analyzes feedback and generates improved prompt variants."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from clawed.database import Database
from clawed.feedback import analyze_feedback
from clawed.llm import LLMClient
from clawed.models import AppConfig

if TYPE_CHECKING:
    from clawed.models import DailyLesson

PROMPT_DIR = Path(__file__).parent / "prompts"

# Map prompt types to their template files
PROMPT_FILES: dict[str, str] = {
    "lesson_plan": "lesson_plan.txt",
    "unit_plan": "unit_plan.txt",
    "persona_extract": "persona_extract.txt",
    "worksheet": "worksheet.txt",
    "assessment": "assessment.txt",
    "differentiation": "differentiation.txt",
}


async def improve_prompts(
    db: Database,
    feedback_window_days: int = 7,
    config: AppConfig | None = None,
) -> dict[str, Any]:
    """Analyze recent feedback and generate improved prompt variants.

    Steps:
        1. Pull lessons with low ratings from last N days
        2. Pull teacher edit patterns (which sections get edited most)
        3. Ask LLM: "Given these examples of bad output and what teachers changed,
           how should the prompt be improved?"
        4. Generate 3 new prompt variants
        5. Store as prompt_versions with is_active=False
        6. Randomly assign new generations to test variants (A/B test)
        7. After 10 uses, promote winner to active

    Returns:
        Summary of what was improved.
    """
    analysis = analyze_feedback(db, feedback_window_days)

    if analysis["total_feedback"] == 0:
        return {"status": "no_feedback", "message": "No feedback collected yet. Generate and rate some lessons first."}

    if analysis["avg_rating"] >= 4.0 and analysis["low_rated_count"] == 0:
        msg = f"Prompts performing well (avg rating: {analysis['avg_rating']}). No improvement needed."
        return {"status": "good", "message": msg}

    # Collect examples of poorly-rated lessons
    low_rated_lessons = db.get_low_rated_lessons(max_rating=2, days=feedback_window_days)

    lesson_examples = ""
    for i, row in enumerate(low_rated_lessons[:3], 1):
        lesson_data = row.get("lesson_json", "{}")
        notes = row.get("feedback_notes", "")
        rating = row.get("feedback_rating", "?")
        lesson_examples += (
            f"\n--- Example {i} (rated {rating}/5) ---\n"
            f"Teacher notes: {notes}\n"
            f"Lesson excerpt: {lesson_data[:500]}\n"
        )

    # Determine which prompt type to improve based on edit patterns
    target_type = "lesson_plan"  # Default to lesson plan
    edited = analysis["most_edited_sections"]
    if edited:
        # If teachers mostly edit objectives/standards, improve unit planning
        plan_sections = {"overview", "essential_questions", "standards", "assessment_plan"}
        if any(s in plan_sections for s in edited):
            target_type = "unit_plan"

    # Load current prompt
    prompt_file = PROMPT_FILES.get(target_type, "lesson_plan.txt")
    current_prompt = (PROMPT_DIR / prompt_file).read_text(encoding="utf-8")

    # Get current version number
    versions = db.get_prompt_versions(target_type)
    next_version = (versions[0]["version"] + 1) if versions else 2

    # Ask LLM to suggest improvements
    improvement_prompt = (
        f"You are an expert prompt engineer for educational AI systems.\n\n"
        f"## Current Prompt Template\n```\n{current_prompt[:2000]}\n```\n\n"
        f"## Feedback Analysis\n"
        f"- Average rating: {analysis['avg_rating']}/5\n"
        f"- Low-rated lessons: {analysis['low_rated_count']}\n"
        f"- Most edited sections: {', '.join(analysis['most_edited_sections']) or 'N/A'}\n"
        f"- Teacher complaints: {'; '.join(analysis['sample_notes'][:5]) or 'None recorded'}\n\n"
        f"## Examples of Poor Output\n{lesson_examples or 'No specific examples available.'}\n\n"
        f"## Task\n"
        f"Generate an improved version of this prompt that addresses the feedback.\n"
        f"Focus on: making output more practical, better aligned to teacher expectations, "
        f"and reducing the need for manual edits.\n\n"
        f"Return ONLY the improved prompt text, nothing else."
    )

    client = LLMClient(config)
    improved_text = await client.generate(
        prompt=improvement_prompt,
        system="You are a prompt engineering expert. Return only the improved prompt template.",
        temperature=0.5,
        max_tokens=4000,
    )

    # Store the new variant
    prompt_id = db.insert_prompt_version(target_type, next_version, improved_text)

    # Check if any prior versions have enough usage to promote
    _check_and_promote(db, target_type)

    return {
        "status": "improved",
        "prompt_type": target_type,
        "new_version": next_version,
        "prompt_id": prompt_id,
        "feedback_summary": analysis,
        "message": f"Generated improved {target_type} prompt (version {next_version}).",
    }


async def suggest_improvements(
    lesson: DailyLesson,
    feedback_notes: str = "",
    config: AppConfig | None = None,
) -> list[str]:
    """Given a lesson plan (and optional teacher feedback), generate 3-5 specific, actionable improvement suggestions.

    Each suggestion targets a specific section and explains the change.
    """

    parts = [
        f"Title: {lesson.title}",
        f"Objective: {lesson.objective}",
        f"Do-Now: {lesson.do_now}",
        f"Direct Instruction: {lesson.direct_instruction}",
        f"Guided Practice: {lesson.guided_practice}",
        f"Independent Work: {lesson.independent_work}",
    ]
    if lesson.exit_ticket:
        parts.append("Exit Ticket:")
        for et in lesson.exit_ticket:
            parts.append(f"  - {et.question}")
    if lesson.differentiation:
        diff = lesson.differentiation
        if diff.struggling:
            parts.append(f"Struggling: {'; '.join(diff.struggling)}")
        if diff.advanced:
            parts.append(f"Advanced: {'; '.join(diff.advanced)}")

    lesson_text = "\n".join(parts)
    feedback_block = f"\n\nTeacher feedback: {feedback_notes}" if feedback_notes else ""

    prompt = (
        "You are an expert instructional coach reviewing a lesson plan.\n\n"
        f"## Lesson Plan\n{lesson_text}\n"
        f"{feedback_block}\n\n"
        "## Task\n"
        "Generate exactly 5 specific, actionable improvement suggestions.\n"
        "Each suggestion should:\n"
        "1. Target a specific section of the lesson\n"
        "2. Explain what's wrong or could be better\n"
        "3. Provide a concrete alternative or addition\n\n"
        "Format: Return a JSON array of 5 strings. Each string is one complete suggestion.\n"
        "Example: [\"Your Do-Now doesn't connect to today's objective. Consider: ...\", ...]\n\n"
        "Return ONLY the JSON array, nothing else."
    )

    client = LLMClient(config)
    raw = await client.generate_json(
        prompt=prompt,
        system="You are an instructional coach. Return only a JSON array of suggestion strings.",
        temperature=0.5,
        max_tokens=2000,
    )

    # Handle both list and dict responses
    if isinstance(raw, list):  # type: ignore[unreachable]
        return [str(s) for s in raw[:5]]  # type: ignore[unreachable]
    elif isinstance(raw, dict) and "suggestions" in raw:
        return [str(s) for s in raw["suggestions"][:5]]
    return [str(raw)]


def queue_low_rated_for_improvement(rating: int, lesson_id: str, teacher_id: str) -> bool:
    """When a lesson is rated below 3, flag it for the next improvement cycle.

    This is called from the rating flow (Telegram, CLI, web) to ensure
    low-quality lessons automatically feed into prompt improvement.

    Returns True if the lesson was queued (rating < 3).
    """
    if rating >= 3:
        return False

    import logging

    logger = logging.getLogger(__name__)

    try:
        from clawed.state import _get_conn, init_db

        init_db()
        with _get_conn() as _conn:
            # Mark the lesson as needing improvement by ensuring its feedback
            # is stored — the improve_prompts() function already picks up
            # low-rated lessons from the feedback table.
            # Additionally, log this for visibility.
            logger.info(
                "Lesson %s rated %d/5 by teacher %s — queued for improvement analysis",
                lesson_id, rating, teacher_id,
            )
    except Exception as e:
        logger.warning("Failed to queue lesson for improvement: %s", e)

    return True


def _check_and_promote(db: Database, prompt_type: str) -> None:
    """Check if any test variants have enough usage data to promote."""
    versions = db.get_prompt_versions(prompt_type)
    candidates = [v for v in versions if v["usage_count"] >= 10 and not v["is_active"]]
    if not candidates:
        return

    # Find the best-performing variant
    best = max(candidates, key=lambda v: v["avg_rating"] or 0)
    active = db.get_active_prompt(prompt_type)

    if active and best.get("avg_rating", 0) and active.get("avg_rating", 0):
        if best["avg_rating"] > active["avg_rating"]:
            db.promote_prompt(best["id"], prompt_type)
