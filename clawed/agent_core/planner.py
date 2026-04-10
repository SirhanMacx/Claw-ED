"""Multi-step request planning — system prompt enhancement for complex tasks."""

from __future__ import annotations

_PLANNING_KEYWORDS = [
    "prepare my week",
    "prep my week",
    "plan my week",
    "create a full",
    "generate everything",
    "do everything",
    "prepare next week",
    "get ready for",
    "unit with materials",
    "unit plan with",
    "full unit",
    "complete unit",
    "plan a unit",
    "plan a full",
    "plan the unit",
    "year-long",
    "year long",
    "yearlong",
    "curriculum map",
    "pacing guide",
    "scope and sequence",
    "plan the semester",
    "plan the year",
    "plan next month",
    "prepare all",
    "generate all",
    "build a unit",
]

_PLANNING_ADDITION = """
## Multi-Step Planning Mode

This request requires multiple steps. Think through what needs to happen,
then execute each step by calling tools in sequence. For example:
1. First, check what's needed (search standards, check curriculum state)
2. Then generate the content (unit plan, lessons, materials)
3. Finally, organize the output (export, upload to Drive if connected)

Execute each step by calling the appropriate tool. Don't just describe what you would do — actually do it.
If a step requires teacher approval (like uploading to Drive), use the request_approval tool.
"""


def is_planning_request(message: str) -> bool:
    """Check if a message looks like it needs multi-step planning."""
    lower = message.lower()
    return any(kw in lower for kw in _PLANNING_KEYWORDS)


def build_planning_prompt() -> str:
    """Return the planning addition to inject into the system prompt."""
    return _PLANNING_ADDITION
