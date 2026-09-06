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
from app.services.chat.router import ModelRouter
from app.services.research.models import AgentType, ResearchPlan, ResearchTask

logger = logging.getLogger(__name__)
settings = get_settings()

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

        active_provider = provider or self.provider
        active_model = model or self.model
        raw_output = await self._stream_collect(
            messages,
            provider=active_provider,
            model=active_model,
        )
        tasks = self._parse_tasks(query, raw_output, max_tasks)

        return ResearchPlan(
            original_query=query,
            research_intent=tasks[0].query if tasks else query,
            tasks=tasks,
        )

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
