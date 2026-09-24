"""
ResearchPlanner — Phase 10 LangGraph Node.

Uses the reasoning model via ModelRouter to decompose a complex research query
into a list of independent ResearchTask objects.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Optional
from uuid import UUID

from app.core.config import get_settings
from app.core.enums import ConversationMode, MessageRole
from app.providers.base import NormalizedMessage
from app.services.research.models import (
    AgentType,
    Evidence,
    ResearchPlan,
    ResearchQuery,
    ResearchTask,
    SectionTask,
)

logger = logging.getLogger(__name__)
settings = get_settings()

_QUERY_GEN_SYSTEM = """You are a master research planner. Given a user's question, generate {count} diverse, highly specific search queries covering multiple complementary dimensions.
Rules:
1. Cover: primary sources/docs, technical specs/architecture, recent announcements/pricing, comparisons/benchmarks, real-world usage/limitations.
2. Avoid duplicate phrasing.
3. Keep each query concise and keyword-dense (ideal for search engines).
4. Output ONLY valid JSON:
{{
  "queries": [
    {{
      "query": "specific search string",
      "purpose": "why this query is needed",
      "recency_days": {recency_days}
    }}
  ]
}}"""

_SECTION_PLAN_SYSTEM = """You are an expert research editor. Given a research query and gathered evidence, divide the comprehensive research report into 4 to 8 distinct, non-overlapping section tasks.
Rules:
1. Each section must cover a clear sub-topic (e.g., Executive Overview, Technical Architecture, Performance & Benchmarks, Pricing & Availability, Real-World Tradeoffs).
2. Each section task must contain:
   - "id": short unique string
   - "title": clear section heading
   - "goal": what this section must establish
   - "key_questions": list of 2-3 specific questions to answer
   - "target_words": estimated word count (250-400)
   - "required_citations": true
   - "needs_code": true/false
3. Respond ONLY with valid JSON:
{{
  "sections": [
    {{
      "id": "s1",
      "title": "Section Title",
      "goal": "Specific goal",
      "key_questions": ["Q1?", "Q2?"],
      "target_words": 300,
      "required_citations": true,
      "needs_code": false
    }}
  ]
}}"""

_PLANNER_SYSTEM = """You are an expert research strategist. Your job is to decompose a user's research query into a set of independent, focused research sub-tasks that can be researched in parallel.

Rules:
1. Create between 2 and {max_tasks} sub-tasks.
2. Each sub-task must be a specific, focused search query — NOT a category label.
3. Assign each task an agent_type: "web" (for current web info), "document" (for uploaded PDFs/docs), or "finance" (for stock/crypto prices).
4. Assign priority 1–10 (10=most critical).
5. Tasks should be independent where possible.
6. Do NOT repeat the same angle.
7. Respond ONLY with valid JSON in this exact format:

{{
  "research_intent": "Brief description of what the user wants to know",
  "tasks": [
    {{
      "query": "specific focused search query",
      "agent_type": "web",
      "priority": 8
    }},
    ...
  ]
}}

Current date: {current_date}
"""

_JSON_EXTRACT = re.compile(r"\{[\s\S]*\}", re.DOTALL)


class ResearchPlanner:
    """Decomposes a research query into independent sub-tasks."""

    def __init__(
        self,
        router: Optional[ModelRouter] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        self.router = router or ModelRouter.from_settings()
        self.provider = provider
        self.model = model

    async def plan(
        self,
        query: str,
        max_tasks: int = 6,
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ) -> ResearchPlan:
        """Generate a research plan from the given query."""
        from datetime import datetime, timezone
        current_date = datetime.now(timezone.utc).strftime("%A, %B %d, %Y")

        system_prompt = _PLANNER_SYSTEM.format(
            max_tasks=max_tasks,
            current_date=current_date,
        )
        messages = [
            NormalizedMessage(role=MessageRole.SYSTEM, content=system_prompt),
            NormalizedMessage(role=MessageRole.USER, content=f"Research query: {query}"),
        ]

        from app.services.research.router import ResearchTaskType, select_research_model
        decision = select_research_model(
            ResearchTaskType.RESEARCH_PLANNING,
            self.router,
            explicit_provider=provider or self.provider,
            explicit_model=model or self.model,
        )
        raw_output = await self._stream_collect(
            messages,
            provider=decision.provider,
            model=decision.model,
            timeout=6.0,
        )
        tasks = self._parse_tasks(query, raw_output, max_tasks)

        return ResearchPlan(
            original_query=query,
            research_intent=tasks[0].query if tasks else query,
            tasks=tasks,
        )

    async def generate_queries(
        self,
        query: str,
        recency_days: int = 30,
        count: int = 5,
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ) -> list[ResearchQuery]:
        """Generate 3–8 diverse, targeted search queries covering complementary angles."""
        from app.services.research.router import ResearchTaskType, select_research_model
        decision = select_research_model(
            ResearchTaskType.QUERY_GENERATION,
            self.router,
            explicit_provider=provider or self.provider,
            explicit_model=model or self.model,
        )

        system_prompt = _QUERY_GEN_SYSTEM.format(count=count, recency_days=recency_days)
        messages = [
            NormalizedMessage(role=MessageRole.SYSTEM, content=system_prompt),
            NormalizedMessage(role=MessageRole.USER, content=f"Research topic: {query}"),
        ]

        raw_output = await self._stream_collect(
            messages,
            provider=decision.provider,
            model=decision.model,
            timeout=6.0,
        )

        data = self._extract_json_dict(raw_output)
        raw_queries = data.get("queries", [])
        parsed_queries: list[ResearchQuery] = []
        for rq in raw_queries:
            if isinstance(rq, dict) and rq.get("query"):
                parsed_queries.append(
                    ResearchQuery(
                        query=str(rq["query"]).strip(),
                        purpose=str(rq.get("purpose", "")).strip(),
                        recency_days=int(rq.get("recency_days", recency_days)),
                    )
                )

        if not parsed_queries:
            # Deterministic diverse angles fallback
            clean_q = query.strip()
            parsed_queries = [
                ResearchQuery(query=f"{clean_q} architecture technical overview", purpose="Technical architecture", recency_days=recency_days),
                ResearchQuery(query=f"{clean_q} pricing comparison limitations", purpose="Pricing & limitations", recency_days=recency_days),
                ResearchQuery(query=f"{clean_q} benchmarks capabilities performance", purpose="Benchmarks & performance", recency_days=recency_days),
                ResearchQuery(query=f"{clean_q} latest update documentation", purpose="Recent updates", recency_days=recency_days),
                ResearchQuery(query=clean_q, purpose="Primary query", recency_days=recency_days),
            ]

        return parsed_queries[:max(3, count)]

    async def plan_sections(
        self,
        query: str,
        evidence: list[Evidence],
        max_sections: int = 6,
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ) -> list[SectionTask]:
        """
        Decompose research into 4–8 section tasks for parallel fanout workers.
        Uses Gemini 3.5 Flash-Lite (or reasoning fallback) tested for heavy planning.
        """
        from app.services.research.models import SectionTask
        from app.services.research.router import ResearchTaskType, select_research_model
        decision = select_research_model(
            ResearchTaskType.RESEARCH_PLANNING,
            self.router,
            explicit_provider=provider or self.provider,
            explicit_model=model or self.model,
        )

        evidence_summary = "\n".join(
            f"- [{idx+1}] {e.title} ({e.domain or 'web'}): {e.snippet[:120]}"
            for idx, e in enumerate(evidence[:12])
        )

        system_prompt = _SECTION_PLAN_SYSTEM
        user_prompt = (
            f"Research Question: {query}\n\n"
            f"Discovered Evidence Sources ({len(evidence)} total):\n{evidence_summary}\n\n"
            f"Generate {max_sections} structured section tasks."
        )

        messages = [
            NormalizedMessage(role=MessageRole.SYSTEM, content=system_prompt),
            NormalizedMessage(role=MessageRole.USER, content=user_prompt),
        ]

        raw_output = await self._stream_collect(
            messages,
            provider=decision.provider,
            model=decision.model,
            timeout=10.0,
        )

        data = self._extract_json_dict(raw_output)
        raw_sections = data.get("sections", [])
        sections: list[SectionTask] = []
        for s in raw_sections:
            if isinstance(s, dict) and s.get("title"):
                sections.append(
                    SectionTask(
                        id=str(s.get("id") or str(len(sections) + 1)),
                        title=str(s.get("title")),
                        goal=str(s.get("goal", "")),
                        key_questions=[str(q) for q in s.get("key_questions", [])],
                        target_words=int(s.get("target_words", 300)),
                        required_citations=bool(s.get("required_citations", True)),
                        needs_code=bool(s.get("needs_code", False)),
                    )
                )

        if not sections:
            # Fallback sections
            sections = [
                SectionTask(id="s1", title="Executive Summary & Overview", goal="Synthesize high-level landscape"),
                SectionTask(id="s2", title="Technical Architecture & Details", goal="Analyze core technology"),
                SectionTask(id="s3", title="Comparisons & Real-World Tradeoffs", goal="Evaluate alternatives"),
                SectionTask(id="s4", title="Limitations & Future Outlook", goal="Document caveats and future direction"),
            ]

        return sections[:8]

    async def _stream_collect(
        self,
        messages: list[NormalizedMessage],
        provider: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 25.0,
    ) -> str:
        """Stream from reasoning model and collect full text with bounded tokens and timeout."""
        chunks: list[str] = []

        async def _collect():
            async for _selection, event in self.router.stream(
                messages=messages,
                mode=ConversationMode.DEEP_RESEARCH,
                provider=provider,
                model=model,
                max_tokens=800,
            ):
                if event.delta:
                    chunks.append(event.delta)

        try:
            await asyncio.wait_for(_collect(), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning("Planner streaming timed out after %.1fs", timeout)
        except Exception as exc:
            logger.warning("Planner stream failed: %s", exc)
        return "".join(chunks)

    def _parse_tasks(self, query: str, text: str, max_tasks: int) -> list[ResearchTask]:
        """Extract ResearchTask list from model JSON output."""
        data = self._extract_json_dict(text)
        raw_tasks = data.get("tasks", [])[:max_tasks]
        tasks = []
        for raw in raw_tasks:
            if not isinstance(raw, dict):
                continue
            task_query = str(raw.get("query", "")).strip()
            if not task_query:
                continue
            agent_str = str(raw.get("agent_type", "web")).lower()
            try:
                agent_type = AgentType(agent_str)
            except ValueError:
                agent_type = AgentType.WEB
            priority = int(raw.get("priority", 5))
            tasks.append(ResearchTask(query=task_query, agent_type=agent_type, priority=priority))

        if not tasks:
            tasks = [ResearchTask(query=query, agent_type=AgentType.WEB, priority=8)]
        # Sort by priority descending
        tasks.sort(key=lambda t: t.priority, reverse=True)
        return tasks

    @staticmethod
    def _extract_json_dict(text: str) -> dict:
        if not text:
            return {}
        text = re.sub(r"<think>[\s\S]*?</think>", "", text).strip()
        text = re.sub(r"```(?:json)?\s*([\s\S]*?)\s*```", r"\1", text).strip()
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            snippet = text[start : end + 1]
            try:
                data = json.loads(snippet)
                if isinstance(data, dict):
                    return data
            except Exception:
                cleaned = re.sub(r",\s*([\}\]])", r"\1", snippet)
                try:
                    data = json.loads(cleaned)
                    if isinstance(data, dict):
                        return data
                except Exception:
                    pass
        return {}
