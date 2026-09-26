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

FRESHNESS_KEYWORDS = {
    "latest", "recent", "today", "news", "current", "breaking", "update", "updates",
    "now", "this week", "this month", "2025", "2026", "score", "winner", "match",
    "price", "ceo", "release", "released", "announcement"
}

SPAM_OR_SPECULATIVE_DOMAINS = {
    "hidekazu-konishi.com",
    "evertune.ai",
    "scriptbyai.com",
    "local-ai-zone.github.io",
    "releasebot.io",
    "gracker.ai",
    "llm-stats.com",
    "thursdai.news",
    "felloai.com",
}


import httpx


class BaseWebSearchProvider(ABC):
    @abstractmethod
    async def search(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        raise NotImplementedError


class TavilyWebSearchProvider(BaseWebSearchProvider):
    """High-accuracy real-time web search using Tavily AI Search API."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.last_answer: Optional[str] = None

    def _get_api_key(self) -> Optional[str]:
        if self.api_key:
            return self.api_key
        try:
            val = get_settings().tavily_api_key or os.environ.get("TAVILY_API_KEY")
            if val:
                return val
        except Exception:
            pass
        val = os.environ.get("TAVILY_API_KEY")
        if val:
            return val
        # Dynamic fallback: check local .env files if not in environment
        for env_path in [".env", "backend/.env", "../.env"]:
            if os.path.exists(env_path):
                try:
                    with open(env_path, "r", encoding="utf-8") as f:
                        for line in f:
                            line_s = line.strip()
                            if line_s.startswith("TAVILY_API_KEY="):
                                k = line_s.split("=", 1)[1].strip().strip('"\'')
                                if k:
                                    return k
                except Exception:
                    pass
        return None

    @staticmethod
    def _clean_query(q: str) -> str:
        cleaned = q.strip()
        # 1. Clean Hinglish/Hindi noise and inspection directives
        hinglish_noise = [
            r"^\s*(?:bhai\s+)?(?:please\s+)?(?:dhang|dhng|hng|ache|acche|sahi|theek|dobara|fir\s+se)\s+se\s+dekh(?:iye|o)?\s*",
            r"^\s*(?:bhai\s+)?(?:dekh|dekho|check\s+karo|check\s+kr|khojo|dhundho)\s*",
            r"\s*(?:dekh\s+ke\s+batao|search\s+karke\s+batao|dhundh\s+ke\s+batao|batao|bata|bataiye|search\s+karo|search\s+kro)\s*$",
            r"\b(?:kiska\s+hai|kiske\s+liye\s+hai|ke\s+baare\s+me)\b",
            r"\b(?:hai|tha|thi|h)\b",
            r"\b(?:bhai|yaar|please)\b",
        ]
        for pat in hinglish_noise:
            cleaned = re.sub(pat, " ", cleaned, flags=re.IGNORECASE)

        # 2. Clean English search prefix noise
        noise_patterns = [
            r"^(?:please\s+)?search(\s+and\s+tell(\s+me)?)?(\s+for|\s+about)?\s*",
            r"^(?:can\s+you\s+)?search(\s+the\s+web(\s+for)?)?\s*",
            r"^(?:tell\s+me|what\s+is|which\s+is)\s+(?:the\s+)?",
        ]
        for pat in noise_patterns:
            cleaned = re.sub(pat, " ", cleaned, flags=re.IGNORECASE)

        # 3. Normalize common conversational tech terms
        cleaned = re.sub(r"\bopen\s+ai\b", "OpenAI", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bdevloper\b", "developer", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bye\b", "", cleaned, flags=re.IGNORECASE)
        cleaned = " ".join(cleaned.split()).strip()

        return cleaned or q.strip()

    async def search(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        self.last_answer = None
        api_key = self._get_api_key()
        if not api_key:
            logger.debug("Tavily API key not found; skipping Tavily search provider.")
            return []

        effective_query = self._clean_query(query)
        lower_q = effective_query.lower()
        is_fresh_query = any(k in lower_q for k in FRESHNESS_KEYWORDS)

        payload: Dict[str, Any] = {
            "api_key": api_key,
            "query": effective_query,
            "search_depth": "advanced" if is_fresh_query else "basic",
            "include_answer": True,
            "exclude_domains": list(SPAM_OR_SPECULATIVE_DOMAINS),
            "max_results": min(max_results * 2, 10),
        }

        try:
            async with httpx.AsyncClient(timeout=7.5) as client:
                resp = await client.post("https://api.tavily.com/search", json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    raw_answer = data.get("answer")
                    # Sanitize hallucinated or speculative answers
                    if raw_answer:
                        hallucination_indicators = [
                            "inventors at amazon", "sol and luna", "gpt-6 astra",
                            "gpt-5.6", "claude fable", "tier sol", "tier luna"
                        ]
                        if not any(h in raw_answer.lower() for h in hallucination_indicators):
                            self.last_answer = raw_answer

                    results: List[Dict[str, Any]] = []
                    for item in data.get("results", []):
                        url = item.get("url") or ""
                        if any(spam in url.lower() for spam in SPAM_OR_SPECULATIVE_DOMAINS):
                            continue
                        pub_date = item.get("published_date")
                        results.append({
                            "title": item.get("title") or "Web Page",
                            "url": url,
                            "snippet": item.get("content") or "",
                            "published_date": pub_date,
                            "source": "tavily",
                        })
                        if len(results) >= max_results:
                            break

                    logger.info("Tavily returned %d results for query: %r (has_answer=%s)", len(results), query[:50], bool(self.last_answer))
                    return results
                else:
                    logger.warning("Tavily search returned status %d: %s", resp.status_code, resp.text[:200])
        except Exception as exc:
            logger.warning("Tavily search provider failed: %s", exc)
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
            async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as client:
                response = await client.get(url, headers=headers)
                if response.status_code != 200:
                    return []
                content = response.text

            title_matches = re.findall(
                r'<a[^>]*class="[^"]*result__a[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                content,
                re.DOTALL,
            )
            snippet_matches = re.findall(
                r'<a[^>]*class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>',
                content,
                re.DOTALL,
            )

            results = []
            for i, (link, raw_title) in enumerate(title_matches[:max_results]):
                clean_title = re.sub(r"<[^>]+>", "", raw_title).strip()
                clean_title = html.unescape(clean_title)

                actual_url = link
                if "uddg=" in link:
                    m = re.search(r"uddg=([^&]+)", link)
                    if m:
                        actual_url = urllib.parse.unquote(m.group(1))

                snippet = ""
                if i < len(snippet_matches):
                    snippet = re.sub(r"<[^>]+>", "", snippet_matches[i]).strip()
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


class WikipediaWebSearchProvider(BaseWebSearchProvider):
    """Zero-key authoritative encyclopedia and factual entity search using Wikipedia API."""

    async def search(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        clean_q = query.strip()
        encoded = urllib.parse.quote_plus(clean_q)
        url = (
            f"https://en.wikipedia.org/w/api.php?action=query&list=search"
            f"&srsearch={encoded}&format=json&utf8=1&srlimit={max_results}"
        )
        headers = {
            "User-Agent": "TarkAI-Bot/1.0 (https://tarkai.dev; contact@tarkai.dev)",
            "Accept": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=4.0, follow_redirects=True) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code != 200:
                    return []
                data = resp.json()

            items = data.get("query", {}).get("search", [])
            results: List[Dict[str, Any]] = []
            for item in items[:max_results]:
                title = item.get("title", "")
                raw_snippet = item.get("snippet", "")
                clean_snippet = html.unescape(re.sub(r"<[^>]+>", "", raw_snippet).strip())
                page_url = f"https://en.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}"
                results.append({
                    "title": title,
                    "url": page_url,
                    "snippet": clean_snippet or title,
                    "published_date": None,
                    "source": "wikipedia",
                })
            return results
        except Exception as exc:
            logger.debug("WikipediaWebSearchProvider failed: %s", exc)
            return []


class GoogleNewsRSSWebProvider(BaseWebSearchProvider):
    """Real-time Google News RSS search provider with guaranteed publication dates and keyword filtering."""

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
            raw_results: List[Dict[str, Any]] = []

            for item in items[:max_results * 2]:
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
                    raw_results.append({
                        "title": clean_title,
                        "url": link,
                        "snippet": clean_desc or f"{clean_title} — Source: {source_name}. Published: {pub_date or 'Recent'}",
                        "published_date": pub_date,
                        "source": source_name,
                    })

            # Filter items for query relevance to prevent unrelated random news
            query_words = set(re.findall(r"\b[A-Za-z0-9]{3,}\b", query.lower())) - {
                "what", "where", "when", "which", "whose", "whom", "this", "that",
                "search", "latest", "recent", "about", "find", "online", "news", "total", "scored"
            }
            if query_words:
                filtered = []
                for r in raw_results:
                    txt = (r["title"] + " " + r["snippet"]).lower()
                    if any(w in txt for w in query_words):
                        filtered.append(r)
                if filtered:
                    return filtered[:max_results]

            return raw_results[:max_results]
        except Exception as exc:
            logger.warning("GoogleNewsRSSWebProvider failed: %s", exc)
            return []


class CompositeWebSearchEngine(BaseWebSearchProvider):
    """Multi-tiered search engine prioritizing Tavily AI, with DuckDuckGo, Wikipedia, and Google News RSS fallbacks."""

    def __init__(self):
        self.tavily = TavilyWebSearchProvider()
        self.duckduckgo = DuckDuckGoWebSearchProvider()
        self.wikipedia = WikipediaWebSearchProvider()
        self.google_news = GoogleNewsRSSWebProvider()
        self.providers: List[BaseWebSearchProvider] = [
            self.tavily,
            self.duckduckgo,
            self.wikipedia,
            self.google_news,
        ]

    @property
    def last_answer(self) -> Optional[str]:
        return self.tavily.last_answer

    async def search(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        seen_urls: set[str] = set()

        # 1. Primary: Tavily AI Search (rich citations + live web with spam filtered)
        try:
            tavily_results = await self.tavily.search(query, max_results=max_results)
            for r in tavily_results:
                u = r.get("url") or ""
                if u and u not in seen_urls:
                    seen_urls.add(u)
                    results.append(r)
        except Exception as e:
            logger.warning("Primary Tavily search failed: %s", e)

        # 2. Authoritative Wikipedia grounding for tech, entities, companies, and models
        lower_q = query.lower()
        needs_encyclopedia = any(k in lower_q for k in [
            "openai", "gpt", "o1", "o3", "claude", "gemini", "deepseek", "sora",
            "model", "company", "ceo", "who is", "what is", "founder", "developer", "history", "release"
        ])
        if needs_encyclopedia or len(results) < 2:
            try:
                wiki_results = await self.wikipedia.search(query, max_results=2)
                for w in wiki_results:
                    u = w.get("url") or ""
                    if u and u not in seen_urls:
                        seen_urls.add(u)
                        results.append(w)
            except Exception as e:
                logger.debug("Wikipedia supplemental search failed: %s", e)

        # 3. Fallback to DuckDuckGo if still insufficient results
        if len(results) < 2:
            try:
                ddg_results = await self.duckduckgo.search(query, max_results=max_results)
                for d in ddg_results:
                    u = d.get("url") or ""
                    if u and u not in seen_urls:
                        seen_urls.add(u)
                        results.append(d)
            except Exception as e:
                logger.debug("DuckDuckGo search failed: %s", e)

        # 4. Fallback to Google News RSS for fresh breaking events
        if len(results) < 2:
            try:
                news_results = await self.google_news.search(query, max_results=max_results)
                for n in news_results:
                    u = n.get("url") or ""
                    if u and u not in seen_urls:
                        seen_urls.add(u)
                        results.append(n)
            except Exception as e:
                logger.debug("Google News RSS search failed: %s", e)

        return results[:max_results]



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
        query = str(
            arguments.get("query")
            or arguments.get("input")
            or arguments.get("q")
            or arguments.get("search_query")
            or (arguments.get("parameters", {}).get("query") if isinstance(arguments.get("parameters"), dict) else "")
            or ""
        ).strip()
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
            direct_answer = getattr(self.provider, "last_answer", None)
            if not direct_answer and hasattr(self.provider, "providers"):
                for p in getattr(self.provider, "providers", []):
                    if getattr(p, "last_answer", None):
                        direct_answer = p.last_answer
                        break

            if not results:
                return ToolResult(
                    tool_name=self.name,
                    success=True,
                    data={
                        "query": query,
                        "direct_answer": direct_answer,
                        "count": 0,
                        "results": [],
                        "retrieved_at": now_iso,
                        "message": "No direct search results returned by provider for this query.",
                    },
                    source="web_search_engine",
                )

            is_tavily = any(r.get("source") == "tavily" for r in results)
            source_label = "tavily" if is_tavily else "live_web_search"

            return ToolResult(
                tool_name=self.name,
                success=True,
                data={
                    "query": query,
                    "direct_answer": direct_answer,
                    "count": len(results),
                    "retrieved_at": now_iso,
                    "results": results,
                },
                source=source_label,
            )
        except Exception as exc:
            logger.exception("WebSearchTool execution error: %s", exc)
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=f"Web search error: {str(exc)}",
                source="web_search",
            )
