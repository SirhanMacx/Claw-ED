"""Browser tool — Ed can navigate the web to find sources and information."""

from __future__ import annotations

import logging
from typing import Any

from clawed.agent_core.context import AgentContext, ToolResult

logger = logging.getLogger(__name__)

_MAX_TEXT_LENGTH = 8000


class BrowserNavigateTool:
    """Navigate to a URL and read the page text."""

    risk_level = "network_call"

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "browse_web",
                "description": (
                    "Navigate to a URL and read the page content. "
                    "Returns the main text content of the page. "
                    "Use for finding primary sources, current events, "
                    "educational resources, images, and verifying facts."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "The URL to navigate to",
                        },
                    },
                    "required": ["url"],
                },
            },
        }

    async def execute(
        self, params: dict[str, Any], context: AgentContext
    ) -> ToolResult:
        url = params.get("url", "").strip()
        if not url:
            return ToolResult(text="ERROR: url is required")

        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"

        try:
            text = await _fetch_page_text(url)
            if not text or len(text.strip()) < 20:
                return ToolResult(text=f"Page at {url} returned no readable content.")
            return ToolResult(
                text=f"Content from {url}:\n\n{text[:_MAX_TEXT_LENGTH]}",
                data={"url": url, "length": len(text)},
            )
        except Exception as e:
            logger.warning("Browser navigate failed: %s", e)
            return ToolResult(text=f"Could not load {url}: {e}")


class BrowserSearchTool:
    """Search the web for information."""

    risk_level = "network_call"

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "web_search",
                "description": (
                    "Search the web for information. Returns search result "
                    "titles, URLs, and snippets. Use for finding primary "
                    "sources, current events, educational materials, and "
                    "fact-checking."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The search query",
                        },
                    },
                    "required": ["query"],
                },
            },
        }

    async def execute(
        self, params: dict[str, Any], context: AgentContext
    ) -> ToolResult:
        query = params.get("query", "").strip()
        if not query:
            return ToolResult(text="ERROR: query is required")

        try:
            results = await _search_web(query)
            if not results:
                return ToolResult(text=f"No results found for: {query}")

            lines = [f"Search results for: {query}\n"]
            for i, r in enumerate(results[:8], 1):
                title = r.get("title", "Untitled")
                url = r.get("url", "")
                snippet = r.get("snippet", "")[:200]
                lines.append(f"{i}. {title}\n   {url}\n   {snippet}\n")

            return ToolResult(text="\n".join(lines))
        except Exception as e:
            logger.warning("Web search failed: %s", e)
            return ToolResult(text=f"Search failed: {e}")


async def _fetch_page_text(url: str, timeout_ms: int = 15000) -> str:
    """Fetch page text using Playwright headless browser."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        # Fallback to httpx for simple pages
        return await _fetch_with_httpx(url)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
            # Try to get main article content first
            text = await page.evaluate("""() => {
                // Try article/main content first
                const article = document.querySelector('article') ||
                                document.querySelector('main') ||
                                document.querySelector('[role="main"]');
                if (article) return article.innerText;
                // Fall back to body
                return document.body.innerText;
            }""")
            return text or ""
        finally:
            await browser.close()


async def _fetch_with_httpx(url: str) -> str:
    """Simple HTTP fetch fallback when Playwright unavailable."""
    import httpx
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        resp = await client.get(url, headers={
            "User-Agent": "Mozilla/5.0 (compatible; Claw-ED/4.4; Educational Agent)"
        })
        resp.raise_for_status()
        # Basic HTML to text
        text = resp.text
        import re
        text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text


async def _search_web(query: str) -> list[dict]:
    """Search using DuckDuckGo HTML (no API key needed)."""
    import re
    import urllib.parse

    import httpx

    search_url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"

    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        resp = await client.get(search_url, headers={
            "User-Agent": "Mozilla/5.0 (compatible; Claw-ED/4.4; Educational Agent)"
        })
        resp.raise_for_status()
        html = resp.text

    results = []
    # Parse DuckDuckGo HTML results
    # Results are in <a class="result__a" ...> tags
    pattern = r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>'
    snippet_pattern = r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>'

    links = re.findall(pattern, html, re.DOTALL)
    snippets = re.findall(snippet_pattern, html, re.DOTALL)

    for i, (url, title) in enumerate(links[:10]):
        # Clean HTML from title
        title = re.sub(r"<[^>]+>", "", title).strip()
        # DuckDuckGo wraps URLs in a redirect
        if "uddg=" in url:
            url_match = re.search(r"uddg=([^&]+)", url)
            if url_match:
                url = urllib.parse.unquote(url_match.group(1))

        snippet = ""
        if i < len(snippets):
            snippet = re.sub(r"<[^>]+>", "", snippets[i]).strip()

        results.append({"title": title, "url": url, "snippet": snippet})

    return results
