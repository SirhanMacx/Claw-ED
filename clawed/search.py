"""Web search for teachers — Tavily API with DuckDuckGo fallback."""

from __future__ import annotations

import json
import os
import re
from typing import Optional

import httpx

from clawed.models import TeacherPersona


def _get_tavily_key() -> Optional[str]:
    """Read TAVILY_API_KEY from env or ~/.eduagent/config.json."""
    key = os.environ.get("TAVILY_API_KEY")
    if key:
        return key
    from clawed.paths import data_dir

    config_path = data_dir() / "config.json"
    if config_path.exists():
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
            return data.get("tavily_api_key") or data.get("TAVILY_API_KEY")
        except (json.JSONDecodeError, OSError):
            pass
    return None


def _add_edu_framing(query: str, persona: Optional[TeacherPersona] = None) -> str:
    """Add educational context to a raw search query."""
    # Strip obvious command prefixes
    cleaned = re.sub(r"^(search for|look up|find)\s+", "", query, flags=re.IGNORECASE).strip()
    parts = [cleaned, "teaching resource"]
    if persona and persona.grade_levels:
        parts.append(f"grade {persona.grade_levels[0]}")
    if persona and persona.subject_area:
        parts.append(persona.subject_area)
    return " ".join(parts)


def _format_results(results: list[dict], max_results: int = 3) -> str:
    """Format search results as a Telegram-friendly bullet list."""
    if not results:
        return "No results found. Try rephrasing your query."
    lines = ["🔍 *Search Results*", ""]
    for item in results[:max_results]:
        title = item.get("title", "Untitled")
        url = item.get("url", "")
        snippet = item.get("snippet", item.get("content", ""))[:200]
        lines.append(f"• *{title}*")
        if snippet:
            lines.append(f"  {snippet}")
        if url:
            lines.append(f"  🔗 {url}")
        lines.append("")
    return "\n".join(lines).rstrip()


async def _search_tavily(query: str, api_key: str, max_results: int = 3) -> list[dict]:
    """Search using the Tavily API."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            "https://api.tavily.com/search",
            json={
                "api_key": api_key,
                "query": query,
                "max_results": max_results,
                "search_depth": "basic",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return [
            {"title": r.get("title", ""), "url": r.get("url", ""), "snippet": r.get("content", "")}
            for r in data.get("results", [])
        ]


async def _search_duckduckgo(query: str, max_results: int = 3) -> list[dict]:
    """Scrape DuckDuckGo HTML-only endpoint as a fallback."""
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        resp = await client.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query},
            headers={"User-Agent": "Mozilla/5.0 (compatible; Claw-ED/0.1)"},
        )
        resp.raise_for_status()
        html = resp.text

    results: list[dict] = []
    # Parse result blocks: <a class="result__a" href="...">title</a>
    # and <a class="result__snippet">snippet</a>
    link_pattern = re.compile(r'<a\s+[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>', re.DOTALL)
    snippet_pattern = re.compile(r'<a\s+[^>]*class="result__snippet"[^>]*>(.*?)</a>', re.DOTALL)

    links = link_pattern.findall(html)
    snippets = snippet_pattern.findall(html)

    for i, (url, raw_title) in enumerate(links[:max_results]):
        title = re.sub(r"<[^>]+>", "", raw_title).strip()
        snippet = ""
        if i < len(snippets):
            snippet = re.sub(r"<[^>]+>", "", snippets[i]).strip()
        # DuckDuckGo wraps URLs in a redirect; extract the actual URL
        actual_url = url
        uddg_match = re.search(r"uddg=([^&]+)", url)
        if uddg_match:
            from urllib.parse import unquote

            actual_url = unquote(uddg_match.group(1))
        results.append({"title": title, "url": actual_url, "snippet": snippet})

    return results


async def search_for_teacher(query: str, persona: Optional[TeacherPersona] = None) -> str:
    """Search web and return Telegram-formatted results for a teacher query.

    Automatically adds educational framing to queries.
    Uses Tavily API if key is available, otherwise DuckDuckGo scraping.
    """
    framed_query = _add_edu_framing(query, persona)
    api_key = _get_tavily_key()

    try:
        if api_key:
            results = await _search_tavily(framed_query, api_key)
        else:
            results = await _search_duckduckgo(framed_query)
    except httpx.HTTPError:
        return "Search is temporarily unavailable. Please try again in a moment."

    return _format_results(results)


async def search_standards_web(grade: str, subject: str) -> str:
    """Search specifically for curriculum standards."""
    query = f"{subject} curriculum standards grade {grade} CCSS NGSS"
    api_key = _get_tavily_key()

    try:
        if api_key:
            results = await _search_tavily(query, api_key)
        else:
            results = await _search_duckduckgo(query)
    except httpx.HTTPError:
        return "Standards search is temporarily unavailable."

    if not results:
        return (
            f"No standards found for grade {grade} {subject} online. "
            f"Use `standards list --grade {grade} --subject {subject}` for built-in standards."
        )

    lines = [f"📋 *Online Standards: Grade {grade} {subject}*", ""]
    for item in results[:3]:
        title = item.get("title", "")
        url = item.get("url", "")
        lines.append(f"• *{title}*")
        if url:
            lines.append(f"  🔗 {url}")
        lines.append("")
    return "\n".join(lines).rstrip()


async def find_lesson_resource(topic: str, grade: str) -> str:
    """Find a specific teaching resource (video, article, activity) for a topic."""
    query = f"{topic} lesson activity grade {grade} classroom resource"
    api_key = _get_tavily_key()

    try:
        if api_key:
            results = await _search_tavily(query, api_key)
        else:
            results = await _search_duckduckgo(query)
    except httpx.HTTPError:
        return "Resource search is temporarily unavailable."

    if not results:
        return f"No resources found for {topic} (grade {grade}). Try a more specific query."

    lines = [f"📎 *Resources for: {topic} (Grade {grade})*", ""]
    for item in results[:3]:
        title = item.get("title", "")
        url = item.get("url", "")
        snippet = item.get("snippet", "")[:150]
        lines.append(f"• *{title}*")
        if snippet:
            lines.append(f"  {snippet}")
        if url:
            lines.append(f"  🔗 {url}")
        lines.append("")
    return "\n".join(lines).rstrip()
