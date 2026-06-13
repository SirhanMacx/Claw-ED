"""Agent tools for the Claw-ED teaching brain and curriculum index.

These wrap CLI-only capabilities so the desktop/iOS harness can operate the
same long-term memory, dream, and indexed-material workflows through chat.
"""
from __future__ import annotations

from typing import Any

from clawed.agent_core.context import AgentContext, ToolResult
from clawed.agent_core.tools.base import RISK_READ_ONLY, RISK_WRITE_LOCAL
from clawed.brain.store import PAGE_TYPES


def _page_type(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    return text if text in PAGE_TYPES else None


class BrainStatsTool:
    """Show counts for the teacher's durable teaching brain."""

    risk_level = RISK_READ_ONLY

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "brain_stats",
                "description": (
                    "Show statistics for the durable teaching brain: students, "
                    "topics, lessons, concepts, original insights, classes, and people."
                ),
                "parameters": {"type": "object", "properties": {}},
            },
        }

    async def execute(self, params: dict[str, Any], context: AgentContext) -> ToolResult:
        from clawed.brain.store import BrainStore

        store = BrainStore()
        stats = store.stats()
        total = sum(int(v) for v in stats.values())
        lines = [f"Teaching brain: {total} page(s)."]
        for page_type in PAGE_TYPES:
            count = int(stats.get(page_type, 0))
            lines.append(f"- {page_type}: {count}")
        return ToolResult(text="\n".join(lines), data={"stats": stats, "total": total})


class BrainSearchTool:
    """Hybrid search across brain pages and, optionally, the curriculum corpus."""

    risk_level = RISK_READ_ONLY

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "brain_search",
                "description": (
                    "Search the teaching brain for students, topics, past lessons, "
                    "original pedagogical insights, concepts, classes, and people. "
                    "Can also include the indexed curriculum corpus."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "What to search for.",
                        },
                        "page_type": {
                            "type": "string",
                            "description": (
                                "Optional filter: student, topic, lesson, original, "
                                "class, concept, or person."
                            ),
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum results to return. Default 8.",
                        },
                        "include_corpus": {
                            "type": "boolean",
                            "description": (
                                "Also search indexed curriculum chunks. Default true."
                            ),
                        },
                    },
                    "required": ["query"],
                },
            },
        }

    async def execute(self, params: dict[str, Any], context: AgentContext) -> ToolResult:
        from clawed.brain.search import hybrid_search

        query = str(params.get("query", "")).strip()
        if not query:
            return ToolResult(text="ERROR: query is required.")

        limit = int(params.get("limit") or 8)
        limit = max(1, min(limit, 20))
        include_corpus = bool(params.get("include_corpus", True))
        page_type = _page_type(params.get("page_type"))

        results = hybrid_search(
            query,
            page_type=page_type,
            limit=limit,
            include_corpus=include_corpus,
        )
        if not results:
            return ToolResult(
                text=f"No brain or indexed-material results found for '{query}'.",
                data={"results": []},
            )

        lines = [f"Found {len(results)} result(s) for '{query}':"]
        payload: list[dict[str, Any]] = []
        for r in results:
            snippet = (r.snippet or "").replace("\n", " ").strip()
            if len(snippet) > 220:
                snippet = snippet[:217].rstrip() + "..."
            lines.append(f"- {r.page_type}/{r.slug} - {r.title}")
            if snippet:
                lines.append(f"  {snippet}")
            payload.append({
                "source": r.source,
                "page_type": r.page_type,
                "slug": r.slug,
                "title": r.title,
                "snippet": snippet,
                "score": r.score,
            })
        return ToolResult(text="\n".join(lines), data={"results": payload})


class BrainReadTool:
    """Read one brain page by type and slug."""

    risk_level = RISK_READ_ONLY

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "brain_read",
                "description": (
                    "Read a durable brain page by type and slug, including the "
                    "compiled truth and evidence timeline."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "page_type": {
                            "type": "string",
                            "description": (
                                "Page type: student, topic, lesson, original, "
                                "class, concept, or person."
                            ),
                        },
                        "slug": {
                            "type": "string",
                            "description": "The page slug, for example industrial-revolution.",
                        },
                    },
                    "required": ["page_type", "slug"],
                },
            },
        }

    async def execute(self, params: dict[str, Any], context: AgentContext) -> ToolResult:
        from clawed.brain.store import BrainStore

        page_type = _page_type(params.get("page_type"))
        slug = str(params.get("slug", "")).strip()
        if page_type is None:
            return ToolResult(text="ERROR: page_type must be a valid brain page type.")
        if not slug:
            return ToolResult(text="ERROR: slug is required.")

        page = BrainStore().get(page_type, slug)
        if page is None:
            return ToolResult(text=f"Brain page not found: {page_type}/{slug}")

        rendered = page.render()
        return ToolResult(
            text=rendered[:12000],
            data={
                "page_type": page.page_type,
                "slug": page.slug,
                "title": page.title,
                "timeline_count": len(page.timeline),
            },
        )


class BrainCaptureTool:
    """Capture an original teacher insight into the brain."""

    risk_level = RISK_WRITE_LOCAL

    @staticmethod
    def approval_description(params: dict[str, Any]) -> str:
        message = str(params.get("message", "")).strip()
        return (
            "Save this teacher insight into the durable teaching brain: "
            f"{message[:160]}"
        )

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "brain_capture",
                "description": (
                    "Capture an original teacher insight, classroom observation, "
                    "or pedagogical rule into the durable teaching brain. Preserves "
                    "the teacher's exact phrasing."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "message": {
                            "type": "string",
                            "description": "The insight or observation to preserve.",
                        },
                        "context": {
                            "type": "string",
                            "description": "Optional context for why this insight matters.",
                        },
                        "force": {
                            "type": "boolean",
                            "description": (
                                "Save even if the heuristic does not detect an insight."
                            ),
                        },
                    },
                    "required": ["message"],
                },
            },
        }

    async def execute(self, params: dict[str, Any], context: AgentContext) -> ToolResult:
        from clawed.brain.capture import capture_original

        message = str(params.get("message", "")).strip()
        if not message:
            return ToolResult(text="ERROR: message is required.")

        page = capture_original(
            message=message,
            context=str(params.get("context", "")).strip(),
            source_channel=context.transport or "app",
            force=bool(params.get("force", False)),
        )
        if page is None:
            return ToolResult(
                text=(
                    "I did not save that because it did not look like a durable "
                    "teaching insight. Rephrase it as an observation or set force=true."
                )
            )
        return ToolResult(
            text=f"Captured insight in brain page originals/{page.slug}.",
            data={"page_type": page.page_type, "slug": page.slug, "title": page.title},
            side_effects=[f"captured-brain-insight:{page.slug}"],
        )


class BrainDreamTool:
    """Run the overnight brain enrichment cycle on demand."""

    risk_level = RISK_WRITE_LOCAL

    @staticmethod
    def approval_description(params: dict[str, Any]) -> str:
        if bool(params.get("dry_run", False)):
            return "Run a read-only dream-cycle preview over the teaching brain."
        return (
            "Run the teaching-brain dream cycle: consolidate evidence, detect gaps, "
            "and add cross-links inside the local brain store."
        )

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "brain_dream",
                "description": (
                    "Run the dream cycle: scan the teaching brain, consolidate hot "
                    "pages, detect stale or thin knowledge, repair/cross-link related "
                    "pages, and return a report. Use dry_run for a preview."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "dry_run": {
                            "type": "boolean",
                            "description": "Report what would change without writing.",
                        },
                        "consolidate": {
                            "type": "boolean",
                            "description": (
                                "Use the configured LLM to consolidate compiled truth. "
                                "Default true."
                            ),
                        },
                    },
                },
            },
        }

    async def execute(self, params: dict[str, Any], context: AgentContext) -> ToolResult:
        from clawed.brain.dream import dream_cycle

        context.notify_progress("Running the teaching-brain dream cycle...")
        report = await dream_cycle(
            consolidate=bool(params.get("consolidate", True)),
            dry_run=bool(params.get("dry_run", False)),
        )
        return ToolResult(
            text=report.render(),
            data={
                "pages_scanned": report.pages_scanned,
                "pages_consolidated": report.pages_consolidated,
                "cross_links_added": report.cross_links_added,
                "gaps_detected": report.gaps_detected,
                "errors": report.errors,
            },
            side_effects=[] if bool(params.get("dry_run", False)) else ["brain-dream-cycle"],
        )


class CurriculumIndexTool:
    """Inspect and search the indexed curriculum knowledge base."""

    risk_level = RISK_READ_ONLY

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "curriculum_index",
                "description": (
                    "Check or search the local curriculum index built from ingested "
                    "lesson materials. Use this to verify indexing coverage before "
                    "generating teacher materials from the teacher's own corpus."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["stats", "search"],
                            "description": "Whether to show index stats or search it.",
                        },
                        "query": {
                            "type": "string",
                            "description": "Search query when action=search.",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum search results. Default 8.",
                        },
                    },
                    "required": ["action"],
                },
            },
        }

    async def execute(self, params: dict[str, Any], context: AgentContext) -> ToolResult:
        from clawed.agent_core.memory.curriculum_kb import CurriculumKB

        action = str(params.get("action", "stats")).strip().lower()
        kb = CurriculumKB()

        if action == "stats":
            stats = kb.stats(context.teacher_id)
            return ToolResult(
                text=(
                    "Curriculum index status:\n"
                    f"- documents indexed: {stats.get('doc_count', 0)}\n"
                    f"- searchable chunks: {stats.get('chunk_count', 0)}"
                ),
                data={"stats": stats},
            )

        if action == "search":
            query = str(params.get("query", "")).strip()
            if not query:
                return ToolResult(text="ERROR: query is required when action=search.")
            limit = max(1, min(int(params.get("limit") or 8), 20))
            results = kb.search(context.teacher_id, query, top_k=limit)
            if not results:
                return ToolResult(
                    text=f"No indexed curriculum results found for '{query}'.",
                    data={"results": []},
                )
            lines = [f"Indexed curriculum results for '{query}':"]
            payload = []
            for hit in results:
                title = str(hit.get("doc_title") or "Untitled")
                source = str(hit.get("source_path") or "")
                text = str(hit.get("chunk_text") or "").replace("\n", " ").strip()
                if len(text) > 220:
                    text = text[:217].rstrip() + "..."
                lines.append(f"- {title}")
                if source:
                    lines.append(f"  {source}")
                if text:
                    lines.append(f"  {text}")
                payload.append({
                    "doc_title": title,
                    "source_path": source,
                    "chunk_text": text,
                    "similarity": hit.get("similarity"),
                    "metadata": hit.get("metadata", {}),
                })
            return ToolResult(text="\n".join(lines), data={"results": payload})

        return ToolResult(text=f"Unknown curriculum_index action: {action}")
