"""
DocumentResearchAgent — Phase 10 LangGraph Node.

Reuses the existing search_knowledge_base tool via ToolExecutor.
Retrieves evidence from uploaded PDFs / documents scoped to the user/project.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.services.research.models import Evidence, EvidenceSource, ResearchTask
from app.tools.base import ToolExecutionContext
from app.tools.executor import ToolExecutor
from app.tools.registry import get_tool_registry

logger = logging.getLogger(__name__)


class DocumentResearchAgent:
    """
    Performs document-based research for a ResearchTask.
    Reuses search_knowledge_base tool via ToolExecutor.
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
        try:
            return await asyncio.wait_for(
                self._do_research(task, context, max_sources),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError:
            logger.warning("DocumentResearchAgent timeout for task %s", task.task_id)
            return [], f"Task timed out after {timeout_seconds}s"
        except Exception as exc:
            logger.error("DocumentResearchAgent error for task %s: %s", task.task_id, exc)
            return [], str(exc)

    async def _do_research(
        self,
        task: ResearchTask,
        context: ToolExecutionContext,
        max_sources: int,
    ) -> tuple[list[Evidence], str | None]:
        result = await self.executor.execute(
            tool_name="search_knowledge_base",
            arguments={
                "query": task.query,
                "top_k": max_sources,
                "strategy": "hybrid",
            },
            context=context,
        )

        if not result.success:
            logger.info("search_knowledge_base returned no results for task %s", task.task_id)
            return [], result.error

        raw = result.data
        if not raw:
            return [], None

        # Knowledge base returns structured chunks
        chunks = raw if isinstance(raw, list) else raw.get("chunks", raw.get("results", []))
        evidence_list: list[Evidence] = []

        for idx, chunk in enumerate(chunks[:max_sources]):
            if not isinstance(chunk, dict):
                continue

            # Handle both direct chunk format and nested format
            content = chunk.get("content", chunk.get("text", ""))
            filename = chunk.get("filename", chunk.get("file_name", ""))
            page = chunk.get("page_number", chunk.get("page", None))
            file_id = str(chunk.get("file_id", "")) or None
            score = float(chunk.get("score", chunk.get("similarity_score", chunk.get("relevance", 0.7))))

            evidence = Evidence(
                task_id=task.task_id,
                source_type=EvidenceSource.PDF,
                title=filename or "Document",
                url=None,
                file_id=file_id,
                page_number=int(page) if page is not None else None,
                snippet=str(content)[:500],
                content=str(content)[:3000],
                relevance=min(1.0, score),
                reliability=0.85,  # Documents are generally reliable
            )
            evidence_list.append(evidence)

        return evidence_list, None
