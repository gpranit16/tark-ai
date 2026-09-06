"""
DeepResearchGraph — Phase 10 LangGraph StateGraph orchestrator.

Graph flow:
  START → plan_research → dispatch_tasks → [parallel research] →
  collect_evidence → verify_evidence →
    sufficient? → synthesize → END
    insufficient & retries < MAX → refine_queries → dispatch_tasks (loop)
    retries exhausted → synthesize_partial → END
    cancelled → END

Uses asyncio for bounded parallel task execution.
Yields SSE events during execution for real-time progress streaming.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any, Optional

from langgraph.graph import StateGraph, END, START

from app.core.config import get_settings
from app.services.chat.router import ModelRouter
from app.services.chat.sse import text_delta
from app.services.research.models import (
    AgentType, Evidence, ResearchPlan, ResearchStatus, ResearchTask,
    TaskStatus, VerificationResult,
)
from app.services.research.nodes.document_agent import DocumentResearchAgent
from app.services.research.nodes.finance_agent import FinanceResearchAgent
from app.services.research.nodes.planner import ResearchPlanner
from app.services.research.nodes.refiner import ResearchQueryRefiner
from app.services.research.nodes.synthesizer import ResearchSynthesizer
from app.services.research.nodes.verifier import VerifierAgent
from app.services.research.sse import (
    research_citation,
    research_complete,
    research_evidence_collected,
    research_plan_created,
    research_planning,
    research_retry,
    research_started,
    research_synthesis_started,
    research_task_completed,
    research_task_failed,
    research_task_progress,
    research_task_started,
    research_verification_complete,
    research_verification_started,
    research_cancelled,
    research_error,
)
from app.services.research.nodes.web_agent import WebResearchAgent
from app.services.research.state import ResearchState
from app.tools.base import ToolExecutionContext
from app.tools.executor import ToolExecutor
from app.tools.registry import get_tool_registry

logger = logging.getLogger(__name__)
settings = get_settings()


class DeepResearchGraph:
    """
    LangGraph-based Deep Research orchestrator.

    Builds and executes the research state graph, yielding SSE events
    for real-time progress streaming to the client.
    """

    def __init__(
        self,
        router: Optional[ModelRouter] = None,
        executor: Optional[ToolExecutor] = None,
        sse_queue: Optional[asyncio.Queue] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        self.router = router or ModelRouter.from_settings()
        registry = get_tool_registry()
        self.executor = executor or ToolExecutor(registry)
        self.sse_queue: asyncio.Queue[str | None] = sse_queue or asyncio.Queue()
        self.provider = provider
        self.model = model

        # Initialize nodes with provider/model routing
        self.planner = ResearchPlanner(self.router, provider=self.provider, model=self.model)
        self.web_agent = WebResearchAgent(self.executor)
        self.doc_agent = DocumentResearchAgent(self.executor)
        self.finance_agent = FinanceResearchAgent(self.executor)
        self.verifier = VerifierAgent(self.router, provider=self.provider, model=self.model)
        self.refiner = ResearchQueryRefiner(self.router, provider=self.provider, model=self.model)
        self.synthesizer = ResearchSynthesizer(self.router, provider=self.provider, model=self.model)

        # Cancellation token
        self._cancelled = False

    def cancel(self) -> None:
        """Signal cancellation of the research graph."""
        self._cancelled = True

    async def _emit(self, event: str) -> None:
        """Queue an SSE event for streaming."""
        await self.sse_queue.put(event)

    # ── Graph Node Functions ───────────────────────────────────────────────

    async def node_plan(self, state: ResearchState) -> dict:
        """Planner node — converts query into a ResearchPlan."""
        logger.info("[RESEARCH] planning query=%r", state.get("query", "")[:80])
        await self._emit(research_planning())
        query = state["query"]
        max_tasks = min(settings.max_research_tasks, 8)

        active_provider = self.provider or (state.get("metadata") or {}).get("provider")
        active_model = self.model or (state.get("metadata") or {}).get("model")

        try:
            plan: ResearchPlan = await self.planner.plan(
                query,
                max_tasks=max_tasks,
                provider=active_provider,
                model=active_model,
            )
        except Exception as exc:
            logger.error("Planner failed: %s", exc)
            # Fallback: single web search task
            plan = ResearchPlan(
                original_query=query,
                research_intent=query,
                tasks=[ResearchTask(query=query, agent_type=AgentType.WEB, priority=8)],
            )

        plan_dict = plan.model_dump()
        task_dicts = [t.model_dump() for t in plan.tasks]

        await self._emit(research_plan_created(
            tasks=[{"task_id": t["task_id"], "query": t["query"], "agent_type": t["agent_type"]} for t in task_dicts],
            task_count=len(task_dicts),
        ))

        return {
            "plan": plan_dict,
            "research_tasks": task_dicts,
            "status": ResearchStatus.RESEARCHING,
            "rewritten_queries": [t["query"] for t in task_dicts],
        }

    @staticmethod
    def _deduplicate_evidence(evidence_list: list[Evidence]) -> list[Evidence]:
        """
        Consolidate duplicate evidence by exact canonical URL or title+domain without URL.
        Preserves distinct pages from the same domain (e.g. cursor.com/pricing vs cursor.com/features).
        """
        seen_urls: set[str] = set()
        seen_non_url_keys: set[str] = set()
        deduped: list[Evidence] = []
        for ev in evidence_list:
            norm_url = ev.url.split("?")[0].rstrip("/").lower() if ev.url else ""
            if norm_url:
                if norm_url in seen_urls:
                    continue
                seen_urls.add(norm_url)
                deduped.append(ev)
            else:
                clean_title = (ev.title or "").lower().strip()
                key = f"{ev.file_id or ev.domain or 'no-domain'}::{clean_title}"
                if clean_title and key in seen_non_url_keys:
                    continue
                if clean_title:
                    seen_non_url_keys.add(key)
                deduped.append(ev)
        return deduped

    async def node_research(self, state: ResearchState) -> dict:
        """
        Parallel research node — executes up to MAX_PARALLEL_RESEARCH_TASKS simultaneously.
        Gracefully handles individual task failures.
        """
        tasks_raw = state.get("research_tasks", [])
        # Only process PENDING tasks
        pending = [t for t in tasks_raw if t.get("status") == "pending"]
        if not pending:
            return {"evidence": [], "task_results": [], "failed_tasks": []}

        logger.info("[RESEARCH] tasks_started count=%d parallel_limit=%d", len(pending), settings.max_parallel_research_tasks)
        max_parallel = min(settings.max_parallel_research_tasks, len(pending))
        all_evidence: list[dict] = []
        all_results: list[dict] = []
        all_failed: list[dict] = []

        # Create copy of all tasks to update statuses
        updated_tasks = [dict(t) for t in tasks_raw]
        task_map = {t["task_id"]: t for t in updated_tasks}

        # Process in batches
        for batch_start in range(0, len(pending), max_parallel):
            if self._cancelled:
                break

            batch = pending[batch_start : batch_start + max_parallel]
            batch_coros = [self._execute_task(state, task) for task in batch]
            batch_results = await asyncio.gather(*batch_coros, return_exceptions=True)

            for task_dict, result in zip(batch, batch_results):
                t_id = task_dict.get("task_id", "")
                mapped = task_map.get(t_id, task_dict)

                if isinstance(result, Exception):
                    mapped["status"] = "failed"
                    mapped["error"] = str(result)
                    all_failed.append(mapped)
                    await self._emit(research_task_failed(t_id, str(result)))
                else:
                    evidence_list, error = result
                    if error and not evidence_list:
                        mapped["status"] = "failed"
                        mapped["error"] = error
                        all_failed.append(mapped)
                        await self._emit(research_task_failed(t_id, error))
                    else:
                        mapped["status"] = "completed"
                        all_results.append(mapped)
                        ev_dicts = [e.model_dump() for e in evidence_list]
                        all_evidence.extend(ev_dicts)
                        await self._emit(research_task_completed(
                            t_id, len(evidence_list)
                        ))

        # Deduplicate evidence objects to calculate actual usable source count
        raw_combined = [Evidence(**e) for e in state.get("evidence", []) + all_evidence if isinstance(e, dict)]
        deduped_combined = self._deduplicate_evidence(raw_combined)
        usable_count = len(deduped_combined)

        if all_evidence:
            await self._emit(research_evidence_collected(usable_count))

        return {
            "evidence": all_evidence,
            "task_results": all_results,
            "failed_tasks": all_failed,
            "research_tasks": updated_tasks,
            "status": ResearchStatus.VERIFYING,
        }

    async def _execute_task(
        self,
        state: ResearchState,
        task_dict: dict,
    ) -> tuple[list[Evidence], str | None]:
        """Execute a single research task using the appropriate agent."""
        task = ResearchTask(**task_dict)
        tool_ctx = self._build_tool_context(state)

        await self._emit(research_task_started(task.task_id, task.query, task.agent_type))

        timeout = settings.research_task_timeout_seconds
        max_sources = settings.max_sources_per_task

        if task.agent_type == AgentType.DOCUMENT:
            return await self.doc_agent.research(task, tool_ctx, max_sources, timeout)
        elif task.agent_type == AgentType.FINANCE:
            return await self.finance_agent.research(task, tool_ctx, max_sources, timeout)
        else:
            return await self.web_agent.research(task, tool_ctx, max_sources, timeout)

    def _build_tool_context(self, state: ResearchState) -> ToolExecutionContext:
        """Build a ToolExecutionContext from graph state."""
        from uuid import UUID
        return ToolExecutionContext(
            user_id=UUID(state["user_id"]),
            project_id=UUID(state["project_id"]) if state.get("project_id") else None,
            thread_id=UUID(state["thread_id"]),
            session=None,  # Research agents use stateless tool calls
        )

    async def node_verify(self, state: ResearchState) -> dict:
        """Verifier node — evaluates evidence quality and deduplicates."""
        logger.info("[RESEARCH] verification total_evidence=%d", len(state.get("evidence", [])))
        await self._emit(research_verification_started())

        all_evidence = state.get("evidence", [])
        evidence_objects = [Evidence(**e) for e in all_evidence if isinstance(e, dict)]

        # Deduplicate and sort by credibility
        evidence_objects = self._deduplicate_evidence(evidence_objects)
        evidence_objects.sort(
            key=lambda e: (
                1 if getattr(e, "is_official", False) else 0,
                getattr(e, "credibility_score", 0.7),
                getattr(e, "relevance", 0.5),
            ),
            reverse=True,
        )

        # Cap to avoid token overflow
        evidence_objects = evidence_objects[:settings.max_total_sources]

        active_provider = self.provider or (state.get("metadata") or {}).get("provider")
        active_model = self.model or (state.get("metadata") or {}).get("model")

        try:
            result: VerificationResult = await self.verifier.verify(
                query=state["query"],
                evidence=evidence_objects,
                min_confidence=0.35,
                provider=active_provider,
                model=active_model,
            )
        except Exception as exc:
            logger.error("Verifier failed: %s", exc)
            result = VerificationResult(
                sufficient=bool(evidence_objects),
                confidence=0.4 if evidence_objects else 0.0,
                reasoning=f"Verifier error: {exc}",
            )

        await self._emit(research_verification_complete(
            result.sufficient, result.confidence, result.conflicts
        ))

        return {
            "verified_evidence": [e.model_dump() for e in evidence_objects],
            "verification_result": result.model_dump(),
            "status": ResearchStatus.VERIFYING,
        }

    async def node_refine(self, state: ResearchState) -> dict:
        """Refiner node — generates new tasks for evidence gaps."""
        retry_count = state.get("retry_count", 0) + 1
        verification_dict = state.get("verification_result") or {}
        verification = VerificationResult(**verification_dict)
        tried = state.get("rewritten_queries", [])

        await self._emit(research_retry(retry_count, "; ".join(verification.missing_information[:2])))

        active_provider = self.provider or (state.get("metadata") or {}).get("provider")
        active_model = self.model or (state.get("metadata") or {}).get("model")

        try:
            new_tasks = await self.refiner.refine(
                original_query=state["query"],
                verification=verification,
                tried_queries=tried,
                max_new_tasks=3,
                provider=active_provider,
                model=active_model,
            )
        except Exception as exc:
            logger.error("Refiner failed: %s", exc)
            new_tasks = []

        new_task_dicts = [t.model_dump() for t in new_tasks]
        new_queries = [t.query for t in new_tasks]

        # Combine existing tasks and new tasks
        existing_tasks = state.get("research_tasks", [])
        combined_tasks = existing_tasks + new_task_dicts

        return {
            "research_tasks": combined_tasks,
            "rewritten_queries": tried + new_queries,
            "retry_count": retry_count,
            "status": ResearchStatus.RESEARCHING,
        }

    async def node_synthesize(self, state: ResearchState, is_partial: bool = False) -> dict:
        """Synthesizer node — produces final answer with citations."""
        logger.info("[RESEARCH] synthesis is_partial=%s", is_partial)
        await self._emit(research_synthesis_started())

        verified_ev_raw = state.get("verified_evidence", state.get("evidence", []))
        evidence_objects = [Evidence(**e) for e in verified_ev_raw if isinstance(e, dict)]
        verification_dict = state.get("verification_result")
        verification = VerificationResult(**verification_dict) if verification_dict else None

        active_provider = self.provider or (state.get("metadata") or {}).get("provider")
        active_model = self.model or (state.get("metadata") or {}).get("model")

        try:
            final_answer, citations = await self.synthesizer.synthesize(
                query=state["query"],
                evidence=evidence_objects,
                verification=verification,
                is_partial=is_partial,
                provider=active_provider,
                model=active_model,
            )
        except Exception as exc:
            logger.error("Synthesizer failed: %s", exc)
            final_answer = f"Research completed but synthesis failed: {exc}"
            citations = []

        citation_dicts = [c.model_dump() for c in citations]

        for cit in citation_dicts:
            await self._emit(research_citation(cit))

        return {
            "final_answer": final_answer,
            "citations": citation_dicts,
            "status": ResearchStatus.COMPLETED if not is_partial else ResearchStatus.PARTIAL,
        }

    async def node_synthesize_partial(self, state: ResearchState) -> dict:
        return await self.node_synthesize(state, is_partial=True)

    # ── Conditional Edge Functions ─────────────────────────────────────────

    def should_retry(self, state: ResearchState) -> str:
        """Decide whether to retry or proceed to synthesis. Strictly bounded to 1 retry."""
        if self._cancelled:
            return "cancelled"

        retry_count = state.get("retry_count", 0)
        max_retries = min(settings.max_research_retries, 1)

        verification_dict = state.get("verification_result") or {}
        verification = VerificationResult(**verification_dict)

        if verification.sufficient:
            return "synthesize"

        if retry_count >= max_retries:
            logger.info("Max research retries (%d) reached, synthesizing with partial evidence", max_retries)
            return "synthesize_partial"

        # Check if we have new tasks to research
        new_tasks = state.get("research_tasks", [])
        pending = [t for t in new_tasks if t.get("status") == "pending"]
        if not pending:
            return "synthesize_partial"

        return "refine"

    # ── Graph Builder ──────────────────────────────────────────────────────

    def build(self) -> StateGraph:
        """Build and compile the LangGraph StateGraph."""
        graph = StateGraph(ResearchState)

        # Register nodes
        graph.add_node("plan_research", self.node_plan)
        graph.add_node("research", self.node_research)
        graph.add_node("verify_evidence", self.node_verify)
        graph.add_node("refine_queries", self.node_refine)
        graph.add_node("synthesize", self.node_synthesize)
        graph.add_node("synthesize_partial", self.node_synthesize_partial)

        # Define edges
        graph.add_edge(START, "plan_research")
        graph.add_edge("plan_research", "research")
        graph.add_edge("research", "verify_evidence")

        # Conditional: verify → synthesize or refine
        graph.add_conditional_edges(
            "verify_evidence",
            self.should_retry,
            {
                "synthesize": "synthesize",
                "synthesize_partial": "synthesize_partial",
                "refine": "refine_queries",
                "cancelled": END,
            },
        )

        # Refine → Research again (corrective loop)
        graph.add_edge("refine_queries", "research")

        # Terminal nodes
        graph.add_edge("synthesize", END)
        graph.add_edge("synthesize_partial", END)

        return graph.compile()

    async def run(
        self,
        initial_state: ResearchState,
    ) -> ResearchState:
        """Execute the full research graph asynchronously. Returns final state."""
        compiled = self.build()
        final_state: ResearchState = await compiled.ainvoke(initial_state)
        return final_state
