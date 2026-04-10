"""Game generation tool — Ed can create interactive HTML learning games."""

from __future__ import annotations

import logging
from typing import Any

from clawed.agent_core.context import AgentContext, ToolResult

logger = logging.getLogger(__name__)


class GenerateGameTool:
    """Create an interactive HTML learning game for students."""

    risk_level = "read_only"

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "generate_game",
                "description": (
                    "Create an interactive HTML learning game that students can "
                    "play in a browser. Games are self-contained HTML files with "
                    "embedded JavaScript. Types: quiz_show, matching, timeline, "
                    "vocabulary, jeopardy, escape_room."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "topic": {
                            "type": "string",
                            "description": "The topic for the game (e.g., 'French Revolution causes')",
                        },
                        "subject": {
                            "type": "string",
                            "description": "School subject (e.g., 'World History')",
                        },
                        "grade": {
                            "type": "string",
                            "description": "Grade level (e.g., '10')",
                        },
                        "game_type": {
                            "type": "string",
                            "enum": ["quiz_show", "matching", "timeline", "vocabulary", "jeopardy", "escape_room"],
                            "description": "Type of game to create",
                        },
                    },
                    "required": ["topic"],
                },
            },
        }

    async def execute(self, params: dict[str, Any], context: AgentContext) -> ToolResult:
        topic = params.get("topic", "").strip()
        if not topic:
            return ToolResult(text="ERROR: topic is required")

        subject = params.get("subject", "")
        grade = params.get("grade", "")
        game_type = params.get("game_type", "quiz_show")

        context.notify_progress(f"Creating {game_type} game on {topic}...")

        try:
            from clawed.compile_game import compile_game
            from clawed.models import TeacherPersona

            persona = None
            if context.persona:
                try:
                    persona = TeacherPersona(**context.persona)
                except Exception:
                    pass

            # Build a minimal MasterContent for compile_game
            from clawed.master_content import MasterContent

            resolved_subject = subject or (context.persona or {}).get("subject_area", "")
            resolved_grade = grade or ((context.persona or {}).get("grade_levels", [""])[0] if context.persona else "")
            master = MasterContent(
                title=f"{topic} Game",
                subject=resolved_subject,
                grade_level=resolved_grade,
                topic=topic,
                objective=f"Review and reinforce {topic} concepts",
            )

            result_path = await compile_game(
                master=master,
                persona=persona,
                output_dir=None,
                game_style=game_type,
                config=context.config,
            )

            if result_path and result_path.exists():
                return ToolResult(
                    text=f"Created {game_type} game on '{topic}': {result_path}",
                    files=[result_path],
                )
            return ToolResult(text="Game generation completed but no file was produced.")

        except Exception as e:
            logger.error("Game generation failed: %s", e)
            return ToolResult(text=f"Game generation failed: {e}")
