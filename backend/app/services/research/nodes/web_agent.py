"""
WebResearchAgent — Phase 10 LangGraph Node.

Reuses the existing web_search and read_url tools via ToolExecutor.
Returns normalized, credibility-ranked Evidence objects.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

from app.core.config import get_settings
from app.services.research.models import Evidence, EvidenceSource, ResearchTask, TaskStatus
from app.tools.base import ToolExecutionContext
from app.tools.executor import ToolExecutor
from app.tools.registry import get_tool_registry

logger = logging.getLogger(__name__)
settings = get_settings()

# Known high-credibility authoritative & official vendor domains
_OFFICIAL_DOMAINS = {
    "docs.anthropic.com", "anthropic.com",
    "openai.com", "platform.openai.com", "help.openai.com",
    "cursor.com", "cursor.sh", "docs.cursor.com",
    "codeium.com", "windsurf.ai",
    "github.com", "docs.github.com",
    "arxiv.org",
    "huggingface.co",
    "microsoft.com", "learn.microsoft.com",
    "google.com", "ai.google.dev", "cloud.google.com",
    "aws.amazon.com", "developer.apple.com",
}

_REPUTABLE_TECH_DOMAINS = {
    "techcrunch.com", "reuters.com", "bloomberg.com", "theverge.com",
    "wired.com", "arstechnica.com", "venturebeat.com", "infoworld.com",
    "zdnet.com", "stackoverflow.com", "news.ycombinator.com",
}

_LOW_QUALITY_PATTERNS = [
    r"blogspot\.", r"wordpress\.com", r"medium\.com/@", r"hubpages\.",
    r"ezine\.", r"contentfarm\.", r"seo-article\.",
]


class WebResearchAgent:
    """
    Performs web research for a single ResearchTask.
    Reuses web_search and read_url tools via ToolExecutor.
    Ranks evidence by source credibility and filters unsupported duplicates.
    """

    def __init__(self, executor: ToolExecutor | None = None) -> None:
        self.executor = executor or ToolExecutor(get_tool_registry())

    async def research(
        self,
        task: ResearchTask,
        context: ToolExecutionContext,
        max_sources: int = 5,
        timeout_seconds: float = 30.0,
    ) -> tuple[list[Evidence], str | None]:
        """
        Execute web research for the task.

        Returns (evidence_list, error_message_or_None).
        """
        try:
            return await asyncio.wait_for(
                self._do_research(task, context, max_sources),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError:
            logger.warning("WebResearchAgent timeout for task %s", task.task_id)
            return [], f"Task timed out after {timeout_seconds}s"
        except Exception as exc:
            logger.error("WebResearchAgent error for task %s: %s", task.task_id, exc)
            return [], str(exc)

    @staticmethod
    def _extract_domain(url: str | None) -> str:
        """Extract normalized domain name from URL."""
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

    @classmethod
    def _score_source_credibility(
        cls, url: str | None, title: str, snippet: str
    ) -> tuple[float, bool]:
        """
        Determine source credibility score (0.0–1.0) and whether it is an official source.
        """
        domain = cls._extract_domain(url)
        if not domain:
            return 0.5, False

        # 1. Check exact or subdomain match with known official domains
        for off in _OFFICIAL_DOMAINS:
            if domain == off or domain.endswith("." + off):
                return 0.95, True

        # 2. Check doc subdomains (e.g. docs.xyz.com)
        if domain.startswith("docs.") or domain.startswith("api.") or "developer." in domain:
            return 0.90, True

        # 3. Check reputable journalism / established tech media
        for rep in _REPUTABLE_TECH_DOMAINS:
            if domain == rep or domain.endswith("." + rep):
                return 0.85, False

        # 4. Check low-quality / scraper patterns
        for pat in _LOW_QUALITY_PATTERNS:
            if re.search(pat, url or "", re.IGNORECASE):
                return 0.40, False

        # 5. Default web domain
        return 0.70, False

    async def _do_research(
        self,
        task: ResearchTask,
        context: ToolExecutionContext,
        max_sources: int,
    ) -> tuple[list[Evidence], str | None]:
        evidence_list: list[Evidence] = []

        # 1. Web search
        search_result = await self.executor.execute(
            tool_name="web_search",
            arguments={"query": task.query, "max_results": max_sources * 2},
            context=context,
        )

        if not search_result.success:
            logger.warning("web_search failed for task %s: %s", task.task_id, search_result.error)
            # Try news search as fallback
            news_result = await self.executor.execute(
                tool_name="search_news",
                arguments={"query": task.query, "max_results": max_sources},
                context=context,
            )
            if news_result.success and news_result.data:
                return self._extract_evidence_from_news(task, news_result.data, max_sources), None
            return [], search_result.error

        raw_results = search_result.data
        if not raw_results:
            return [], None

        # Handle different result formats
        items = []
        if isinstance(raw_results, list):
            items = raw_results
        elif isinstance(raw_results, dict):
            items = raw_results.get("results", raw_results.get("items", []))

        # 2. For each result, create Evidence and score credibility
        seen_urls: set[str] = set()
        seen_titles: set[str] = set()
        candidates: list[Evidence] = []

        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                continue

            url = (item.get("url") or item.get("href") or item.get("link") or "").strip()
            title = (item.get("title") or item.get("name") or "").strip()
            snippet = (item.get("snippet") or item.get("description") or item.get("body") or "").strip()
            published_at = item.get("published_at") or item.get("date") or item.get("published_date")

            if not snippet and not title:
                continue

            # Deduplicate by canonical URL
            norm_url = url.split("?")[0].rstrip("/") if url else ""
            if norm_url and norm_url in seen_urls:
                continue
            if norm_url:
                seen_urls.add(norm_url)

            # Deduplicate by normalized title
            clean_title = re.sub(r"[^\w\s]", "", title.lower()).strip()
            if clean_title and clean_title in seen_titles:
                continue
            if clean_title:
                seen_titles.add(clean_title)

            domain = self._extract_domain(url)
            credibility, is_official = self._score_source_credibility(url, title, snippet)
            relevance = max(0.2, 0.90 - (idx * 0.04))

            evidence = Evidence(
                task_id=task.task_id,
                source_type=EvidenceSource.WEB,
                title=str(title)[:200],
                url=str(url)[:500] if url else None,
                domain=domain,
                snippet=str(snippet)[:500],
                content=str(snippet)[:3000],
                published_at=str(published_at) if published_at else None,
                relevance=relevance,
                reliability=credibility,
                credibility_score=credibility,
                is_official=is_official,
            )
            candidates.append(evidence)

        # Sort candidate evidence by (is_official DESC, credibility_score DESC, relevance DESC)
        candidates.sort(
            key=lambda e: (
                1 if e.is_official else 0,
                e.credibility_score,
                e.relevance,
            ),
            reverse=True,
        )

        # Select top max_sources
        selected = candidates[:max_sources]

        # 3. Deep-read the top 2 authoritative URLs if possible
        for idx, ev in enumerate(selected[:2]):
            if ev.url and ev.url.startswith("http"):
                try:
                    read_result = await self.executor.execute(
                        tool_name="read_url",
                        arguments={"url": ev.url, "max_length": 3000},
                        context=context,
                    )
                    if read_result.success and read_result.data:
                        rd = read_result.data
                        if isinstance(rd, dict):
                            ev.content = str(rd.get("content", rd.get("text", ev.snippet)))[:3000]
                        elif isinstance(rd, str):
                            ev.content = str(rd)[:3000]
                except Exception as exc:
                    logger.debug("Failed deep read for URL %s: %s", ev.url, exc)

        return selected, None

    def _extract_evidence_from_news(
        self, task: ResearchTask, data: Any, max_sources: int
    ) -> list[Evidence]:
        items = data if isinstance(data, list) else data.get("articles", [])
        evidence_list = []
        seen_urls = set()
        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            url = str(item.get("url", item.get("link", "")))[:500] or ""
            if url in seen_urls:
                continue
            if url:
                seen_urls.add(url)
            domain = self._extract_domain(url)
            credibility, is_official = self._score_source_credibility(url, item.get("title", ""), "")
            evidence_list.append(Evidence(
                task_id=task.task_id,
                source_type=EvidenceSource.NEWS,
                title=str(item.get("title", ""))[:200],
                url=url or None,
                domain=domain,
                snippet=str(item.get("description", item.get("snippet", "")))[:500],
                content=str(item.get("body", item.get("content", "")))[:3000],
                published_at=str(item.get("published_at", item.get("pubDate", ""))) or None,
                relevance=0.85 - (idx * 0.05),
                reliability=credibility,
                credibility_score=credibility,
                is_official=is_official,
            ))
            if len(evidence_list) >= max_sources:
                break
        return evidence_list

