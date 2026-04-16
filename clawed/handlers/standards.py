"""Standards lookup handler. Extracted from tg.py lines 916-945."""
from __future__ import annotations

import logging

from clawed.gateway_response import GatewayResponse

logger = logging.getLogger(__name__)

def get_standards(subject: str, grade: str | None) -> list[tuple[str, str, str]]:
    from clawed.standards import get_standards as _get_standards
    return _get_standards(subject, grade)

class StandardsHandler:
    async def lookup(self, subject: str, grade: str, limit: int = 15) -> GatewayResponse:
        """Note: get_standards returns list[tuple[str, str, str]] = (code, description, grade_band)."""
        standards = get_standards(subject, grade)
        if not standards:
            return GatewayResponse(text=f"No standards found for {subject} grade {grade}.")
        lines = [f"Standards for {subject.title()} Grade {grade}:\n"]
        for code, desc, _band in standards[:limit]:
            lines.append(f"  {code}: {desc}")
        if len(standards) > limit:
            lines.append(f"\n  ...and {len(standards) - limit} more")
        return GatewayResponse(text="\n".join(lines))
