"""Live Web Search Tool for TARK AI with fresh publication dates and multi-provider fallback."""
from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from datetime import datetime, timezone
import html
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple
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


def normalize_url(u: str) -> str:
    """Canonicalize URLs for reliable deduplication across different search providers."""
    try:
        parsed = urllib.parse.urlparse(u.strip())
        scheme = parsed.scheme.lower() or "https"
        netloc = parsed.netloc.lower().split(":")[0]
        if netloc.startswith("www."):
            netloc = netloc[4:]
        path = parsed.path.rstrip("/")
        # Filter out tracking and cache parameters
        query_params = urllib.parse.parse_qsl(parsed.query)
        clean_params = [
            (k, v) for k, v in query_params
            if not k.lower().startswith(("utm_", "ref", "fbclid", "gclid", "source", "feature", "spm"))
        ]
        clean_query = urllib.parse.urlencode(sorted(clean_params))
        return f"{scheme}://{netloc}{path}" + (f"?{clean_query}" if clean_query else "")
    except Exception:
        return u.strip().lower()


class DomainAuthorityRanker:
    """Algorithmic domain authority and trust scoring engine.
    Ranks sources across 5 trust tiers based on structural domain authority,
    institution types, wire services, and dynamic entity domain matching.
    """

    TIER_1_TLDS = (".gov", ".edu", ".mil")
    TIER_1_DOMAINS = {
        "wikipedia.org",
        "en.wikipedia.org",
        "britannica.com",
        "arxiv.org",
        "doi.org",
        "nature.com",
        "science.org",
        "ncbi.nlm.nih.gov",
        "pnas.org",
        "cell.com",
        "oscars.org",
        "nobelprize.org",
    }

    TIER_2_DOMAINS = {
        "reuters.com",
        "apnews.com",
        "bloomberg.com",
        "bbc.com",
        "bbc.co.uk",
        "wsj.com",
        "ft.com",
        "nytimes.com",
        "washingtonpost.com",
        "theguardian.com",
        "thehindu.com",
        "indianexpress.com",
        "ndtv.com",
        "afp.com",
        "time.com",
        "economist.com",
        "cnbc.com",
        "forbes.com",
    }

    TIER_3_DOMAINS = {
        "theverge.com",
        "techcrunch.com",
        "arstechnica.com",
        "wired.com",
        "venturebeat.com",
        "zdnet.com",
        "cnet.com",
        "ieee.org",
        "acm.org",
        "github.com",
        "developer.mozilla.org",
        "stackoverflow.com",
        "espncricinfo.com",
        "cricbuzz.com",
        "olympics.com",
        "fifa.com",
        "nba.com",
        "who.int",
        "gsmarena.com",
        "variety.com",
        "hollywoodreporter.com",
        "ign.com",
        "space.com",
    }

    ENTITY_DOMAIN_MAP = {
        "openai": "openai.com",
        "chatgpt": "openai.com",
        "gpt": "openai.com",
        "sora": "openai.com",
        "dall-e": "openai.com",
        "anthropic": "anthropic.com",
        "claude": "anthropic.com",
        "google": "google.com",
        "deepmind": "deepmind.google",
        "gemini": "deepmind.google",
        "android": "google.com",
        "pixel": "google.com",
        "microsoft": "microsoft.com",
        "windows": "microsoft.com",
        "azure": "microsoft.com",
        "copilot": "microsoft.com",
        "apple": "apple.com",
        "iphone": "apple.com",
        "ipad": "apple.com",
        "macbook": "apple.com",
        "ios": "apple.com",
        "meta": "meta.com",
        "facebook": "meta.com",
        "instagram": "meta.com",
        "whatsapp": "whatsapp.com",
        "nvidia": "nvidia.com",
        "geforce": "nvidia.com",
        "amazon": "amazon.com",
        "aws": "amazon.com",
        "python": "python.org",
        "nodejs": "nodejs.org",
        "node.js": "nodejs.org",
        "react": "react.dev",
        "vue": "vuejs.org",
        "angular": "angular.io",
        "golang": "go.dev",
        "rust": "rust-lang.org",
        "typescript": "typescriptlang.org",
        "docker": "docker.com",
        "kubernetes": "kubernetes.io",
        "linux": "kernel.org",
        "tesla": "tesla.com",
        "spacex": "spacex.com",
        "nasa": "nasa.gov",
        "samsung": "samsung.com",
        "galaxy": "samsung.com",
        "intel": "intel.com",
        "amd": "amd.com",
        "ryzen": "amd.com",
        "sony": "sony.com",
        "playstation": "playstation.com",
        "adobe": "adobe.com",
        "figma": "figma.com",
        "spotify": "spotify.com",
        "netflix": "netflix.com",
        "uber": "uber.com",
        "github": "github.com",
    }

    EXCLUDED_FACTUAL_DOMAINS = {
        "youtube.com",
        "youtu.be",
        "tiktok.com",
        "facebook.com",
        "instagram.com",
        "reddit.com",
        "quora.com",
        "pinterest.com",
        "twitter.com",
        "x.com",
        "linkedin.com",
        "medium.com",
        "substack.com",
        "tumblr.com",
        "threads.net",
    }

    SPAM_TLDS = (".xyz", ".top", ".click", ".buzz", ".cfd", ".rest", ".tk", ".ml", ".ga")

    @classmethod
    def get_domain_tier(cls, url: str, query: str = "") -> Tuple[float, int]:
        """Returns (authority_weight, tier_number)."""
        try:
            parsed = urllib.parse.urlparse(url)
            host = (parsed.netloc or "").lower().split(":")[0]
            if host.startswith("www."):
                host = host[4:]
        except Exception:
            return 0.3, 4

        if not host:
            return 0.3, 4

        if any(host == d or host.endswith("." + d) for d in cls.EXCLUDED_FACTUAL_DOMAINS):
            return 0.0, 5
        if any(host.endswith(tld) for tld in cls.SPAM_TLDS):
            return 0.0, 5

        q_lower = query.lower()
        for entity_key, official_domain in cls.ENTITY_DOMAIN_MAP.items():
            if entity_key in q_lower:
                if host == official_domain or host.endswith("." + official_domain):
                    return 1.0, 1

        if any(host.endswith(tld) for tld in cls.TIER_1_TLDS):
            return 1.0, 1
        if any(host == d or host.endswith("." + d) for d in cls.TIER_1_DOMAINS):
            return 1.0, 1
        if any(host == d or host.endswith("." + d) for d in cls.TIER_2_DOMAINS):
            return 0.85, 2
        if any(host == d or host.endswith("." + d) for d in cls.TIER_3_DOMAINS):
            return 0.70, 3

        return 0.40, 4

    @classmethod
    def compute_freshness_score(cls, pub_date: Optional[str], text: str, is_fresh_query: bool) -> float:
        """Score temporal recency relative to current date (2026)."""
        if not is_fresh_query:
            return 0.70
        combined = ((pub_date or "") + " " + text).lower()
        # Breaking recency / current month (September 2026)
        if any(k in combined for k in [
            "sep 2026", "september 2026", "sept 2026", "sep 22, 2026", "sep 3, 2026", "sep 9, 2026",
            "today", "hours ago", "yesterday", "this week", "this month"
        ]):
            return 1.0
        # 2026 recent months
        if any(k in combined for k in ["jul 2026", "july 2026", "aug 2026", "august 2026", "2026"]):
            return 0.85
        if "2025" in combined:
            return 0.50
        if "2024" in combined:
            return 0.25
        return 0.40

    @classmethod
    def rank_and_filter(cls, results: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
        """Multi-factor AI Search Ranking: Authority + Freshness + Directness + Relevance."""
        lower_q = query.lower()
        is_fresh = any(k in lower_q for k in FRESHNESS_KEYWORDS)
        is_explicit_media_request = any(
            k in lower_q for k in ["video", "watch", "youtube", "reddit", "discussion", "forum"]
        )

        query_terms = set(re.findall(r"\b[A-Za-z0-9]{3,}\b", lower_q)) - {
            "what", "where", "when", "which", "whose", "this", "that", "search", "online", "tell"
        }

        ranked = []
        for r in results:
            url = r.get("url", "")
            weight, tier = cls.get_domain_tier(url, query)
            if tier == 5 and not is_explicit_media_request:
                continue

            title = r.get("title", "")
            snippet = r.get("snippet", "")
            pub_date = r.get("published_date")

            # 1. Freshness Score
            freshness = cls.compute_freshness_score(pub_date, title + " " + snippet, is_fresh)

            # 2. Directness / Keyword Relevance
            directness = 0.5
            title_lower = title.lower()
            if query_terms:
                matches = sum(1 for w in query_terms if w in title_lower)
                directness = min(1.0, 0.4 + (matches * 0.15))

            provider_score = float(r.get("score") or 0.6)
            relevance_score = (directness * 0.6) + (provider_score * 0.4)

            # 3. Multi-factor Weighted Combination
            if is_fresh:
                # 35% Domain Authority, 40% Freshness, 25% Relevance
                final_rank = (weight * 0.35) + (freshness * 0.40) + (relevance_score * 0.25)
            else:
                # 60% Domain Authority, 40% Relevance
                final_rank = (weight * 0.60) + (relevance_score * 0.40)

            r_copy = dict(r)
            r_copy["_authority_weight"] = weight
            r_copy["_authority_tier"] = tier
            r_copy["_freshness_score"] = round(freshness, 2)
            r_copy["_rank_score"] = round(final_rank, 4)
            ranked.append(r_copy)

        ranked.sort(key=lambda x: x["_rank_score"], reverse=True)

        # For non-fresh factual queries, if high-authority (Tier 1-3) results exist, keep them clean
        if not is_fresh and not is_explicit_media_request:
            high_authority = [r for r in ranked if r.get("_authority_tier", 4) <= 3]
            if len(high_authority) >= 2:
                return high_authority

        return ranked


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

        # 3. Clean trailing conversational noise
        trailing_noise = [
            r"\s*(?:search\s+and\s+tell(?:\s+me)?|search\s+and\s+batao|search\s+karke\s+batao|search\s+karo|search\s+kr|search\s+it|please)\s*$",
            r"\s*(?:till\s+today|as\s+of\s+today|today|now)\s*$",
        ]
        for pat in trailing_noise:
            cleaned = re.sub(pat, " ", cleaned, flags=re.IGNORECASE)

        # 4. Normalize common conversational tech terms
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
            "include_answer": False,
            "exclude_domains": list(DomainAuthorityRanker.EXCLUDED_FACTUAL_DOMAINS),
            "max_results": min(max_results * 2, 10),
        }

        try:
            async with httpx.AsyncClient(timeout=7.5) as client:
                resp = await client.post("https://api.tavily.com/search", json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    raw_answer = data.get("answer")
                    if raw_answer:
                        self.last_answer = raw_answer

                    results: List[Dict[str, Any]] = []
                    for item in data.get("results", []):
                        url = item.get("url") or ""
                        if not url:
                            continue
                        title = item.get("title") or "Web Page"
                        snippet = item.get("content") or ""
                        pub_date = item.get("published_date")
                        score = float(item.get("score") or 0.6)
                        results.append({
                            "title": title,
                            "url": url,
                            "snippet": snippet,
                            "published_date": pub_date,
                            "score": score,
                            "source": "tavily",
                        })
                        if len(results) >= max_results:
                            break

                    logger.info("Tavily returned %d results for query: %r", len(results), query[:50])
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
            incident_terms = {"incident", "controversy", "lawsuit", "breach", "cyberattack", "allegations", "scandal"}
            is_incident_query = any(t in query.lower() for t in incident_terms)

            for item in items:
                title = item.get("title", "")
                lower_title = title.lower()
                # Filter out incident and breach articles unless explicitly queried
                if not is_incident_query and any(t in lower_title for t in incident_terms):
                    continue
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
                if len(results) >= max_results:
                    break
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
    """Enterprise-grade multi-provider search engine.
    Pools candidate search results across Tavily AI Search, Wikipedia Encyclopedia,
    Google News RSS (for fresh events), and DuckDuckGo fallback,
    followed by URL canonicalization, deduplication, and DomainAuthorityRanker trust scoring.
    """

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

    @staticmethod
    def _should_query_wikipedia(q: str) -> bool:
        lower = q.lower()
        if any(entity in lower for entity in DomainAuthorityRanker.ENTITY_DOMAIN_MAP):
            return True
        wiki_keywords = {
            "who", "what", "which", "when", "where", "history", "biography", "founder",
            "ceo", "model", "release", "released", "version", "specs", "specifications",
            "country", "capital", "president", "prime minister", "winner", "award",
            "oscar", "olympics", "championship", "cup", "space", "mission", "satellite",
            "definition", "meaning", "theory", "algorithm", "language", "framework"
        }
        return any(w in lower for w in wiki_keywords)

    async def search(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        clean_q = TavilyWebSearchProvider._clean_query(query)
        lower_q = clean_q.lower()
        is_fresh = any(k in lower_q for k in FRESHNESS_KEYWORDS)
        should_wiki = self._should_query_wikipedia(clean_q)

        candidate_pool: List[Dict[str, Any]] = []

        # Stage 1: Formulate focused Wikipedia search term if entity is detected
        wiki_search_term = clean_q
        if should_wiki:
            for entity_key in DomainAuthorityRanker.ENTITY_DOMAIN_MAP:
                if entity_key in lower_q:
                    if any(w in lower_q for w in ["model", "release", "version", "product"]):
                        wiki_search_term = f"{entity_key} models"
                    else:
                        wiki_search_term = entity_key
                    break

        # Stage 2: Gather candidates concurrently
        tasks = [self.tavily.search(clean_q, max_results=max_results * 2)]
        if should_wiki:
            tasks.append(self.wikipedia.search(wiki_search_term, max_results=4))
        if is_fresh:
            tasks.append(self.google_news.search(clean_q, max_results=4))

        gathered_results = await asyncio.gather(*tasks, return_exceptions=True)

        for res in gathered_results:
            if isinstance(res, list):
                candidate_pool.extend(res)
            elif isinstance(res, Exception):
                logger.warning("Search provider task failed: %s", res)

        # Stage 2: Fallback to DuckDuckGo if primary candidates are sparse (< 2)
        if len(candidate_pool) < 2:
            try:
                ddg_results = await self.duckduckgo.search(clean_q, max_results=max_results * 2)
                candidate_pool.extend(ddg_results)
            except Exception as exc:
                logger.warning("DuckDuckGo fallback failed: %s", exc)

        # Stage 3: Normalize URLs and Deduplicate
        seen_normalized_urls: set[str] = set()
        deduped_candidates: List[Dict[str, Any]] = []

        for item in candidate_pool:
            url = item.get("url") or ""
            if not url:
                continue
            norm_url = normalize_url(url)
            if norm_url in seen_normalized_urls:
                continue
            seen_normalized_urls.add(norm_url)
            deduped_candidates.append(item)

        # Stage 4: Algorithmic Domain Authority & Trust Scoring
        ranked_results = DomainAuthorityRanker.rank_and_filter(deduped_candidates, clean_q)

        effective_limit = max(max_results, 7) if is_fresh else max_results
        return ranked_results[:effective_limit]



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
