"""Tool: generate_lesson — wraps clawed.lesson.generate_lesson."""
from __future__ import annotations

import contextlib
import json
from typing import Any

from clawed.agent_core.context import AgentContext, ToolResult


class GenerateLessonTool:
    """Generate a complete daily lesson plan on a topic."""

    risk_level = "read_only"

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "generate_lesson",
                "description": (
                    "Generate a complete daily lesson plan on a topic. "
                    "Returns a structured lesson with Do Now, instruction, activities, "
                    "exit ticket, and differentiation."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "topic": {
                            "type": "string",
                            "description": "The lesson topic",
                        },
                        "grade": {
                            "type": "string",
                            "description": "Grade level (e.g. '8', 'K')",
                            "default": "8",
                        },
                        "subject": {
                            "type": "string",
                            "description": "Subject area",
                            "default": "General",
                        },
                    },
                    "required": ["topic"],
                },
            },
        }

    async def execute(
        self, params: dict[str, Any], context: AgentContext
    ) -> ToolResult:
        from clawed.lesson import generate_lesson
        from clawed.models import LessonBrief, TeacherPersona, UnitPlan

        topic = params["topic"]
        grade = params.get("grade", "8")
        subject = params.get("subject", "General")

        config = context.config
        persona = TeacherPersona()
        if context.persona:
            with contextlib.suppress(Exception):
                persona = TeacherPersona(**context.persona)

        unit = UnitPlan(
            title=f"{topic} Unit",
            subject=subject,
            grade_level=grade,
            topic=topic,
            duration_weeks=1,
            overview=f"A lesson on {topic}.",
            daily_lessons=[
                LessonBrief(
                    lesson_number=1,
                    topic=topic,
                    description=f"Introduction to {topic}",
                )
            ],
        )

        # ── Search for teacher's existing materials (assets + KB) ─────
        kb_prompt_section = ""
        try:
            from clawed.asset_registry import AssetRegistry
            registry = AssetRegistry()
            assets = registry.search_assets(context.teacher_id, topic, top_k=5)
            yt_links = registry.get_youtube_links(context.teacher_id, topic, top_k=3)
            if assets or yt_links:
                kb_prompt_section = registry.format_asset_summary(assets, yt_links)
        except Exception:
            pass

        try:
            from clawed.agent_core.memory.curriculum_kb import CurriculumKB
            kb = CurriculumKB()
            kb_results = kb.search(context.teacher_id, topic, top_k=3)
            if kb_results:
                kb_parts = [r for r in kb_results if r.get("similarity", 0) > 0.1]
                if kb_parts:
                    chunk_section = "\n\n".join(
                        f"From \"{r['doc_title']}\":\n{r['chunk_text'][:500]}"
                        for r in kb_parts
                    )
                    if kb_prompt_section:
                        kb_prompt_section += "\n\n" + chunk_section
                    else:
                        kb_prompt_section = (
                            "Teacher's Existing Materials on This Topic\n"
                            "The teacher has created content on this topic before. "
                            "Reference and build on their existing work:\n\n"
                            + chunk_section
                            + "\n\nUse these materials as a foundation."
                        )
        except Exception:
            pass

        try:
            lesson = await generate_lesson(
                lesson_number=1,
                unit=unit,
                persona=persona,
                config=config,
                teacher_materials=kb_prompt_section,
            )
            lesson_data = lesson.model_dump()
            title = lesson_data.get("title", topic)
            return ToolResult(
                text=f"Generated lesson: {title}\n\n"
                f"{json.dumps(lesson_data, indent=2)[:2000]}",
                data=lesson_data,
                side_effects=[f"Generated lesson on {topic}"],
            )
        except Exception as e:
            return ToolResult(text=f"Failed to generate lesson: {e}")
