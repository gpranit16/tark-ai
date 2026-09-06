"""Live Web Search Tool for TARK AI with fresh publication dates and multi-provider fallback."""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
import html
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional
import urllib.parse
import urllib.request

from app.core.config import get_settings
from app.tools.base import BaseTool, ToolExecutionContext, ToolPermission, ToolResult

logger = logging.getLogger(__name__)

FRESHNESS_KEYWORDS = {"latest", "recent", "today", "news", "current", "breaking", "update", "updates", "now", "this week", "this month", "2026"}


import httpx


class BaseWebSearchProvider(ABC):
    @abstractmethod
    async def search(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        raise NotImplementedError


class TavilyWebSearchProvider(BaseWebSearchProvider):
    """High-accuracy real-time web search using Tavily AI Search API."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key

    def _get_api_key(self) -> Optional[str]:
        if self.api_key:
            return self.api_key
        try:
            return get_settings().tavily_api_key or os.environ.get("TAVILY_API_KEY")
        except Exception:
            return os.environ.get("TAVILY_API_KEY")

    async def search(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        api_key = self._get_api_key()
        if not api_key:
            return []

        lower_q = query.lower()
        is_fresh_query = any(k in lower_q for k in FRESHNESS_KEYWORDS)

        payload: Dict[str, Any] = {
            "api_key": api_key,
            "query": query,
            "search_depth": "basic",
            "include_answer": True,
            "max_results": max_results,
        }

        if is_fresh_query:
            payload["topic"] = "news"
            payload["days"] = 7

        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                resp = await client.post("https://api.tavily.com/search", json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    results: List[Dict[str, Any]] = []
                    for item in data.get("results", [])[:max_results]:
                        pub_date = item.get("published_date")
                        results.append({
                            "title": item.get("title") or "Web Page",
                            "url": item.get("url") or "",
                            "snippet": item.get("content") or "",
                            "published_date": pub_date,
                            "source": "tavily",
                        })
                    return results
        except Exception as exc:
            logger.warning("Tavily search provider failed: %s", exc)
        return []


class GoogleNewsRSSWebProvider(BaseWebSearchProvider):
    """Real-time Google News RSS search provider with guaranteed publication dates."""

    async def search(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        encoded_query = urllib.parse.quote_plus(query)
        url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-US&gl=US&ceid=US:en"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }

        try:
            async with httpx.AsyncClient(timeout=4.5, follow_redirects=True) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code != 200:
                    return []
                content = resp.text

            items = re.findall(r"<item>([\s\S]*?)</item>", content)
            results: List[Dict[str, Any]] = []

            for item in items[:max_results]:
                title_m = re.search(r"<title>([\s\S]*?)</title>", item)
                link_m = re.search(r"<link>([\s\S]*?)</link>", item)
                pub_m = re.search(r"<pubDate>([\s\S]*?)</pubDate>", item)
                source_m = re.search(r"<source[^>]*>([\s\S]*?)</source>", item)
                desc_m = re.search(r"<description>([\s\S]*?)</description>", item)

                raw_title = title_m.group(1).strip() if title_m else "Article"
                clean_title = html.unescape(raw_title)
                link = html.unescape(link_m.group(1).strip()) if link_m else ""
                pub_date = pub_m.group(1).strip() if pub_m else None
                source_name = html.unescape(source_m.group(1).strip()) if source_m else "Google News"

                raw_desc = desc_m.group(1) if desc_m else ""
                clean_desc = html.unescape(re.sub(r"<[^>]+>", "", raw_desc).strip())

                if link:
                    results.append({
                        "title": clean_title,
                        "url": link,
                        "snippet": clean_desc or f"{clean_title} — Source: {source_name}. Published: {pub_date or 'Recent'}",
                        "published_date": pub_date,
                        "source": source_name,
                    })

            return results
        except Exception as exc:
            logger.warning("GoogleNewsRSSWebProvider failed: %s", exc)
            return []


class DuckDuckGoWebSearchProvider(BaseWebSearchProvider):
    """Zero-key free web search provider using DuckDuckGo endpoint."""

    async def search(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote_plus(query.strip())
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml",
        }

        try:
            async with httpx.AsyncClient(timeout=4.0, follow_redirects=True) as client:
                response = await client.get(url, headers=headers)
                if response.status_code != 200:
                    return []
                content = response.text

            results = []
            matches = re.findall(
                r'<a class="result__url" href="([^"]+)".*?<a class="result__snippet[^>]*>(.*?)</a>',
                content,
                re.DOTALL,
            )
            title_matches = re.findall(
                r'<a class="result__a" href="([^"]+)">(.*?)</a>',
                content,
                re.DOTALL,
            )

            for i, (link, raw_title) in enumerate(title_matches[:max_results]):
                clean_title = re.sub(r"<[^>]+>", "", raw_title).strip()
                clean_title = html.unescape(clean_title)

                actual_url = link
                if "uddg=" in link:
                    m = re.search(r"uddg=([^&]+)", link)
                    if m:
                        actual_url = urllib.parse.unquote(m.group(1))

                snippet = ""
                if i < len(matches):
                    snippet = re.sub(r"<[^>]+>", "", matches[i][1]).strip()
                    snippet = html.unescape(snippet)

                results.append({
                    "title": clean_title or f"Result {i+1}",
                    "url": actual_url,
                    "snippet": snippet or clean_title,
                    "published_date": None,
                    "source": "duckduckgo",
                })

            return results
        except Exception as exc:
            logger.warning("DuckDuckGoWebSearchProvider failed: %s", exc)
            return []


class CompositeWebSearchEngine(BaseWebSearchProvider):
    """Multi-tiered search engine attempting Google News RSS, Tavily, and DuckDuckGo."""

    def __init__(self):
        self.providers: List[BaseWebSearchProvider] = [
            GoogleNewsRSSWebProvider(),
            TavilyWebSearchProvider(),
            DuckDuckGoWebSearchProvider(),
        ]

    async def search(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        for provider in self.providers:
            try:
                results = await provider.search(query, max_results=max_results)
                if results:
                    return results
            except Exception as e:
                logger.debug("Provider %s failed: %s", provider.__class__.__name__, e)

        return []



class WebSearchTool(BaseTool):
    name = "web_search"
    description = (
        "Search the live public web for current events, fresh facts, recent developments, documentation, and external knowledge. "
        "Returns fresh search results with source URLs, snippets, and actual publication dates."
    )
    category = "search"
    permissions = [ToolPermission.NETWORK]

    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query keywords to find fresh, relevant information on the web.",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of search results to return (default: 5, max: 10).",
                "default": 5,
            },
        },
        "required": ["query"],
    }

    def __init__(self, provider: BaseWebSearchProvider | None = None) -> None:
        self.provider = provider or CompositeWebSearchEngine()

    async def execute(self, arguments: dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        query = str(arguments.get("query", "")).strip()
        if not query:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error="Search query cannot be empty",
                source="validation",
            )

        max_results = int(arguments.get("max_results", 5))
        max_results = max(1, min(max_results, 10))

        try:
            results = await self.provider.search(query, max_results=max_results)
            now_iso = datetime.now(timezone.utc).isoformat()

            if not results:
                return ToolResult(
                    tool_name=self.name,
                    success=True,
                    data={
                        "query": query,
                        "count": 0,
                        "results": [],
                        "retrieved_at": now_iso,
                        "message": "No direct search results returned by provider for this query.",
                    },
                    source="web_search_engine",
                )

            return ToolResult(
                tool_name=self.name,
                success=True,
                data={
                    "query": query,
                    "count": len(results),
                    "retrieved_at": now_iso,
                    "results": results,
                },
                source="live_web_search",
            )
        except Exception as exc:
            logger.exception("WebSearchTool execution error: %s", exc)
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=f"Web search error: {str(exc)}",
                source="web_search",
            )
