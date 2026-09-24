"""
DeepResearchGraph — Phase 10 / Deep Research 2.0 LangGraph StateGraph orchestrator.

Graph flow:
  START → plan_research → research (parallel Tavily + tools) →
  verify_evidence →
    sufficient? → plan_sections → fanout_sections → synthesize → images → END
    insufficient & retries < MAX → refine_queries → research (loop)
    retries exhausted → synthesize_partial → images → END
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
    AgentType, Evidence, ImageItem, ImagePlan, ResearchPlan, ResearchQuery,
    ResearchStatus, ResearchTask, SectionResult, SectionTask, TaskStatus,
    VerificationResult,
)
from app.services.research.nodes.document_agent import DocumentResearchAgent
from app.services.research.nodes.finance_agent import FinanceResearchAgent
from app.services.research.nodes.image_planner import ImagePlanner
from app.services.research.nodes.planner import ResearchPlanner
from app.services.research.nodes.refiner import ResearchQueryRefiner
from app.services.research.nodes.router_node import ResearchRouter
from app.services.research.nodes.section_worker import SectionWorker
from app.services.research.nodes.synthesizer import ResearchSynthesizer
from app.services.research.nodes.verifier import VerifierAgent
from app.services.research.nodes.web_agent import WebResearchAgent
from app.services.research.pollinations import PollinationsImageProvider
from app.services.research.sse import (
    research_cancelled,
    research_citation,
    research_classifying,
    research_complete,
    research_error,
    research_evidence_collected,
    research_image_completed,
    research_image_started,
    research_plan_created,
    research_planning,
    research_queries_generated,
    research_retry,
    research_search_completed,
    research_search_started,
    research_section_completed,
    research_section_started,
    research_sources_deduplicated,
    research_started,
    research_synthesis_started,
    research_task_completed,
    research_task_failed,
    research_task_progress,
    research_task_started,
    research_verification_complete,
    research_verification_started,
)
from app.services.research.state import ResearchState
from app.services.research.tavily import TavilyResearchService
from app.tools.base import ToolExecutionContext
from app.tools.executor import ToolExecutor
from app.tools.registry import get_tool_registry

logger = logging.getLogger(__name__)
settings = get_settings()


class DeepResearchGraph:
    """
    LangGraph-based Deep Research 2.0 orchestrator.

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

        # Initialize nodes with intelligent provider/model routing
        self.router_node = ResearchRouter(self.router, provider=self.provider, model=self.model)
        self.planner = ResearchPlanner(self.router, provider=self.provider, model=self.model)
        self.tavily_service = TavilyResearchService()
        self.section_worker = SectionWorker(self.router, provider=self.provider, model=self.model)
        self.image_planner = ImagePlanner(self.router, provider=self.provider, model=self.model)
        self.pollinations = PollinationsImageProvider()

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
        """Planner node — classifies research scope, generates search queries, and task plan."""
        logger.info("[RESEARCH] planning query=%r", state.get("query", "")[:80])
        query = state["query"]
        active_provider = self.provider or (state.get("metadata") or {}).get("provider")
        active_model = self.model or (state.get("metadata") or {}).get("model")

        # 1. Scope Classification
        await self._emit(research_classifying())
        router_res = await self.router_node.classify(query, provider=active_provider, model=active_model)

        # 2. Targeted Search Queries Generation
        search_queries = await self.planner.generate_queries(
            query,
            recency_days=router_res.recency_days,
            count=router_res.queries_needed,
            provider=active_provider,
            model=active_model,
        )
        query_dicts = [q.model_dump() for q in search_queries]
        await self._emit(research_queries_generated(query_dicts, len(query_dicts)))

        # 3. Tasks Plan (for backwards compatibility with existing UI and tests)
        await self._emit(research_planning())
        max_tasks = min(settings.max_research_tasks, 8)

        try:
            plan: ResearchPlan = await self.planner.plan(
                query,
                max_tasks=max_tasks,
                provider=active_provider,
                model=active_model,
            )
        except Exception as exc:
            logger.error("Planner failed: %s", exc)
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
            "research_mode": router_res.mode,
            "recency_days": router_res.recency_days,
            "search_queries": query_dicts,
            "plan": plan_dict,
            "research_tasks": task_dicts,
            "status": ResearchStatus.RESEARCHING,
            "rewritten_queries": [q.query for q in search_queries] + [t["query"] for t in task_dicts],
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
        Parallel research node — executes Tavily web searches and agent tasks simultaneously.
        """
        search_queries_raw = state.get("search_queries", [])
        tasks_raw = state.get("research_tasks", [])
        pending = [t for t in tasks_raw if t.get("status") == "pending"]

        all_evidence: list[dict] = []
        all_results: list[dict] = []
        all_failed: list[dict] = []

        # 1. Parallel Tavily Discovery
        if search_queries_raw and self.tavily_service.api_key:
            await self._emit(research_search_started(len(search_queries_raw)))
            parsed_queries = [ResearchQuery(**q) for q in search_queries_raw]
            tavily_evidence = await self.tavily_service.search_queries(parsed_queries)
            await self._emit(research_search_completed(len(tavily_evidence)))
            all_evidence.extend([e.model_dump() for e in tavily_evidence])

        # 2. Agent tasks (documents, finance, or web fallback if Tavily not available)
        updated_tasks = [dict(t) for t in tasks_raw]
        task_map = {t["task_id"]: t for t in updated_tasks}

        non_web_tasks = [t for t in pending if t.get("agent_type") in ("document", "finance")]
        web_tasks = [t for t in pending if t.get("agent_type") not in ("document", "finance")]

        # When Tavily provides evidence, web tasks are already covered
        tasks_to_execute = non_web_tasks + (web_tasks if not all_evidence else [])

        if all_evidence:
            for task_dict in web_tasks:
                if task_dict not in tasks_to_execute:
                    t_id = task_dict.get("task_id", "")
                    mapped = task_map.get(t_id, task_dict)
                    mapped["status"] = "completed"
                    all_results.append(mapped)
                    await self._emit(research_task_completed(t_id, len(all_evidence)))

        if tasks_to_execute:
            max_parallel = min(settings.max_parallel_research_tasks, len(tasks_to_execute))
            for batch_start in range(0, len(tasks_to_execute), max_parallel):
                if self._cancelled:
                    break

                batch = tasks_to_execute[batch_start : batch_start + max_parallel]
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
                            await self._emit(research_task_completed(t_id, len(evidence_list)))

        # 3. Deduplicate evidence objects to calculate actual usable source count
        raw_combined = [Evidence(**e) for e in state.get("evidence", []) + all_evidence if isinstance(e, dict)]
        deduped_combined = self._deduplicate_evidence(raw_combined)
        usable_count = len(deduped_combined)

        await self._emit(research_sources_deduplicated(usable_count))
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
        import uuid
        def _safe_uuid(val: Any) -> uuid.UUID:
            if isinstance(val, uuid.UUID):
                return val
            try:
                return uuid.UUID(str(val))
            except Exception:
                return uuid.uuid5(uuid.NAMESPACE_DNS, str(val))

        return ToolExecutionContext(
            user_id=_safe_uuid(state.get("user_id", "default-user")),
            project_id=_safe_uuid(state["project_id"]) if state.get("project_id") else None,
            thread_id=_safe_uuid(state.get("thread_id", "default-thread")),
            session=None,
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

        existing_tasks = state.get("research_tasks", [])
        combined_tasks = existing_tasks + new_task_dicts

        return {
            "research_tasks": combined_tasks,
            "rewritten_queries": tried + new_queries,
            "retry_count": retry_count,
            "status": ResearchStatus.RESEARCHING,
        }

    async def node_plan_sections(self, state: ResearchState) -> dict:
        """Plan 4–8 structured section tasks for parallel fanout workers."""
        query = state["query"]
        evidence_raw = state.get("verified_evidence", state.get("evidence", []))
        evidence_objs = [Evidence(**e) for e in evidence_raw if isinstance(e, dict)]

        active_provider = self.provider or (state.get("metadata") or {}).get("provider")
        active_model = self.model or (state.get("metadata") or {}).get("model")

        try:
            sections = await self.planner.plan_sections(
                query, evidence_objs, max_sections=6, provider=active_provider, model=active_model
            )
        except Exception as exc:
            logger.error("[PLAN_SECTIONS] Section planning fallback: %s", exc)
            sections = [
                SectionTask(id="s1", title="Executive Summary & Core Overview", goal="Synthesize high-level landscape"),
                SectionTask(id="s2", title="Technical Architecture & Details", goal="Analyze core mechanisms"),
                SectionTask(id="s3", title="Comparisons & Real-World Tradeoffs", goal="Evaluate alternatives"),
                SectionTask(id="s4", title="Limitations & Future Outlook", goal="Document caveats and gaps"),
            ]

        section_dicts = [s.model_dump() for s in sections]
        return {
            "section_tasks": section_dicts,
            "status": ResearchStatus.RESEARCHING,
        }

    async def node_fanout_sections(self, state: ResearchState) -> dict:
        """Execute parallel evidence-grounded SectionWorkers for each section task."""
        sections_raw = state.get("section_tasks", [])
        if not sections_raw:
            return {"section_results": []}

        evidence_raw = state.get("verified_evidence", state.get("evidence", []))
        evidence_objs = [Evidence(**e) for e in evidence_raw if isinstance(e, dict)]

        active_provider = self.provider or (state.get("metadata") or {}).get("provider")
        active_model = self.model or (state.get("metadata") or {}).get("model")

        # Bound section fanout to 4 sections and 2 concurrent workers to prevent quota exhaustion
        sections_to_run = sections_raw[:4]
        sem = asyncio.Semaphore(2)

        async def _run_worker(st_dict: dict) -> SectionResult:
            st = SectionTask(**st_dict)
            await self._emit(research_section_started(st.id, st.title))
            try:
                async with sem:
                    res = await self.section_worker.execute_task(
                        st, evidence_objs, provider=active_provider, model=active_model, timeout=25.0
                    )
            except Exception as exc:
                logger.error("[SECTION_WORKER] Error in worker %s: %s", st.id, exc)
                res = SectionResult(
                    section_title=st.title,
                    content=f"### {st.title}\n\n*Error generating section: {exc}*",
                    citations=[],
                    unsupported_claims=[],
                )
            await self._emit(research_section_completed(st.id, st.title))
            return res

        results = await asyncio.gather(*[_run_worker(st) for st in sections_to_run], return_exceptions=True)
        valid_results: list[dict] = []
        for r in results:
            if isinstance(r, SectionResult):
                valid_results.append(r.model_dump())
            elif isinstance(r, Exception):
                logger.warning("[FANOUT] Worker failed: %s", r)

        return {
            "section_results": valid_results,
            "status": ResearchStatus.SYNTHESIZING,
        }

    async def node_synthesize(self, state: ResearchState, is_partial: bool = False) -> dict:
        """Synthesizer node — produces final answer with citations and section drafts."""
        logger.info("[RESEARCH] synthesis is_partial=%s", is_partial)
        await self._emit(research_synthesis_started())

        verified_ev_raw = state.get("verified_evidence", state.get("evidence", []))
        evidence_objects = [Evidence(**e) for e in verified_ev_raw if isinstance(e, dict)]
        verification_dict = state.get("verification_result")
        verification = VerificationResult(**verification_dict) if verification_dict else None
        section_results = state.get("section_results", [])

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
                section_results=section_results,
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

    async def node_images(self, state: ResearchState) -> dict:
        """Optional visual generation node via Pollinations."""
        query = state["query"]
        final_answer = state.get("final_answer") or ""

        active_provider = self.provider or (state.get("metadata") or {}).get("provider")
        active_model = self.model or (state.get("metadata") or {}).get("model")

        try:
            image_plan = await self.image_planner.plan_images(
                query=query, report_summary=final_answer[:1200], provider=active_provider, model=active_model
            )
            if image_plan.should_generate and image_plan.images:
                await self._emit(research_image_started(len(image_plan.images)))
                try:
                    generated = await asyncio.wait_for(
                        self.pollinations.generate_images_parallel(image_plan.images),
                        timeout=10.0,
                    )
                except asyncio.TimeoutError:
                    logger.warning("[IMAGES] Image generation timed out after 10s")
                    generated = []
                gen_dicts = [g.model_dump() for g in generated]
                await self._emit(research_image_completed(gen_dicts))
                return {
                    "image_plan": image_plan.model_dump(),
                    "generated_images": gen_dicts,
                }
        except Exception as exc:
            logger.warning("[IMAGES] Visuals generation skipped: %s", exc)

        return {"image_plan": None, "generated_images": []}

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
        graph.add_node("plan_sections", self.node_plan_sections)
        graph.add_node("fanout_sections", self.node_fanout_sections)
        graph.add_node("synthesize", self.node_synthesize)
        graph.add_node("synthesize_partial", self.node_synthesize_partial)
        graph.add_node("images", self.node_images)

        # Define edges
        graph.add_edge(START, "plan_research")
        graph.add_edge("plan_research", "research")
        graph.add_edge("research", "verify_evidence")

        # Conditional: verify → plan_sections (for synthesis) or refine
        graph.add_conditional_edges(
            "verify_evidence",
            self.should_retry,
            {
                "synthesize": "plan_sections",
                "synthesize_partial": "synthesize_partial",
                "refine": "refine_queries",
                "cancelled": END,
            },
        )

        graph.add_edge("refine_queries", "research")
        graph.add_edge("plan_sections", "fanout_sections")
        graph.add_edge("fanout_sections", "synthesize")
        graph.add_edge("synthesize", "images")
        graph.add_edge("synthesize_partial", "images")
        graph.add_edge("images", END)

        return graph.compile()

    async def run(
        self,
        initial_state: ResearchState,
    ) -> ResearchState:
        """Execute the full research graph asynchronously. Returns final state."""
        compiled = self.build()
        final_state: ResearchState = await compiled.ainvoke(initial_state)
        return final_state
