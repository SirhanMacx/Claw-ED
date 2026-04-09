"""Tool: update_soul — append observations to SOUL.md."""
from __future__ import annotations

import logging
from datetime import date
from typing import Any

from clawed.agent_core.context import AgentContext, ToolResult

logger = logging.getLogger(__name__)

SOUL_TEMPLATE = """\
# Teaching Identity

## Who I Am
<!-- Updated by your agent as it learns about you -->

## My Teaching Philosophy

## My Voice
<!-- How you talk to students -- the agent matches this -->

## My Classroom Norms

## Assessment Approach

## What Makes My Teaching Mine

## Agent Observations
<!-- The agent adds notes here as it reads your files and learns your patterns -->
"""

# Mapping from short section names to the full markdown header
SECTION_MAP = {
    "who": "## Who I Am",
    "identity": "## Who I Am",
    "philosophy": "## My Teaching Philosophy",
    "voice": "## My Voice",
    "norms": "## My Classroom Norms",
    "assessment": "## Assessment Approach",
    "signature": "## What Makes My Teaching Mine",
    "observations": "## Agent Observations",
    "preferences": "## Agent Observations",
}


class UpdateSoulTool:
    """Append observations to SOUL.md — the agent's evolving identity file."""

    risk_level = "write_local"

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "update_soul",
                "description": (
                    "Append an observation or note to a section of SOUL.md. "
                    "Use this when you learn something new about the teacher's "
                    "voice, philosophy, preferences, or teaching patterns."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "section": {
                            "type": "string",
                            "description": (
                                "Which section to update: 'voice', 'philosophy', "
                                "'identity', 'norms', 'assessment', 'signature', "
                                "or 'observations'"
                            ),
                        },
                        "content": {
                            "type": "string",
                            "description": "What to add to the section",
                        },
                    },
                    "required": ["section", "content"],
                },
            },
        }

    async def execute(
        self, params: dict[str, Any], context: AgentContext
    ) -> ToolResult:
        section_key = params["section"].lower().strip()
        content = params["content"].strip()

        header = SECTION_MAP.get(section_key)
        if not header:
            valid = ", ".join(sorted(SECTION_MAP.keys()))
            return ToolResult(
                text=f"Unknown section '{section_key}'. Valid sections: {valid}"
            )

        from clawed.workspace import SOUL_PATH

        soul_path = SOUL_PATH
        soul_path.parent.mkdir(parents=True, exist_ok=True)

        # Read or create SOUL.md
        if soul_path.exists():
            current = soul_path.read_text(encoding="utf-8")
        else:
            current = SOUL_TEMPLATE

        # Guard against oversized content
        if len(content) > 500:
            content = content[:500] + "..."

        import logging
        audit_logger = logging.getLogger("clawed.audit")
        audit_logger.info("SOUL.md update: header=%s, content=%s", header, content[:200])

        # Build the datestamped entry
        entry = f"\n\n*({date.today().isoformat()})* {content}\n"

        # Check for duplicate before writing
        from clawed.workspace import _deduplicate_entry

        if _deduplicate_entry(current, content, header):
            return ToolResult(
                text=f"Observation already exists in SOUL.md section '{section_key}' — skipping duplicate.",
            )

        # Insert after the section header
        if header in current:
            current = current.replace(header, header + entry, 1)
        else:
            # Section header missing -- append at the end
            current += f"\n{header}{entry}"

        try:
            soul_path.write_text(current, encoding="utf-8")
            return ToolResult(
                text=f"Updated SOUL.md section '{section_key}' with new observation.",
                side_effects=[f"Updated SOUL.md: {header}"],
            )
        except Exception as e:
            return ToolResult(text=f"Failed to update SOUL.md: {e}")
