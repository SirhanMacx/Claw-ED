"""Differentiation tool — Ed can modify lessons for IEP, ELL, gifted, 504 students."""

from __future__ import annotations

import logging
from typing import Any

from clawed.agent_core.context import AgentContext, ToolResult

logger = logging.getLogger(__name__)


class DifferentiateLessonTool:
    """Modify a lesson for students with special needs."""

    risk_level = "read_only"

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "differentiate_lesson",
                "description": (
                    "Modify a lesson for students with IEPs, ELLs, gifted learners, "
                    "or 504 plans. Generates scaffolds, accommodations, extensions, "
                    "and modified assessments appropriate to the modification type."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "lesson_content": {
                            "type": "string",
                            "description": "The lesson text or topic to differentiate",
                        },
                        "modification_type": {
                            "type": "string",
                            "enum": ["iep", "ell", "gifted", "504"],
                            "description": "Type of differentiation needed",
                        },
                        "specific_needs": {
                            "type": "string",
                            "description": (
                                "Specific student needs (e.g., 'extended time, visual supports, reduced questions')"
                            ),
                        },
                    },
                    "required": ["lesson_content", "modification_type"],
                },
            },
        }

    async def execute(self, params: dict[str, Any], context: AgentContext) -> ToolResult:
        content = params.get("lesson_content", "").strip()
        mod_type = params.get("modification_type", "iep")
        needs = params.get("specific_needs", "")

        if not content:
            return ToolResult(text="ERROR: lesson_content is required")

        context.notify_progress(f"Creating {mod_type.upper()} modifications...")

        try:
            from clawed.llm import LLMClient
            from clawed.models import AppConfig

            config = context.config or AppConfig.load()
            llm = LLMClient(config)

            mod_labels = {
                "iep": "IEP (Individualized Education Program)",
                "ell": "English Language Learner",
                "gifted": "Gifted and Talented",
                "504": "Section 504 Accommodation Plan",
            }

            prompt = (
                "You are a special education expert modifying a lesson for "
                f"{mod_labels.get(mod_type, mod_type)} students.\n\n"
                f"## Original Lesson\n{content}\n\n"
                f"## Modification Type: {mod_labels.get(mod_type, mod_type)}\n"
            )
            if needs:
                prompt += f"## Specific Student Needs\n{needs}\n\n"

            prompt += (
                "Generate comprehensive modifications including:\n"
                "1. **Modified objectives** — same standard, adjusted complexity\n"
                "2. **Scaffolded activities** — graphic organizers, sentence frames, word banks\n"
                "3. **Assessment modifications** — extended time, reduced items, alternative formats\n"
                "4. **Support materials** — visual aids, vocabulary support, chunked instructions\n"
                "5. **Extension activities** (for gifted) or **accommodations** (for IEP/504/ELL)\n\n"
                "Format as a complete, usable modification document."
            )

            result_text = await llm.generate(prompt, system="You are a master special education teacher.")

            if not result_text or len(result_text.strip()) < 50:
                return ToolResult(text="Differentiation generation produced insufficient content.")

            return ToolResult(
                text=f"## {mod_labels.get(mod_type, mod_type)} Modifications\n\n{result_text}",
            )

        except Exception as e:
            logger.error("Differentiation failed: %s", e)
            return ToolResult(text=f"Differentiation failed: {e}")
