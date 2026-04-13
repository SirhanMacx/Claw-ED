"""Lesson and unit generation handler.

Wraps clawed.generation service functions with transport-agnostic response
building (post-generation buttons, error handling).

Extracted from tg.py lines 1697-1766.
"""
from __future__ import annotations

import asyncio
import logging

from clawed.gateway_response import Button, GatewayResponse
from clawed.hermes_plugin import get_last_lesson_id

logger = logging.getLogger(__name__)


def _post_generation_buttons(lesson_id: str) -> list[list[Button]]:
    """Build export + rating button rows for post-generation UX."""
    export_row = [
        Button(label="Slides", callback_data=f"action:export_slides:{lesson_id}"),
        Button(label="Handout", callback_data=f"action:export_handout:{lesson_id}"),
        Button(label="Word Doc", callback_data=f"action:export_doc:{lesson_id}"),
    ]
    action_row = [
        Button(label="Rate this lesson", callback_data=f"rate:{lesson_id}:0_prompt"),
        Button(label="Worksheet", callback_data=f"action:worksheet:{lesson_id}"),
    ]
    return [export_row, action_row]


class GenerateHandler:
    """Handles lesson and unit generation requests."""

    async def lesson(self, topic: str, teacher_id: str) -> GatewayResponse:
        """Generate a lesson on the given topic."""
        try:
            from clawed.generation import generate_lesson
            from clawed.router import parse_intent
            from clawed.state import TeacherSession

            parsed = parse_intent(f"generate a lesson on {topic}")
            session = TeacherSession.load(teacher_id)
            response_text = await asyncio.wait_for(
                generate_lesson(parsed, session),
                timeout=120.0,
            )
        except TimeoutError:
            logger.error("Lesson generation timed out after 120s")
            return GatewayResponse(
                text="Generation timed out. Please try again with a simpler topic."
            )
        except Exception as e:
            logger.error("Lesson generation failed: %s", e)
            return GatewayResponse(
                text="I ran into an issue generating that lesson. Please try again."
            )

        button_rows = []
        lesson_id = get_last_lesson_id(teacher_id)
        if lesson_id:
            button_rows = _post_generation_buttons(lesson_id)

        return GatewayResponse(text=response_text, button_rows=button_rows)

    async def unit(self, topic: str, teacher_id: str) -> GatewayResponse:
        """Generate a unit plan on the given topic."""
        try:
            from clawed.generation import generate_unit
            from clawed.router import parse_intent
            from clawed.state import TeacherSession

            parsed = parse_intent(f"plan a unit on {topic}")
            session = TeacherSession.load(teacher_id)
            response_text = await asyncio.wait_for(
                generate_unit(parsed, session),
                timeout=120.0,
            )
        except TimeoutError:
            logger.error("Unit generation timed out after 120s")
            return GatewayResponse(
                text="Generation timed out. Please try again with a simpler topic."
            )
        except Exception as e:
            logger.error("Unit generation failed: %s", e)
            return GatewayResponse(
                text="I ran into an issue planning that unit. Please try again."
            )

        return GatewayResponse(text=response_text)
