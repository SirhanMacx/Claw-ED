"""Curriculum gap analysis handler. Extracted from tg.py lines 1030-1127."""

from __future__ import annotations

import logging

from clawed.gateway_response import GatewayResponse

logger = logging.getLogger(__name__)


class GapsHandler:
    async def analyze(self, teacher_id: str) -> GatewayResponse:
        try:
            from clawed.generation import generate_freeform
            from clawed.state import TeacherSession

            session = TeacherSession.load(teacher_id)
            response = await generate_freeform("curriculum gap analysis", session)
            return GatewayResponse(text=response)
        except Exception as e:
            logger.error("Gap analysis failed: %s", e)
            return GatewayResponse(text="Gap analysis failed. Make sure you have lessons and standards configured.")
