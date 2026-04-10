"""Research tool — Ed can do multi-step web research on any topic."""

from __future__ import annotations

import logging
from typing import Any

from clawed.agent_core.context import AgentContext, ToolResult

logger = logging.getLogger(__name__)


class ResearchTopicTool:
    """Multi-step web research for lesson preparation."""

    risk_level = "network_call"

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "research_topic",
                "description": (
                    "Research a topic for lesson preparation. Searches the web, "
                    "finds primary sources, articles, and images relevant to the "
                    "topic. Returns structured results with citations. "
                    "Good for: finding primary sources for history lessons, "
                    "current events connections, scientific articles, images."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "topic": {
                            "type": "string",
                            "description": "The topic to research (e.g., 'causes of the French Revolution')",
                        },
                        "subject": {
                            "type": "string",
                            "description": "School subject (e.g., 'US History', 'Biology')",
                        },
                        "focus": {
                            "type": "string",
                            "enum": ["primary_sources", "current_events", "images", "academic", "general"],
                            "description": "What kind of sources to prioritize",
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
        focus = params.get("focus", "general")

        try:
            from clawed.agent_core.tools.browser import _fetch_page_text, _search_web

            # Build targeted search queries
            queries = _build_research_queries(topic, subject, focus)

            all_results = []
            for query in queries[:3]:  # Max 3 searches
                results = await _search_web(query)
                all_results.extend(results[:5])

            if not all_results:
                return ToolResult(text=f"No results found for research on: {topic}")

            # Deduplicate by URL
            seen_urls = set()
            unique = []
            for r in all_results:
                url = r.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    unique.append(r)

            # Try to read the top 2 results for deeper content
            detailed = []
            for r in unique[:2]:
                url = r.get("url", "")
                if not url:
                    continue
                try:
                    text = await _fetch_page_text(url, timeout_ms=10000)
                    if text and len(text.strip()) > 100:
                        detailed.append(
                            {
                                "title": r.get("title", ""),
                                "url": url,
                                "excerpt": text[:2000],
                            }
                        )
                except Exception:
                    pass

            # Build structured result
            parts = [f"Research results for: {topic}\n"]

            if detailed:
                parts.append("## Detailed Sources")
                for d in detailed:
                    parts.append(f"\n### {d['title']}")
                    parts.append(f"URL: {d['url']}")
                    parts.append(f"{d['excerpt'][:1500]}\n")

            parts.append("\n## Additional Sources")
            for i, r in enumerate(unique[:8], 1):
                title = r.get("title", "Untitled")
                url = r.get("url", "")
                snippet = r.get("snippet", "")[:200]
                parts.append(f"{i}. {title}")
                parts.append(f"   {url}")
                if snippet:
                    parts.append(f"   {snippet}")

            return ToolResult(
                text="\n".join(parts),
                data={"topic": topic, "sources_found": len(unique)},
            )

        except Exception as e:
            logger.error("Research failed: %s", e)
            return ToolResult(text=f"Research on '{topic}' failed: {e}")


def _build_research_queries(topic: str, subject: str, focus: str) -> list[str]:
    """Build targeted search queries based on research focus."""
    base = topic
    if subject:
        base = f"{subject} {topic}"

    queries = []
    if focus == "primary_sources":
        queries = [
            f"{base} primary source document",
            f"{base} original text historical source",
            f"{base} archive.org",
        ]
    elif focus == "current_events":
        queries = [
            f"{base} current events today",
            f"{base} recent news education",
        ]
    elif focus == "images":
        queries = [
            f"{base} educational diagram",
            f"{base} historical image photograph",
        ]
    elif focus == "academic":
        queries = [
            f"{base} academic article",
            f"{base} scholarly research education",
        ]
    else:
        queries = [
            f"{base} educational resource",
            f"{base} lesson materials",
            base,
        ]

    return queries
