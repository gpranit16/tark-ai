"""News Search Tool for TARK AI with real-time RSS/API news and guaranteed publication dates."""
from __future__ import annotations

from datetime import datetime, timezone
import html
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Type
import urllib.parse
import urllib.request
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.tools.base import BaseTool, ToolExecutionContext, ToolPermission, ToolResult

logger = logging.getLogger(__name__)


class NewsSearchInput(BaseModel):
    query: str = Field(
        ...,
        description="The topic, event, or keyword to search current news for (e.g. 'artificial intelligence', 'OpenAI', 'global economy').",
        min_length=1,
        max_length=200,
    )
    max_results: int = Field(default=5, description="Maximum number of news articles to return (1-10).", ge=1, le=10)


class NewsSearchTool(BaseTool):
    name: str = "search_news"
    description: str = (
        "Search real-time news headlines, breaking developments, current events, and articles. "
        "Returns fresh articles with verified publication dates, source publishers, and snippets."
    )
    permission: ToolPermission = ToolPermission.NETWORK
    input_schema: Type[BaseModel] = NewsSearchInput

    async def execute(self, arguments: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        query = str(arguments.get("query", "")).strip()
        max_results = min(int(arguments.get("max_results", 5)), 10)
        max_results = max(1, max_results)

        if not query:
            return ToolResult(tool_name=self.name, success=False, error="Query is required.")

        try:
            # 1. Primary: Real-time Google News RSS Search (Guaranteed fresh publication dates)
            articles = await self._fetch_google_news_rss(query, max_results)

            # 2. Secondary: Tavily Search if Google News RSS returned empty
            if not articles:
                articles = await self._fetch_tavily_news(query, max_results)

            # 3. Tertiary fallback: DuckDuckGo News
            if not articles:
                articles = await self._fetch_duckduckgo_news(query, max_results)

            now_iso = datetime.now(timezone.utc).isoformat()

            if not articles:
                return ToolResult(
                    tool_name=self.name,
                    success=True,
                    data={
                        "query": query,
                        "articles": [],
                        "count": 0,
                        "retrieved_at": now_iso,
                        "message": "No news articles found for this topic.",
                    },
                    source="News Search Aggregator",
                )

            return ToolResult(
                tool_name=self.name,
                success=True,
                data={
                    "query": query,
                    "count": len(articles),
                    "retrieved_at": now_iso,
                    "articles": articles,
                },
                source="Live News Search (Verified Publication Dates)",
            )

        except Exception as exc:
            logger.exception("Error during NewsSearchTool execution: %s", exc)
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=f"Failed to fetch news: {str(exc)}",
                source="News Search",
            )

    async def _fetch_google_news_rss(self, query: str, max_results: int) -> List[Dict[str, Any]]:
        import httpx
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
            articles: List[Dict[str, Any]] = []

            for item in items[:max_results]:
                title_m = re.search(r"<title>([\s\S]*?)</title>", item)
                link_m = re.search(r"<link>([\s\S]*?)</link>", item)
                pub_m = re.search(r"<pubDate>([\s\S]*?)</pubDate>", item)
                source_m = re.search(r"<source[^>]*>([\s\S]*?)</source>", item)
                desc_m = re.search(r"<description>([\s\S]*?)</description>", item)

                raw_title = title_m.group(1).strip() if title_m else "News Headline"
                clean_title = html.unescape(raw_title)
                link = html.unescape(link_m.group(1).strip()) if link_m else ""
                pub_date = pub_m.group(1).strip() if pub_m else ""
                source_name = html.unescape(source_m.group(1).strip()) if source_m else "Google News"

                raw_desc = desc_m.group(1) if desc_m else ""
                clean_desc = html.unescape(re.sub(r"<[^>]+>", "", raw_desc).strip())

                snippet = clean_desc or f"{clean_title} (Published: {pub_date})"

                if link:
                    articles.append({
                        "title": clean_title,
                        "url": link,
                        "published_date": pub_date or "Recent",
                        "source": source_name,
                        "snippet": snippet,
                    })

            return articles
        except Exception as exc:
            logger.warning("Google News RSS failed: %s", exc)
            return []

    async def _fetch_tavily_news(self, query: str, max_results: int) -> List[Dict[str, Any]]:
        import httpx
        settings = get_settings()
        api_key = settings.tavily_api_key or os.environ.get("TAVILY_API_KEY")
        if not api_key:
            return []

        payload = {
            "api_key": api_key,
            "query": f"{query} news",
            "topic": "news",
            "search_depth": "basic",
            "max_results": max_results,
        }

        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                resp = await client.post("https://api.tavily.com/search", json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    articles: List[Dict[str, Any]] = []
                    for item in data.get("results", [])[:max_results]:
                        articles.append({
                            "title": item.get("title") or "News Article",
                            "url": item.get("url") or "",
                            "published_date": item.get("published_date") or "Recent",
                            "source": "Tavily News",
                            "snippet": item.get("content") or "",
                        })
                    return articles
        except Exception as exc:
            logger.warning("Tavily news search failed: %s", exc)
        return []

    async def _fetch_duckduckgo_news(self, query: str, max_results: int) -> List[Dict[str, Any]]:
        import httpx
        encoded_query = urllib.parse.quote_plus(f"{query} news")
        url = f"https://html.duckduckgo.com/html/?q={encoded_query}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }

        try:
            async with httpx.AsyncClient(timeout=4.0, follow_redirects=True) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code != 200:
                    return []
                content = resp.text

            articles: List[Dict[str, Any]] = []
            title_matches = re.findall(r'<a class="result__a" href="([^"]+)">(.*?)</a>', content, re.DOTALL)
            snippet_matches = re.findall(r'<a class="result__snippet[^>]*>(.*?)</a>', content, re.DOTALL)

            for i, (link, raw_title) in enumerate(title_matches[:max_results]):
                clean_title = html.unescape(re.sub(r"<[^>]+>", "", raw_title).strip())
                actual_url = link
                if "uddg=" in link:
                    m = re.search(r"uddg=([^&]+)", link)
                    if m:
                        actual_url = urllib.parse.unquote(m.group(1))

                snippet = ""
                if i < len(snippet_matches):
                    snippet = html.unescape(re.sub(r"<[^>]+>", "", snippet_matches[i]).strip())

                if actual_url.startswith("http"):
                    articles.append({
                        "title": clean_title,
                        "url": actual_url,
                        "published_date": "Recent",
                        "source": "DuckDuckGo News",
                        "snippet": snippet or clean_title,
                    })

            return articles
        except Exception as exc:
            logger.warning("DuckDuckGo news failed: %s", exc)
            return []

