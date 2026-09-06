"""
ResearchQueryRefiner — Phase 10 LangGraph Node.

Generates refined/gap-filling queries when evidence is insufficient.
Tracks previously tried queries to prevent useless repetition.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional

from app.core.enums import ConversationMode, MessageRole
from app.providers.base import NormalizedMessage
from app.services.chat.router import ModelRouter
from app.services.research.models import AgentType, ResearchTask, VerificationResult

logger = logging.getLogger(__name__)

_REFINER_SYSTEM = """You are a research query optimizer.

Given a research question, a verification report (showing gaps/missing info), and the list of queries already tried,
generate NEW search queries to fill the identified gaps.

Rules:
1. Generate 1–3 targeted queries ONLY for the missing information identified.
2. Do NOT repeat or rephrase queries already in the tried list.
3. Each query should address a specific gap or missing angle.
4. Assign agent_type: "web", "document", or "finance".
5. Respond ONLY with JSON:

{{
  "refined_queries": [
    {{"query": "specific targeted query", "agent_type": "web"}},
    ...
  ]
}}
"""

_JSON_EXTRACT = re.compile(r"\{[\s\S]*\}", re.DOTALL)


class ResearchQueryRefiner:
    """Generates gap-filling queries based on verification failures."""

    def __init__(
        self,
        router: Optional[ModelRouter] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        self.router = router or ModelRouter.from_settings()
        self.provider = provider
        self.model = model

    async def refine(
        self,
        original_query: str,
        verification: VerificationResult,
        tried_queries: list[str],
        max_new_tasks: int = 3,
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ) -> list[ResearchTask]:
        """
        Generate new ResearchTask objects targeting evidence gaps.

        Returns empty list if no useful refinements can be made.
        """
        if not verification.missing_information and not verification.unsupported_claims:
            return []

        gaps = "\n".join(
            f"- {g}" for g in (verification.missing_information + verification.unsupported_claims)[:6]
        )
        tried = "\n".join(f"- {q}" for q in tried_queries[-10:])

        messages = [
            NormalizedMessage(role=MessageRole.SYSTEM, content=_REFINER_SYSTEM),
            NormalizedMessage(
                role=MessageRole.USER,
                content=(
                    f"Original research question: {original_query}\n\n"
                    f"Evidence gaps identified:\n{gaps}\n\n"
                    f"Queries already tried:\n{tried}\n\n"
                    "Generate focused queries to fill these gaps."
                ),
            ),
        ]

        active_provider = provider or self.provider
        active_model = model or self.model
        raw = await self._stream_collect(
            messages,
            provider=active_provider,
            model=active_model,
        )
        return self._parse_tasks(raw, tried_queries, max_new_tasks)

    async def _stream_collect(
        self,
        messages: list[NormalizedMessage],
        provider: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 20.0,
    ) -> str:
        chunks: list[str] = []

        async def _collect():
            async for _sel, event in self.router.stream(
                messages=messages,
                mode=ConversationMode.DEEP_RESEARCH,
                provider=provider,
                model=model,
                max_tokens=600,
            ):
                if event.delta:
                    chunks.append(event.delta)

        try:
            await asyncio.wait_for(_collect(), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning("Refiner stream timed out after %.1fs", timeout)
        except Exception as exc:
            logger.warning("Refiner stream failed: %s", exc)
        return "".join(chunks)

    def _parse_tasks(
        self, text: str, tried_queries: list[str], max_new_tasks: int
    ) -> list[ResearchTask]:
        data = self._extract_json_dict(text)
        if not data:
            return []

        tried_set = {q.lower().strip() for q in tried_queries}
        tasks: list[ResearchTask] = []

        try:
            for item in data.get("refined_queries", [])[:max_new_tasks]:
                if not isinstance(item, dict):
                    continue
                q = str(item.get("query", "")).strip()
                if not q or q.lower() in tried_set:
                    continue
                agent_str = str(item.get("agent_type", "web")).lower()
                try:
                    agent_type = AgentType(agent_str)
                except ValueError:
                    agent_type = AgentType.WEB
                tasks.append(ResearchTask(
                    query=q,
                    agent_type=agent_type,
                    priority=6,
                ))
        except Exception as exc:
            logger.warning("Refiner parse failed: %s", exc)

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
