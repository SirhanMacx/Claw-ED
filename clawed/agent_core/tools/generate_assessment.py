"""Tool: generate_assessment — wraps clawed.assessment.AssessmentGenerator.generate_quiz."""
from __future__ import annotations

import json
from typing import Any

from clawed.agent_core.context import AgentContext, ToolResult


class GenerateAssessmentTool:
    """Generate a quiz or assessment on a topic."""

    risk_level = "read_only"

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "generate_assessment",
                "description": (
                    "Generate a quiz or assessment with questions and scoring "
                    "for a given topic and grade level."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "topic": {
                            "type": "string",
                            "description": "The assessment topic",
                        },
                        "grade": {
                            "type": "string",
                            "description": "Grade level (e.g. '8', 'K')",
                            "default": "8",
                        },
                        "num_questions": {
                            "type": "integer",
                            "description": "Number of questions to generate",
                            "default": 10,
                        },
                    },
                    "required": ["topic"],
                },
            },
        }

    async def execute(
        self, params: dict[str, Any], context: AgentContext
    ) -> ToolResult:
        from clawed.assessment import AssessmentGenerator

        topic = params["topic"]
        grade = params.get("grade", "8")
        num_questions = params.get("num_questions", 10)

        try:
            gen = AssessmentGenerator(context.config)
            quiz = await gen.generate_quiz(
                topic=topic,
                question_count=num_questions,
                grade=grade,
            )
            quiz_data = quiz.model_dump()
            return ToolResult(
                text=f"Generated quiz: {quiz.topic} "
                f"({quiz.total_points} points, "
                f"{len(quiz.questions)} questions)\n\n"
                f"{json.dumps(quiz_data, indent=2)[:2000]}",
                data=quiz_data,
                side_effects=[f"Generated assessment on {topic}"],
            )
        except Exception as e:
            return ToolResult(text=f"Failed to generate assessment: {e}")
