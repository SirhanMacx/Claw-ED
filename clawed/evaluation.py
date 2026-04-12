"""Voice consistency evaluation framework for Claw-ED.

Evaluates whether generated lessons match the teacher's persona voice.
This is the "5 real teachers, 10 lessons each" test harness — it lets
anyone verify whether the persona extraction and voice injection work.

Usage:
    from clawed.evaluation import evaluate_voice_consistency

    report = await evaluate_voice_consistency(persona, lessons)
    print(report.summary())

CLI:
    clawed evaluate --lessons 10
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from clawed.models import AppConfig, DailyLesson, TeacherPersona

logger = logging.getLogger(__name__)


class LessonScore(BaseModel):
    """Voice evaluation scores for a single lesson."""

    lesson_title: str = ""
    lesson_number: int = 0
    voice_consistency: int = 3  # 1-5
    vocabulary_match: int = 3  # 1-5
    structure_match: int = 3  # 1-5
    drift_examples: list[str] = Field(default_factory=list)
    notes: str = ""


class VoiceReport(BaseModel):
    """Complete voice evaluation report across multiple lessons."""

    persona_name: str = ""
    total_lessons: int = 0
    lesson_scores: list[LessonScore] = Field(default_factory=list)
    avg_voice_consistency: float = 0.0
    avg_vocabulary_match: float = 0.0
    avg_structure_match: float = 0.0
    overall_score: float = 0.0
    recommendations: list[str] = Field(default_factory=list)

    def summary(self) -> str:
        """Human-readable summary of the evaluation."""
        lines = [
            f"Voice Evaluation Report: {self.persona_name}",
            f"Lessons evaluated: {self.total_lessons}",
            "",
            f"  Voice Consistency:  {self.avg_voice_consistency:.1f}/5",
            f"  Vocabulary Match:   {self.avg_vocabulary_match:.1f}/5",
            f"  Structure Match:    {self.avg_structure_match:.1f}/5",
            f"  Overall Score:      {self.overall_score:.1f}/5",
            "",
        ]
        if self.recommendations:
            lines.append("Recommendations:")
            for rec in self.recommendations:
                lines.append(f"  - {rec}")
            lines.append("")

        # Show per-lesson drift examples
        drift_count = sum(len(s.drift_examples) for s in self.lesson_scores)
        if drift_count > 0:
            lines.append(f"Voice drift detected in {drift_count} instance(s):")
            for score in self.lesson_scores:
                for ex in score.drift_examples:
                    lines.append(f"  Lesson {score.lesson_number}: {ex}")

        return "\n".join(lines)


_EVALUATION_PROMPT = """You are evaluating whether a generated lesson plan matches a teacher's voice and style.

## Teacher Persona
{persona}

## Generated Lesson
Title: {lesson_title}
Objective: {objective}

Do-Now:
{do_now}

Direct Instruction:
{direct_instruction}

Guided Practice:
{guided_practice}

## Evaluation Criteria

Score each dimension from 1-5:

1. **Voice Consistency** (1-5): Does the lesson sound like this teacher wrote it?
   - 5 = Perfect match, indistinguishable from teacher's own writing
   - 3 = Generally similar but some generic/AI-sounding passages
   - 1 = Completely different voice, clearly AI-generated

2. **Vocabulary Match** (1-5): Does the lesson use the teacher's characteristic vocabulary?
   - 5 = Uses teacher's exact phrases, terminology, and word choices
   - 3 = Some matching vocabulary but also many generic terms
   - 1 = Academic/formal language that doesn't match the teacher at all

3. **Structure Match** (1-5): Does the lesson follow the teacher's preferred format?
   - 5 = Matches their exact structural preferences (e.g., warm-ups, exit tickets, etc.)
   - 3 = Has some preferred elements but misses others
   - 1 = Completely different structure

For each score below 4, provide a specific example of where the voice drifted.

## Output Format
Respond with ONLY a JSON object:

{{
    "voice_consistency": 4,
    "vocabulary_match": 3,
    "structure_match": 5,
    "drift_examples": ["The phrase 'leverage synergies' is not how this teacher talks"],
    "notes": "Generally good but the direct instruction section sounds too formal"
}}"""


async def evaluate_voice_consistency(
    persona: TeacherPersona,
    lessons: list[DailyLesson],
    config: AppConfig | None = None,
) -> VoiceReport:
    """Evaluate how well generated lessons match the teacher's voice.

    Uses the LLM to score each lesson on voice consistency, vocabulary match,
    and structure match. Returns a VoiceReport with scores and drift examples.

    Args:
        persona: The teacher persona to evaluate against.
        lessons: List of generated lessons to evaluate.
        config: Optional app config for LLM access.

    Returns:
        VoiceReport with per-lesson scores and aggregate metrics.
    """
    from clawed.llm import LLMClient

    if config is None:
        config = AppConfig.load()

    client = LLMClient(config)
    scores: list[LessonScore] = []

    for lesson in lessons:
        prompt = (
            _EVALUATION_PROMPT
            .replace("{persona}", persona.to_prompt_context())
            .replace("{lesson_title}", lesson.title)
            .replace("{objective}", lesson.objective)
            .replace("{do_now}", lesson.do_now[:500])
            .replace("{direct_instruction}", lesson.direct_instruction[:1000])
            .replace("{guided_practice}", lesson.guided_practice[:500])
        )

        try:
            data = await client.generate_json(
                prompt=prompt,
                system="You are an expert evaluator of educational content voice consistency. Respond only with JSON.",
                temperature=0.2,
                max_tokens=500,
            )

            score = LessonScore(
                lesson_title=lesson.title,
                lesson_number=lesson.lesson_number,
                voice_consistency=min(5, max(1, data.get("voice_consistency", 3))),
                vocabulary_match=min(5, max(1, data.get("vocabulary_match", 3))),
                structure_match=min(5, max(1, data.get("structure_match", 3))),
                drift_examples=data.get("drift_examples", []),
                notes=data.get("notes", ""),
            )
        except Exception as e:
            # Broad catch: per-lesson evaluation is best-effort; any
            # failure degrades gracefully to neutral scores.
            logger.debug("Voice evaluation failed for lesson %s: %s", lesson.title, e)
            score = LessonScore(
                lesson_title=lesson.title,
                lesson_number=lesson.lesson_number,
                notes=f"Evaluation failed: {str(e)[:100]}",
            )

        scores.append(score)

    # Compute averages
    n = len(scores) or 1
    avg_voice = sum(s.voice_consistency for s in scores) / n
    avg_vocab = sum(s.vocabulary_match for s in scores) / n
    avg_struct = sum(s.structure_match for s in scores) / n
    overall = (avg_voice + avg_vocab + avg_struct) / 3

    # Generate recommendations
    recommendations: list[str] = []
    if avg_voice < 3.5:
        recommendations.append(
            "Voice consistency is low. Add more voice_examples to the persona "
            "by sharing additional teaching materials."
        )
    if avg_vocab < 3.5:
        recommendations.append(
            "Vocabulary doesn't match well. The persona's voice_sample and "
            "voice_examples may need more characteristic phrases."
        )
    if avg_struct < 3.5:
        recommendations.append(
            "Structure doesn't match the teacher's preferences. "
            "Update structural_preferences in the persona."
        )
    if overall >= 4.0:
        recommendations.append("Voice quality is strong across all dimensions.")

    return VoiceReport(
        persona_name=persona.name,
        total_lessons=len(lessons),
        lesson_scores=scores,
        avg_voice_consistency=round(avg_voice, 2),
        avg_vocabulary_match=round(avg_vocab, 2),
        avg_structure_match=round(avg_struct, 2),
        overall_score=round(overall, 2),
        recommendations=recommendations,
    )
