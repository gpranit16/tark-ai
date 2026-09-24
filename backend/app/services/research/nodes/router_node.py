"""
ResearchRouter Node for Deep Research 2.0.

Classifies incoming research questions into:
- closed_book: purely conceptual / stable reasoning from knowledge
- hybrid: internal context + fresh external evidence
- open_book: fresh, real-time, or contemporary web research required
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Optional

from app.core.config import get_settings
from app.core.enums import ConversationMode, MessageRole
from app.providers.base import NormalizedMessage
from app.services.chat.router import ModelRouter
from app.services.research.models import ResearchRouterResult
from app.services.research.router import ResearchTaskType, select_research_model

logger = logging.getLogger(__name__)

_FRESHNESS_TRIGGERS = [
    r"\blatest\b", r"\btoday\b", r"\bcurrent\b", r"\brecent\b", r"\bthis week\b",
    r"\bthis month\b", r"\b2025\b", r"\b2026\b", r"\bnews\b", r"\bpricing\b",
    r"\bannouncement\b", r"\bupdate\b", r"\bbenchmark\b", r"\brelease\b",
    r"\bmarket\b", r"\bcompare\b", r"\bvs\b",
]

_ROUTER_SYSTEM = """You are a research classifier for an AI research workspace.
Classify the user's inquiry into one of three research modes:
1. "open_book": Highly time-sensitive, requires current web data, recent pricing, latest technical releases, or external evidence.
2. "hybrid": Benefits from both background conceptual knowledge and fresh external web grounding.
3. "closed_book": Timeless logic, math, fundamental science, or pure conceptual explanation where external web search adds little value.

Respond ONLY with valid JSON:
{{
  "mode": "open_book" | "hybrid" | "closed_book",
  "requires_research": true | false,
  "reason": "brief rationale",
  "recency_days": 7 (for urgent/recent events) | 30 (for standard recent) | 365 (for broad),
  "queries_needed": integer between 3 and 6
}}"""

_JSON_EXTRACT = re.compile(r"\{[\s\S]*\}", re.DOTALL)


class ResearchRouter:
    """Classifies user queries to configure Deep Research pipeline parameters."""

    def __init__(
        self,
        router: Optional[ModelRouter] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        self.router = router or ModelRouter.from_settings()
        self.provider = provider
        self.model = model

    async def classify(
        self,
        query: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ) -> ResearchRouterResult:
        """Classify research query and determine recency and query volume requirements."""
        query_lower = query.lower()

        # Deterministic keyword check for open_book freshness
        is_high_freshness = any(re.search(pat, query_lower) for pat in _FRESHNESS_TRIGGERS)

        # Fast model selection for classification
        decision = select_research_model(
            ResearchTaskType.CLASSIFICATION,
            self.router,
            explicit_provider=provider or self.provider,
            explicit_model=model or self.model,
        )

        messages = [
            NormalizedMessage(role=MessageRole.SYSTEM, content=_ROUTER_SYSTEM),
            NormalizedMessage(role=MessageRole.USER, content=f"Query: {query}"),
        ]

        chunks: list[str] = []
        try:
            async def _collect():
                async for _sel, event in self.router.stream(
                    messages=messages,
                    mode=ConversationMode.DEEP_RESEARCH,
                    provider=decision.provider,
                    model=decision.model,
                    max_tokens=250,
                ):
                    if event.delta:
                        chunks.append(event.delta)

            await asyncio.wait_for(_collect(), timeout=4.0)
            clean_raw = "".join(chunks)
            if "```" in clean_raw:
                clean_raw = re.sub(r"```(?:json)?", "", clean_raw)
            match = _JSON_EXTRACT.search(clean_raw)
            if match:
                data = json.loads(match.group(0))
                mode = str(data.get("mode", "open_book")).lower()
                recency = int(data.get("recency_days", 7 if is_high_freshness else 30))
                queries_needed = max(3, min(int(data.get("queries_needed", 5)), 6))
                return ResearchRouterResult(
                    mode=mode if mode in ("closed_book", "hybrid", "open_book") else "open_book",
                    requires_research=bool(data.get("requires_research", True)),
                    reason=str(data.get("reason", "Classified by research router")),
                    recency_days=recency,
                    queries_needed=queries_needed,
                )
        except Exception as exc:
            logger.warning("[ROUTER] Classification LLM fallback: %s", exc)

        # Deterministic rule-based fallback
        recency = 7 if is_high_freshness else 30
        return ResearchRouterResult(
            mode="open_book" if is_high_freshness else "hybrid",
            requires_research=True,
            reason="Rule-based classification fallback",
            recency_days=recency,
            queries_needed=5 if is_high_freshness else 4,
        )
