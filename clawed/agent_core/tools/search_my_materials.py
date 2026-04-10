"""Tool: search_my_materials — search the teacher's uploaded curriculum files.

This is the key tool that makes Claw-ED curriculum-aware. The agent calls
this before generating to find relevant prior work in the teacher's own
uploaded materials. Now includes asset-level awareness (slideshows, handouts,
YouTube links) alongside text chunk search.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from clawed.agent_core.context import AgentContext, ToolResult

logger = logging.getLogger(__name__)


class SearchMyMaterialsTool:
    """Search the teacher's curriculum knowledge base for relevant content."""

    risk_level = "read_only"

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "search_my_materials",
                "description": (
                    "Search the teacher's uploaded curriculum files for relevant "
                    "content. Use this BEFORE generating lessons, units, or materials "
                    "to ground your output in the teacher's own prior work. Returns "
                    "matching files (slideshows, handouts, assessments), YouTube links, "
                    "and text excerpts with source file attribution."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": (
                                "What to search for — a topic, concept, or question. "
                                "Example: 'Civil War causes', 'photosynthesis lab', "
                                "'fractions worksheet'"
                            ),
                        },
                        "top_k": {
                            "type": "integer",
                            "description": "Maximum results to return (default 5)",
                            "default": 5,
                        },
                    },
                    "required": ["query"],
                },
            },
        }

    async def execute(self, params: dict[str, Any], context: AgentContext) -> ToolResult:
        query = params["query"]
        top_k = params.get("top_k", 5)
        teacher_id = context.teacher_id

        lines: list[str] = []

        # ── Asset-level search (files, YouTube links) ──────────────
        try:
            from clawed.asset_registry import AssetRegistry

            registry = AssetRegistry()
            assets = registry.search_assets(teacher_id, query, top_k=top_k)
            # Fallback: if no results with this teacher_id, try without
            # teacher_id filter. This handles cross-transport mismatches
            # (e.g. files ingested via Telegram ID, searched via CLI "local-teacher").
            if not assets:
                assets = registry.search_assets("", query, top_k=top_k)
            yt_links = registry.get_youtube_links(teacher_id, query, top_k=3)
            if not yt_links:
                yt_links = registry.get_youtube_links("", query, top_k=3)

            if assets:
                lines.append("EXISTING MATERIALS:\n")
                for i, a in enumerate(assets, 1):
                    type_label = a["material_type"].replace("_", " ").title()
                    extras: list[str] = []
                    if a.get("slide_count"):
                        extras.append(f"{a['slide_count']} slides")
                    if a.get("image_count"):
                        extras.append(f"{a['image_count']} images")
                    yt_raw = a.get("youtube_urls", [])
                    yt_list = json.loads(yt_raw) if isinstance(yt_raw, str) else yt_raw
                    yt_count = len(yt_list)
                    if yt_count:
                        extras.append(f"{yt_count} YouTube links")
                    extra_str = f" ({', '.join(extras)})" if extras else ""
                    lines.append(f'  {i}. [{type_label}] "{a["title"]}"{extra_str}\n     File: {a["filename"]}\n')

            if yt_links:
                lines.append("YOUTUBE LINKS IN YOUR FILES:\n")
                for link in yt_links:
                    lines.append(f'  - {link["url"]} (from "{link["from_file"]}")\n')

        except Exception as e:
            logger.warning("Asset search failed: %s", e)

        # ── Chunk-level search (text excerpts) ─────────────────────
        try:
            from clawed.agent_core.memory.curriculum_kb import CurriculumKB

            kb = CurriculumKB()
            results = kb.search(teacher_id, query, top_k=top_k)
            # Fallback: cross-transport teacher_id mismatch
            if not results:
                results = kb.search_all_teachers(query, top_k=top_k)

            if not results and not lines:
                # Check stats for both the transport-specific ID and "default"
                # (CLI ingest stores chunks under "default")
                stats = kb.stats(teacher_id)
                if stats["doc_count"] == 0 and teacher_id != "default":
                    stats = kb.stats("default")
                if stats["doc_count"] == 0:
                    return ToolResult(
                        text="No curriculum files uploaded yet. Ask the teacher "
                        "to share their lesson plans, handouts, or other "
                        "teaching materials so you can reference them."
                    )
                return ToolResult(text=f"No matches found for '{query}' in {stats['doc_count']} uploaded documents.")

            if results:
                lines.append("RELEVANT EXCERPTS:\n")
                for i, r in enumerate(results, 1):
                    source = r["doc_title"]
                    if r.get("source_path"):
                        fname = Path(r["source_path"]).name
                        source = f"{r['doc_title']} ({fname})"
                    sim_pct = int(r["similarity"] * 100)
                    text_preview = r["chunk_text"][:300]
                    if len(r["chunk_text"]) > 300:
                        text_preview += "..."
                    lines.append(f"  {i}. From '{source}' ({sim_pct}% match):\n     {text_preview}\n")

        except Exception as e:
            if not lines:
                return ToolResult(text=f"Failed to search curriculum files: {e}")

        if lines:
            header = f'Found materials related to "{query}":\n\n'
            lines.append("\nWould you like me to use these existing materials, enhance them, or create something new?")
            return ToolResult(
                text=header + "\n".join(lines),
                data={"query": query},
            )

        return ToolResult(text=f"No materials found for '{query}'.")
