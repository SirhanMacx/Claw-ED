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

        original_content = self._search_lesson_content(teacher_id, topic)

        if not original_content:
            return ToolResult(
                text=(
                    f"Could not find an existing lesson on \"{topic}\" in your "
                    f"materials or generation history. Try generating the lesson "
                    f"first with generate_lesson_bundle, then use improve_lesson "
                    f"to refine it."
                )
            )

        prompt = self._build_improvement_prompt(
            original_content, improvement, section, context,
        )

        improved_text = await self._call_llm_for_improvement(prompt, config)
        if isinstance(improved_text, ToolResult):
            return improved_text

        section_label = section.replace("_", " ").title() if section else "Lesson"
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

    def _search_lesson_content(self, teacher_id: str, topic: str) -> str:
        """Search assets, KB, and DB for existing lesson content on a topic."""
        original_content = ""

        try:
            from clawed.asset_registry import AssetRegistry
            registry = AssetRegistry()
            assets = registry.search_assets(teacher_id, topic, top_k=3)
            if not assets:
                assets = registry.search_assets("", topic, top_k=3)
            if assets:
                parts = [
                    f"[{a.get('material_type', 'document')}] "
                    f"{a.get('title', 'Untitled')} ({a.get('filename', 'unknown')})"
                    for a in assets
                ]
                original_content += "Existing teacher files on this topic:\n" + "\n".join(parts) + "\n\n"
        except Exception as e:
            logger.debug("Asset search for improve_lesson failed: %s", e)

        try:
            from clawed.agent_core.memory.curriculum_kb import CurriculumKB
            kb = CurriculumKB()
            results = kb.search(teacher_id, topic, top_k=5)
            if not results:
                results = kb.search_all_teachers(topic, top_k=5)
            relevant = [r for r in (results or []) if r.get("similarity", 0) > 0.1]
            if relevant:
                original_content += "Original lesson content from knowledge base:\n\n"
                for r in relevant:
                    source = r.get("doc_title", "Unknown")
                    chunk = r.get("chunk_text", "")[:800]
                    original_content += f'--- From "{source}" ---\n{chunk}\n\n'
        except Exception as e:
            logger.debug("KB search for improve_lesson failed: %s", e)

        try:
            import json

            from clawed.database import Database
            db = Database()
            for unit in db.list_units():
                for row in db.list_lessons(unit["id"]):
                    title = (row.get("title") or "").lower()
                    if topic.lower() in title or title in topic.lower():
                        if row.get("lesson_json"):
                            try:
                                data = json.loads(row["lesson_json"])
                                s = json.dumps(data, indent=2)
                                if len(s) > 3000:
                                    s = s[:3000] + "\n... (truncated)"
                                original_content += f"Previously generated lesson:\n{s}\n\n"
                            except (json.JSONDecodeError, TypeError):
                                pass
        except Exception as e:
            logger.debug("DB search for improve_lesson failed: %s", e)

        return original_content

    def _build_improvement_prompt(self, original_content, improvement, section, context):
        """Build the LLM prompt for lesson improvement."""
        if section:
            label = section.replace("_", " ").title()
            section_instruction = (
                f"\nFocus specifically on the {label} section. "
                f"Return ONLY the revised {label} section, not the entire lesson.\n"
            )
        else:
            section_instruction = (
                "\nDetermine which section(s) are most relevant and revise "
                "only those. Return ONLY the revised content, not the entire lesson.\n"
            )

        persona_context = ""
        if context.persona:
            try:
                from clawed.models import TeacherPersona
                persona_context = TeacherPersona(**context.persona).to_prompt_context()
            except ImportError:
                pass

        return (
            "You are an expert curriculum editor helping a teacher improve "
            "an existing lesson. The teacher has a specific change request.\n\n"
            f"{persona_context}\n\n"
            f"EXISTING LESSON CONTENT:\n{original_content}\n\n"
            f"TEACHER'S IMPROVEMENT REQUEST:\n{improvement}\n"
            f"{section_instruction}\n"
            "INSTRUCTIONS:\n"
            "1. Read the existing lesson content carefully.\n"
            "2. Apply ONLY the requested change. Do not rewrite sections that don't need changes.\n"
            "3. Maintain the teacher's existing voice, vocabulary level, and formatting conventions.\n"
            "4. Return the improved section with clear formatting.\n"
            "5. If the improvement involves adding content, make it specific and actionable.\n"
            "6. Keep the same standards alignment and grade-level appropriateness as the original.\n"
        )

    async def _call_llm_for_improvement(self, prompt, config):
        """Call LLM and humanize the result. Returns str or ToolResult on error."""
        try:
            from clawed.llm import LLMClient
            improved_text = await LLMClient(config=config).generate(prompt)
        except Exception as e:
            logger.error(
                "NLAH_FAILURE=%s: improve_lesson LLM call failed: %s",
                FailureCode.API_FAILURE, e,
            )
            return ToolResult(
                text=f"[{FailureCode.API_FAILURE}] Failed to generate improvement: "
                f"{type(e).__name__}. Check your LLM provider connection."
            )

        if not improved_text or len(improved_text.strip()) < 20:
            return ToolResult(
                text="The LLM returned an empty or unusable response. "
                "Try rephrasing your improvement request."
            )

        try:
            from clawed.humanize import humanize
            improved_text = humanize(improved_text)
        except ImportError:
            pass
        return improved_text

