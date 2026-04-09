"""Tool: improve_lesson — revise a specific section of an existing lesson."""
from __future__ import annotations

import logging
from typing import Any

from clawed.agent_core.context import AgentContext, ToolResult
from clawed.failure_codes import FailureCode

logger = logging.getLogger(__name__)


class ImproveLessonTool:
    """Improve or revise part of an existing lesson without full regeneration.

    The teacher specifies the original lesson topic and a concrete
    improvement request (e.g. "make the primary source harder",
    "add a misconception trap", "shorten the Do Now"). The tool finds
    the original lesson content in the KB, sends it to the LLM with the
    improvement instruction, and returns the revised section.
    """

    risk_level = "read_only"

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "improve_lesson",
                "description": (
                    "Revise or improve a specific part of an existing lesson "
                    "without regenerating the whole thing. Provide the lesson "
                    "topic and a specific improvement request. The tool finds "
                    "the original lesson in the knowledge base, applies the "
                    "requested change via the LLM, and returns ONLY the "
                    "improved section. "
                    "Examples: 'make the primary source harder', "
                    "'add a misconception trap to the exit ticket', "
                    "'shorten the Do Now to 3 minutes', "
                    "'add an ELL scaffold to the vocabulary section'."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "topic": {
                            "type": "string",
                            "description": (
                                "The topic of the existing lesson to improve. "
                                "Used to find the lesson in the knowledge base."
                            ),
                        },
                        "improvement": {
                            "type": "string",
                            "description": (
                                "What specifically to improve or change. "
                                "Be concrete: 'make the exit ticket harder', "
                                "'add a Think-Pair-Share to the We Do section', "
                                "'replace the warm-up with a misconception trap'."
                            ),
                        },
                        "section": {
                            "type": "string",
                            "description": (
                                "Optional: which section to target. If omitted, "
                                "the LLM determines the best section to revise."
                            ),
                            "enum": [
                                "do_now",
                                "direct_instruction",
                                "guided_practice",
                                "independent_practice",
                                "exit_ticket",
                                "vocabulary",
                                "homework",
                                "differentiation",
                                "full_lesson",
                            ],
                        },
                    },
                    "required": ["topic", "improvement"],
                },
            },
        }

    async def execute(
        self, params: dict[str, Any], context: AgentContext
    ) -> ToolResult:
        topic = params["topic"]
        improvement = params["improvement"]
        section = params.get("section", "")

        teacher_id = context.teacher_id
        config = context.config

        # ── Notify the teacher ───────────────────────────────────────
        context.notify_progress(
            f"Looking up your existing lesson on \"{topic}\" and applying "
            f"your requested change. This usually takes under a minute."
        )

        # ── Search KB for the original lesson content ────────────────
        original_content = ""

        # 1. Try asset-level search (complete files)
        try:
            from clawed.asset_registry import AssetRegistry

            registry = AssetRegistry()
            assets = registry.search_assets(teacher_id, topic, top_k=3)
            if not assets:
                assets = registry.search_assets("", topic, top_k=3)
            if assets:
                asset_parts = []
                for a in assets:
                    title = a.get("title", "Untitled")
                    atype = a.get("material_type", "document")
                    asset_parts.append(
                        f"[{atype}] {title} ({a.get('filename', 'unknown')})"
                    )
                original_content += (
                    "Existing teacher files on this topic:\n"
                    + "\n".join(asset_parts)
                    + "\n\n"
                )
        except Exception as e:
            logger.debug("Asset search for improve_lesson failed: %s", e)

        # 2. Try chunk-level KB search (text excerpts)
        try:
            from clawed.agent_core.memory.curriculum_kb import CurriculumKB

            kb = CurriculumKB()
            results = kb.search(teacher_id, topic, top_k=5)
            if not results:
                results = kb.search_all_teachers(topic, top_k=5)

            if results:
                relevant = [r for r in results if r.get("similarity", 0) > 0.1]
                if relevant:
                    original_content += "Original lesson content from knowledge base:\n\n"
                    for r in relevant:
                        source = r.get("doc_title", "Unknown source")
                        chunk = r.get("chunk_text", "")[:800]
                        original_content += f"--- From \"{source}\" ---\n{chunk}\n\n"
        except Exception as e:
            logger.debug("KB search for improve_lesson failed: %s", e)

        # 3. Try database search for generated lessons
        try:
            from clawed.database import Database

            db = Database()
            units = db.list_units()
            for unit in units:
                lessons = db.list_lessons(unit["id"])
                for lesson_row in lessons:
                    title = (lesson_row.get("title") or "").lower()
                    if topic.lower() in title or title in topic.lower():
                        import json

                        lesson_json = lesson_row.get("lesson_json", "")
                        if lesson_json:
                            try:
                                lesson_data = json.loads(lesson_json)
                                # Extract a summary of the lesson for context
                                parts = []
                                if lesson_data.get("title"):
                                    parts.append(f"Title: {lesson_data['title']}")
                                if lesson_data.get("objective"):
                                    parts.append(f"Objective: {lesson_data['objective']}")
                                if lesson_data.get("standards"):
                                    parts.append(
                                        f"Standards: {', '.join(lesson_data['standards'][:5])}"
                                    )
                                # Include full lesson JSON (truncated for context window)
                                lesson_str = json.dumps(lesson_data, indent=2)
                                if len(lesson_str) > 3000:
                                    lesson_str = lesson_str[:3000] + "\n... (truncated)"
                                parts.append(f"\nFull lesson data:\n{lesson_str}")
                                original_content += (
                                    "Previously generated lesson:\n"
                                    + "\n".join(parts)
                                    + "\n\n"
                                )
                            except (json.JSONDecodeError, TypeError):
                                pass
        except Exception as e:
            logger.debug("DB search for improve_lesson failed: %s", e)

        if not original_content:
            return ToolResult(
                text=(
                    f"Could not find an existing lesson on \"{topic}\" in your "
                    f"materials or generation history. Try generating the lesson "
                    f"first with generate_lesson_bundle, then use improve_lesson "
                    f"to refine it."
                )
            )

        # ── Build the improvement prompt ─────────────────────────────
        section_instruction = ""
        if section:
            section_label = section.replace("_", " ").title()
            section_instruction = (
                f"\nFocus specifically on the {section_label} section. "
                f"Return ONLY the revised {section_label} section, not the "
                f"entire lesson.\n"
            )
        else:
            section_instruction = (
                "\nDetermine which section(s) of the lesson are most "
                "relevant to this improvement request and revise only "
                "those sections. Return ONLY the revised content, not "
                "the entire lesson.\n"
            )

        # Load persona for voice matching
        persona_context = ""
        if context.persona:
            try:
                from clawed.models import TeacherPersona

                persona = TeacherPersona(**context.persona)
                persona_context = persona.to_prompt_context()
            except Exception:
                pass

        prompt = (
            "You are an expert curriculum editor helping a teacher improve "
            "an existing lesson. The teacher has a specific change request.\n\n"
            f"{persona_context}\n\n"
            f"EXISTING LESSON CONTENT:\n{original_content}\n\n"
            f"TEACHER'S IMPROVEMENT REQUEST:\n{improvement}\n"
            f"{section_instruction}\n"
            "INSTRUCTIONS:\n"
            "1. Read the existing lesson content carefully.\n"
            "2. Apply ONLY the requested change. Do not rewrite sections "
            "that don't need changes.\n"
            "3. Maintain the teacher's existing voice, vocabulary level, "
            "and formatting conventions.\n"
            "4. Return the improved section with clear formatting "
            "(headers, bullet points, numbered lists as appropriate).\n"
            "5. If the improvement involves adding content (e.g. a new "
            "question, a new activity), make it specific and actionable "
            "-- not generic filler.\n"
            "6. Keep the same standards alignment and grade-level "
            "appropriateness as the original.\n"
        )

        # ── Call the LLM ─────────────────────────────────────────────
        try:
            from clawed.llm import LLMClient

            llm = LLMClient(config=config)
            improved_text = await llm.generate(prompt)
        except Exception as e:
            logger.error(
                "NLAH_FAILURE=%s: improve_lesson LLM call failed: %s",
                FailureCode.API_FAILURE, e,
            )
            return ToolResult(
                text=(
                    f"[{FailureCode.API_FAILURE}] Failed to generate improvement: "
                    f"{type(e).__name__}. Check your LLM provider connection."
                )
            )

        if not improved_text or len(improved_text.strip()) < 20:
            return ToolResult(
                text="The LLM returned an empty or unusable response. "
                     "Try rephrasing your improvement request."
            )

        # ── Humanize the output ──────────────────────────────────────
        try:
            from clawed.humanize import humanize

            improved_text = humanize(improved_text)
        except Exception:
            pass

        # ── Build the response ───────────────────────────────────────
        section_label = (
            section.replace("_", " ").title() if section else "Lesson"
        )
        lines = [
            f"Improved {section_label} for \"{topic}\":",
            "",
            improved_text,
            "",
            "---",
            "This is the revised section only. Your original lesson files "
            "are unchanged. Copy this into your lesson plan, or ask me to "
            "regenerate the full bundle with these changes baked in.",
        ]

        return ToolResult(
            text="\n".join(lines),
            data={
                "topic": topic,
                "improvement": improvement,
                "section": section,
            },
        )
