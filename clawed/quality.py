"""Lesson Quality Score Engine — score generated lesson plans on multiple dimensions."""

from __future__ import annotations

from typing import Any

from clawed.llm import LLMClient
from clawed.models import AppConfig, DailyLesson, LessonMaterials


class LessonQualityScore:
    """Score a generated lesson plan on multiple dimensions."""

    dimensions = [
        "objective_clarity",
        "do_now_relevance",
        "instruction_depth",
        "differentiation_quality",
        "exit_ticket_alignment",
        "materials_completeness",
    ]

    dimension_descriptions = {
        "objective_clarity": "Is the SWBAT measurable and specific?",
        "do_now_relevance": "Does the warm-up connect to the objective?",
        "instruction_depth": "Is the direct instruction substantive?",
        "differentiation_quality": "Are accommodations specific, not generic?",
        "exit_ticket_alignment": "Do exit ticket questions test the objective?",
        "materials_completeness": "Does the worksheet cover key concepts?",
    }

    def __init__(self, config: AppConfig | None = None):
        self.client = LLMClient(config)

    async def score(self, lesson: DailyLesson, materials: LessonMaterials | None = None) -> dict[str, Any]:
        """Score each dimension 1-5 with brief explanation.

        Returns:
            {
                "objective_clarity": {"score": 4, "explanation": "..."},
                ...,
                "overall": 3.8
            }
        """
        lesson_text = self._lesson_to_text(lesson)
        materials_text = self._materials_to_text(materials) if materials else "No materials provided."

        dimensions_block = "\n".join(f"- {dim}: {desc}" for dim, desc in self.dimension_descriptions.items())

        prompt = (
            "You are an expert instructional coach evaluating a lesson plan.\n\n"
            "## Lesson Plan\n"
            f"{lesson_text}\n\n"
            "## Materials\n"
            f"{materials_text}\n\n"
            "## Scoring Dimensions\n"
            f"{dimensions_block}\n\n"
            "## Task\n"
            "Score each dimension from 1-5 (1=poor, 5=excellent). "
            "For each, provide a 1-sentence explanation.\n\n"
            "Return valid JSON with this exact structure:\n"
            "{\n"
            '  "objective_clarity": {"score": <int>, "explanation": "<string>"},\n'
            '  "do_now_relevance": {"score": <int>, "explanation": "<string>"},\n'
            '  "instruction_depth": {"score": <int>, "explanation": "<string>"},\n'
            '  "differentiation_quality": {"score": <int>, "explanation": "<string>"},\n'
            '  "exit_ticket_alignment": {"score": <int>, "explanation": "<string>"},\n'
            '  "materials_completeness": {"score": <int>, "explanation": "<string>"}\n'
            "}\n"
            "Return ONLY the JSON object, nothing else."
        )

        raw = await self.client.generate_json(
            prompt=prompt,
            system="You are a lesson quality evaluator. Return only valid JSON.",
            temperature=0.3,
            max_tokens=2000,
        )

        # Validate and normalize scores
        result: dict[str, Any] = {}
        scores = []
        for dim in self.dimensions:
            entry = raw.get(dim, {"score": 3, "explanation": "Not evaluated."})
            score_val = max(1, min(5, int(entry.get("score", 3))))
            result[dim] = {
                "score": score_val,
                "explanation": str(entry.get("explanation", "")),
            }
            scores.append(score_val)

        result["overall"] = round(sum(scores) / len(scores), 2) if scores else 0.0
        return result

    @staticmethod
    def _lesson_to_text(lesson: DailyLesson) -> str:
        parts = [
            f"Title: {lesson.title}",
            f"Objective: {lesson.objective}",
            f"Standards: {', '.join(lesson.standards) if lesson.standards else 'None'}",
            f"Do-Now: {lesson.do_now}",
            f"Direct Instruction: {lesson.direct_instruction}",
            f"Guided Practice: {lesson.guided_practice}",
            f"Independent Work: {lesson.independent_work}",
        ]
        if lesson.exit_ticket:
            parts.append("Exit Ticket Questions:")
            for et in lesson.exit_ticket:
                parts.append(f"  - {et.question}")
        if lesson.differentiation:
            diff = lesson.differentiation
            if diff.struggling:
                parts.append(f"Struggling learners: {'; '.join(diff.struggling)}")
            if diff.advanced:
                parts.append(f"Advanced learners: {'; '.join(diff.advanced)}")
            if diff.ell:
                parts.append(f"ELL: {'; '.join(diff.ell)}")
        return "\n".join(parts)

    @staticmethod
    def _materials_to_text(materials: LessonMaterials) -> str:
        parts = [f"Lesson Title: {materials.lesson_title}"]
        if materials.worksheet_items:
            parts.append(f"Worksheet: {len(materials.worksheet_items)} items")
            for item in materials.worksheet_items[:5]:
                parts.append(f"  - {item.prompt}")
        if materials.assessment_questions:
            parts.append(f"Assessment: {len(materials.assessment_questions)} questions")
        return "\n".join(parts)


async def score_voice_match(
    lesson_text: str,
    persona_context: str,
    llm_client: Any = None,
) -> float:
    """Score how well lesson text matches the teacher's voice (1.0-5.0).

    Uses an LLM to compare the lesson language, tone, scaffolding style,
    and pedagogical patterns against the teacher persona.

    Returns 3.0 (neutral) if scoring fails — NLAH: do not block delivery.
    """
    if not persona_context or not lesson_text:
        return 3.0

    prompt = (
        "Rate how well this lesson matches the teacher's established voice "
        "and teaching style on a scale of 1.0 to 5.0.\n\n"
        "Teacher persona:\n"
        f"{persona_context[:1500]}\n\n"
        "Lesson excerpt:\n"
        f"{lesson_text[:2000]}\n\n"
        "Score criteria:\n"
        "5.0 = Sounds exactly like this teacher wrote it\n"
        "4.0 = Captures most of their style and patterns\n"
        "3.0 = Generic but acceptable\n"
        "2.0 = Noticeably different from their voice\n"
        "1.0 = Completely wrong tone/style\n\n"
        'Return ONLY a JSON object: {"score": 4.2, "reason": "brief explanation"}'
    )

    if llm_client is None:
        return 3.0  # No LLM available, neutral score

    try:
        import json as _json

        raw = await llm_client.generate(prompt, temperature=0.2, max_tokens=200)
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines)
        result = _json.loads(cleaned)
        score = float(result.get("score", 3.0))
        return max(1.0, min(5.0, score))  # Clamp to valid range
    except Exception:
        return 3.0  # Fail neutral — NLAH: do not block delivery
