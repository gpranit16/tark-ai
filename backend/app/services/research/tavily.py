"""
Dedicated Tavily Research Service for Deep Research 2.0.

Provides parallel web search execution with bounded concurrency, timeout handling,
and evidence normalization. Does not modify or interfere with normal web search.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
import os
import re
from typing import Any
from urllib.parse import urlparse

import httpx

from app.core.config import get_settings
from app.services.research.models import Evidence, EvidenceSource, ResearchQuery

logger = logging.getLogger(__name__)

# Known high-credibility authoritative & official vendor domains
_OFFICIAL_DOMAINS = {
    "docs.anthropic.com", "anthropic.com",
    "openai.com", "platform.openai.com", "help.openai.com",
    "cursor.com", "cursor.sh", "docs.cursor.com",
    "codeium.com", "windsurf.ai",
    "github.com", "docs.github.com",
    "arxiv.org", "huggingface.co",
    "microsoft.com", "learn.microsoft.com",
    "google.com", "ai.google.dev", "cloud.google.com",
    "aws.amazon.com", "developer.apple.com",
}

_REPUTABLE_TECH_DOMAINS = {
    "techcrunch.com", "reuters.com", "bloomberg.com", "theverge.com",
    "wired.com", "arstechnica.com", "venturebeat.com", "infoworld.com",
    "zdnet.com", "stackoverflow.com", "news.ycombinator.com", "nature.com",
    "ieee.org", "technologyreview.com",
}

_LOW_QUALITY_PATTERNS = [
    r"blogspot\.", r"wordpress\.com", r"medium\.com/@", r"hubpages\.",
    r"ezine\.", r"contentfarm\.", r"seo-article\.",
]


class TavilyResearchService:
    """Dedicated search client for Deep Research web discovery."""

    def __init__(self, api_key: str | None = None) -> None:
        self.settings = get_settings()
        self.api_key = api_key or self.settings.tavily_api_key or os.environ.get("TAVILY_API_KEY")
        self.max_queries = getattr(self.settings, "deep_research_max_queries", 6)
        self.max_results_per_query = getattr(self.settings, "deep_research_max_results_per_query", 5)

    @staticmethod
    def extract_domain(url: str | None) -> str:
        """Extract canonical domain name from URL."""
        if not url:
            return ""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            if domain.startswith("www."):
                domain = domain[4:]
            return domain
        except Exception:
            return ""

    @staticmethod
    def canonicalize_url(url: str | None) -> str:
        """Return canonical URL without tracking parameters, trailing slashes, or www prefix."""
        if not url:
            return ""
        try:
            parsed = urlparse(url.strip())
            netloc = parsed.netloc.lower()
            if netloc.startswith("www."):
                netloc = netloc[4:]
            clean = f"{parsed.scheme.lower()}://{netloc}{parsed.path}".rstrip("/")
            return clean.lower()
        except Exception:
            return url.split("?")[0].rstrip("/").lower()

    @classmethod
    def score_source_credibility(cls, url: str | None, title: str, snippet: str) -> tuple[float, bool]:
        """Compute credibility score (0.0 to 1.0) and whether it is an official source."""
        domain = cls.extract_domain(url)
        if not domain:
            return 0.5, False

        for off in _OFFICIAL_DOMAINS:
            if domain == off or domain.endswith("." + off):
                return 0.95, True

        if domain.startswith("docs.") or domain.startswith("api.") or "developer." in domain:
            return 0.90, True

        for rep in _REPUTABLE_TECH_DOMAINS:
            if domain == rep or domain.endswith("." + rep):
                return 0.85, False

        for pat in _LOW_QUALITY_PATTERNS:
            if re.search(pat, url or "", re.IGNORECASE):
                return 0.40, False

        return 0.70, False

    @staticmethod
    def calculate_recency_score(published_at: str | None, target_days: int) -> float:
        """Calculate a normalized recency score (0.0 to 1.0) based on target freshness."""
        if not published_at:
            return 0.5
        try:
            # Common formats: YYYY-MM-DD or ISO
            clean_date = published_at[:10]
            dt = datetime.fromisoformat(clean_date).replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            age_days = max(0, (now - dt).days)
            if age_days <= target_days:
                return 1.0 - (0.5 * (age_days / max(1, target_days)))
            elif age_days <= target_days * 3:
                return 0.4
            else:
                return 0.2
        except Exception:
            return 0.5

    async def search_single_query(
        self,
        query: str,
        recency_days: int = 30,
        max_results: int = 5,
        timeout: float = 12.0,
        semaphore: asyncio.Semaphore | None = None,
    ) -> list[Evidence]:
        """Execute a single query against Tavily Search API with retry and timeout."""
        if not self.api_key:
            logger.warning("[TAVILY] No API key configured. Skipping search for: %r", query[:60])
            return []

        async def _do_call() -> list[Evidence]:
            payload: dict[str, Any] = {
                "api_key": self.api_key,
                "query": query,
                "search_depth": "advanced",
                "max_results": max_results,
                "include_answer": False,
                "include_raw_content": False,
            }
            if recency_days <= 14:
                payload["topic"] = "news"
                payload["days"] = max(3, recency_days)

            # Retry with exponential backoff (max 2 attempts)
            last_exc = None
            for attempt in range(2):
                try:
                    async with httpx.AsyncClient(timeout=timeout) as client:
                        resp = await client.post("https://api.tavily.com/search", json=payload)
                        if resp.status_code == 200:
                            data = resp.json()
                            raw_results = data.get("results", [])
                            evidence_items: list[Evidence] = []
                            for idx, item in enumerate(raw_results):
                                raw_url = item.get("url") or ""
                                raw_title = item.get("title") or "Web Source"
                                raw_content = item.get("content") or ""
                                published_at = item.get("published_date")

                                credibility, is_official = self.score_source_credibility(
                                    raw_url, raw_title, raw_content
                                )
                                recency = self.calculate_recency_score(published_at, recency_days)
                                relevance = max(0.2, 0.95 - (idx * 0.05))

                                evidence_items.append(
                                    Evidence(
                                        source_type=EvidenceSource.WEB,
                                        title=str(raw_title)[:250],
                                        url=str(raw_url)[:500] if raw_url else None,
                                        domain=self.extract_domain(raw_url),
                                        snippet=str(raw_content)[:600],
                                        content=str(raw_content)[:3500],
                                        query=query,
                                        published_at=str(published_at) if published_at else None,
                                        relevance=relevance,
                                        recency=recency,
                                        reliability=credibility,
                                        credibility_score=credibility,
                                        is_official=is_official,
                                    )
                                )
                            return evidence_items
                        else:
                            logger.warning("[TAVILY] Query %r returned status %d", query[:50], resp.status_code)
                except Exception as exc:
                    last_exc = exc
                    await asyncio.sleep(0.5 * (attempt + 1))

            if last_exc:
                logger.error("[TAVILY] Search failed for query %r: %s", query[:50], last_exc)
            return []

        if semaphore:
            async with semaphore:
                return await _do_call()
        return await _do_call()

    async def search_queries(
        self,
        queries: list[ResearchQuery],
        max_parallel: int = 3,
        max_results_per_query: int | None = None,
    ) -> list[Evidence]:
        """
        Execute multiple research queries concurrently with bounded concurrency.
        Gracefully aggregates evidence even if individual queries fail.
        """
        if not queries:
            return []

        limit = max_results_per_query or self.max_results_per_query
        bounded_queries = queries[: self.max_queries]
        semaphore = asyncio.Semaphore(max_parallel)

        tasks = [
            self.search_single_query(
                query=q.query,
                recency_days=q.recency_days,
                max_results=limit,
                semaphore=semaphore,
            )
            for q in bounded_queries
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)
        all_evidence: list[Evidence] = []
        for r in results:
            if isinstance(r, list):
                all_evidence.extend(r)
            elif isinstance(r, Exception):
                logger.warning("[TAVILY] Parallel query exception: %s", r)

        return all_evidence
