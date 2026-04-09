"""Wiki tools — Ed can compile, query, and maintain a Karpathy-style wiki.

The wiki transforms raw ingested chunks into LLM-synthesized markdown
articles organized by topic. Knowledge compounds over time as new
materials are ingested and articles are updated.
"""

from __future__ import annotations

import logging
from typing import Any

from clawed.agent_core.context import AgentContext, ToolResult

logger = logging.getLogger(__name__)


class WikiCompileTool:
    """Compile the teacher's curriculum into a structured wiki."""

    risk_level = "write_local"

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "compile_wiki",
                "description": (
                    "Compile the teacher's ingested curriculum files into "
                    "an organized wiki. Creates markdown articles grouped "
                    "by topic with cross-references. Incremental — only "
                    "recompiles changed documents."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "force": {
                            "type": "boolean",
                            "description": (
                                "Recompile all articles even if unchanged"
                            ),
                        },
                    },
                },
            },
        }

    async def execute(
        self, params: dict[str, Any], context: AgentContext
    ) -> ToolResult:
        force = params.get("force", False)
        context.notify_progress("Compiling curriculum wiki...")

        try:
            from clawed.wiki import compile_wiki
            result = await compile_wiki(
                teacher_id=context.teacher_id,
                force=force,
            )
            return ToolResult(
                text=(
                    f"Wiki compiled: {result.compiled} articles updated, "
                    f"{result.skipped} unchanged, "
                    f"{result.errors} errors."
                ),
            )
        except Exception as e:
            logger.error("Wiki compile failed: %s", e)
            return ToolResult(text=f"Wiki compilation failed: {e}")


class WikiQueryTool:
    """Ask a question against the teacher's curriculum wiki."""

    risk_level = "read_only"

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "query_wiki",
                "description": (
                    "Ask a question against the teacher's compiled "
                    "curriculum wiki. Returns an answer with citations "
                    "from the teacher's own materials. Use this to find "
                    "specific information from their curriculum."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "question": {
                            "type": "string",
                            "description": "The question to answer",
                        },
                    },
                    "required": ["question"],
                },
            },
        }

    async def execute(
        self, params: dict[str, Any], context: AgentContext
    ) -> ToolResult:
        question = params.get("question", "").strip()
        if not question:
            return ToolResult(text="ERROR: question is required")

        try:
            from clawed.wiki import query_wiki
            result = await query_wiki(question)
            parts = [result.answer]
            if result.sources:
                parts.append("\nSources:")
                for s in result.sources:
                    parts.append(f"  - {s}")
            return ToolResult(text="\n".join(parts))
        except Exception as e:
            logger.error("Wiki query failed: %s", e)
            return ToolResult(text=f"Wiki query failed: {e}")


class WikiLintTool:
    """Check wiki health — stale, uncovered, and orphaned articles."""

    risk_level = "read_only"

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "lint_wiki",
                "description": (
                    "Check the health of the curriculum wiki. Finds "
                    "stale articles (source changed), uncovered topics "
                    "(no article yet), and orphaned articles (source "
                    "deleted). Use to maintain wiki quality."
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
        try:
            from clawed.wiki import lint_wiki
            result = lint_wiki(teacher_id=context.teacher_id)
            parts = ["Wiki Health Report:"]
            parts.append(f"  Stale articles: {len(result.stale)}")
            parts.append(f"  Uncovered topics: {len(result.uncovered)}")
            parts.append(f"  Orphaned articles: {len(result.orphaned)}")

            if result.stale:
                parts.append("\nStale (source changed):")
                for s in result.stale[:5]:
                    parts.append(f"  - {s}")
            if result.uncovered:
                parts.append("\nUncovered (no article):")
                for u in result.uncovered[:5]:
                    parts.append(f"  - {u}")
            if result.orphaned:
                parts.append("\nOrphaned (source deleted):")
                for o in result.orphaned[:5]:
                    parts.append(
                        f"  - {o.get('doc_title', '?')}"
                    )

            return ToolResult(text="\n".join(parts))
        except Exception as e:
            logger.error("Wiki lint failed: %s", e)
            return ToolResult(text=f"Wiki lint failed: {e}")
