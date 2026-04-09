"""Adaptive lesson adjustment based on student performance data.

Analyzes exit ticket results, ratings, and grading data to automatically
adjust the next lesson:
- Identify weak areas and add targeted re-teach activities
- Strengthen scaffolding for concepts students struggled with
- Generate review activities for the bottom quartile
- Create extension tasks for students who mastered the content

This is the feedback loop that closes the planning-to-outcomes gap.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


def analyze_performance(
    grading_results: list[dict],
) -> dict:
    """Analyze a batch of exit ticket grading results.

    Args:
        grading_results: List of dicts from grade_exit_ticket(), each with
            {"score": int, "meets_standard": bool, "cognitive_level": str}

    Returns:
        {
            "total_students": int,
            "mastery_rate": float,  # % scoring 3+
            "by_question": [{"question_index": int, "avg_score": float, "mastery_rate": float}],
            "weak_areas": [str],  # cognitive levels where students struggled
            "strong_areas": [str],
            "recommendation": str,  # "reteach", "extend", "proceed"
        }
    """
    if not grading_results:
        return {
            "total_students": 0,
            "mastery_rate": 0.0,
            "by_question": [],
            "weak_areas": [],
            "strong_areas": [],
            "recommendation": "no data",
        }

    total = len(grading_results)
    mastered = sum(1 for r in grading_results if r.get("meets_standard", False))
    mastery_rate = mastered / total if total else 0.0

    # Analyze by cognitive level
    by_level: dict[str, list[int]] = {}
    for r in grading_results:
        level = r.get("cognitive_level", "unknown")
        by_level.setdefault(level, []).append(r.get("score", 0))

    weak_areas: list[str] = []
    strong_areas: list[str] = []
    for level, scores in by_level.items():
        avg = sum(scores) / len(scores) if scores else 0
        if avg < 2.5:
            weak_areas.append(level)
        elif avg >= 3.5:
            strong_areas.append(level)

    # Recommendation
    if mastery_rate >= 0.8:
        recommendation = "proceed"
    elif mastery_rate >= 0.5:
        recommendation = "partial_reteach"
    else:
        recommendation = "full_reteach"

    return {
        "total_students": total,
        "mastery_rate": round(mastery_rate, 2),
        "by_question": [],  # Could be expanded with per-question data
        "weak_areas": weak_areas,
        "strong_areas": strong_areas,
        "recommendation": recommendation,
    }


def generate_adjustment_context(
    performance: dict,
    previous_topic: str = "",
) -> str:
    """Generate prompt context for the NEXT lesson based on performance data.

    This string is injected into the teacher_materials section of the
    next lesson's generation prompt, so the LLM adapts its output.

    Args:
        performance: Output from analyze_performance().
        previous_topic: Topic of the lesson that was assessed.

    Returns:
        A prompt context string for the next lesson generation.
    """
    if performance.get("recommendation") == "no data":
        return ""

    mastery = performance.get("mastery_rate", 0)
    total = performance.get("total_students", 0)
    weak = performance.get("weak_areas", [])
    rec = performance.get("recommendation", "proceed")

    parts: list[str] = []

    parts.append("## Student Performance Data (from previous lesson)")
    parts.append(
        f"Previous topic: {previous_topic}\n"
        f"Students assessed: {total}\n"
        f"Mastery rate: {mastery:.0%} scored proficient or above"
    )

    if rec == "full_reteach":
        parts.append(
            "\nACTION REQUIRED: Fewer than 50% of students mastered the content.\n"
            "Begin today's lesson with a 10-minute targeted re-teach activity "
            "covering the key concepts from the previous lesson. Use a DIFFERENT "
            "approach than last time (if you lectured, try stations; if you did "
            "stations, try a whole-class interactive activity)."
        )
    elif rec == "partial_reteach":
        parts.append(
            "\nSuggestion: 50-80% mastery. Start with a 5-minute review warm-up "
            "targeting the weak areas, then proceed with new content.\n"
            "Consider providing extra scaffolding for today's lesson."
        )
    else:
        parts.append(
            "\nStudents are ready to proceed. Consider a brief 2-minute "
            "connection to previous learning in the Do Now."
        )

    if weak:
        parts.append(
            f"\nWeak cognitive areas: {', '.join(weak)}\n"
            "Strengthen these in today's lesson with additional practice."
        )

    return "\n".join(parts)


def generate_parent_notification(
    student_name: str,
    performance: dict,
    lesson_topic: str,
) -> str:
    """Draft a parent notification based on student performance.

    Returns a teacher-ready email draft.
    """
    mastery = performance.get("mastery_rate", 0)
    rec = performance.get("recommendation", "proceed")

    if rec == "proceed":
        return (
            f"Dear Parent/Guardian of {student_name},\n\n"
            f"I wanted to share that {student_name} performed well on our "
            f"recent assessment on {lesson_topic}. "
            f"The class had a {mastery:.0%} mastery rate, and your child "
            f"demonstrated strong understanding.\n\n"
            f"Please continue to encourage their engagement with the material.\n\n"
            f"Best,\n[Teacher Name]"
        )
    else:
        return (
            f"Dear Parent/Guardian of {student_name},\n\n"
            f"I wanted to touch base about our recent work on {lesson_topic}. "
            f"The exit ticket showed that {student_name} could benefit from "
            f"additional practice with some of the key concepts.\n\n"
            f"Here are a few things that might help at home:\n"
            f"- Review the guided notes from class\n"
            f"- Practice the vocabulary terms\n"
            f"- Ask your child to explain what they learned in their own words\n\n"
            f"I'll be providing additional support in class as well. "
            f"Please don't hesitate to reach out with questions.\n\n"
            f"Best,\n[Teacher Name]"
        )
