"""Self-distillation tool — Ed improves by analyzing his own best outputs.

Implements prompt self-distillation inspired by Zhang et al. (2025)
"Embarrassingly Simple Self-Distillation Improves Code Generation."
Adapted for teaching: analyze highest-rated and most-edited generations
to extract actionable rules, then update soul.md.
"""

from __future__ import annotations

import logging
from typing import Any

from clawed.agent_core.context import AgentContext, ToolResult

logger = logging.getLogger(__name__)


class SelfDistillTool:
    """Analyze past outputs and distill improvement rules into soul.md."""

    risk_level = "write_local"

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "self_distill",
                "description": (
                    "Analyze your past lesson generations to improve. "
                    "Looks at highest-rated outputs (what works), "
                    "lowest-rated and most-edited outputs (what to fix), "
                    "and recurring patterns. Distills actionable rules "
                    "and writes them to soul.md for future use. "
                    "Run this periodically to get better over time."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        }

    async def execute(
        self, params: dict[str, Any], context: AgentContext
    ) -> ToolResult:
        context.notify_progress("Analyzing past outputs for patterns...")

        try:
            from clawed.agent_core.quality import self_distill

            # Try to get LLM for rule generation
            llm_fn = None
            try:
                from clawed.llm import LLMClient
                client = LLMClient(context.config)

                def _generate(prompt: str) -> str:
                    import asyncio
                    return asyncio.get_event_loop().run_until_complete(
                        client.generate(prompt, system="You are Ed.")
                    )

                llm_fn = _generate
            except ImportError:
                pass

            result = self_distill(
                teacher_id=context.teacher_id,
                llm_generate=llm_fn,
            )

            if not result:
                return ToolResult(
                    text=(
                        "Not enough data to distill yet. I need more "
                        "teacher ratings and feedback on generated lessons. "
                        "Keep generating and rating — I'll learn from the "
                        "patterns over time."
                    )
                )

            return ToolResult(
                text=(
                    "Self-distillation complete. Here's what I learned:\n\n"
                    f"{result}\n\n"
                    "These insights are now saved to my soul.md and will "
                    "guide future lesson generation."
                )
            )

        except Exception as e:
            logger.error("Self-distillation failed: %s", e)
            return ToolResult(text=f"Self-distillation failed: {e}")
