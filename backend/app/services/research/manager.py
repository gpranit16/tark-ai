"""
ResearchManager — Phase 10 entry point.

Coordinates the full Deep Research lifecycle:
- Validates the request
- Initializes ResearchState
- Runs the LangGraph graph
- Streams SSE events
- Persists the final answer and session metadata
- Handles cancellation
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.enums import ConversationMode, GenerationStatus, MessageRole
from app.models.conversation import Message
from app.models.research import ResearchSession
from app.services.chat.router import ModelRouter
from app.services.chat.sse import message_complete, message_start, text_delta
from app.services.research.graph import DeepResearchGraph
from app.services.research.models import ResearchStatus
from app.services.research.sse import (
    message_end,
    research_cancelled,
    research_complete,
    research_error,
    research_started,
)
from app.services.research.state import ResearchState
from app.tools.executor import ToolExecutor
from app.tools.registry import get_tool_registry

logger = logging.getLogger(__name__)
settings = get_settings()

# Registry of active research sessions for cancellation support
_ACTIVE_RESEARCH: dict[str, DeepResearchGraph] = {}


class ResearchManager:
    """
    Entry point for Deep Research mode.

    Orchestrates the LangGraph execution and streams SSE events
    back through the existing chat SSE infrastructure.
    """

    def __init__(self, router: Optional[ModelRouter] = None) -> None:
        self.router = router or ModelRouter.from_settings()

    async def stream_research(
        self,
        *,
        session: AsyncSession,
        thread_id: UUID,
        user_id: UUID,
        project_id: Optional[UUID],
        query: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        is_disconnected,
    ) -> AsyncIterator[str]:
        """
        Execute Deep Research and yield SSE events.

        This is the main streaming interface, yielding research SSE events
        followed by the final answer text_delta events.
        """
        if not settings.deep_research_enabled:
            yield text_delta("Deep Research is currently disabled. Please use Normal mode.")
            return

        research_id = str(uuid.uuid4())
        start_time = time.perf_counter()
        logger.info(
            "[RESEARCH] dispatch research_id=%s thread_id=%s user_id=%s provider=%s model=%s query=%r",
            research_id,
            thread_id,
            user_id,
            provider,
            model,
            query[:80],
        )

        # Create session record in DB
        research_session = ResearchSession(
            id=uuid.UUID(research_id),
            thread_id=thread_id,
            user_id=user_id,
            project_id=project_id,
            query=query,
            status=ResearchStatus.PLANNING,
        )
        try:
            session.add(research_session)
            await session.commit()
            await session.refresh(research_session)
        except Exception as exc:
            logger.error("Failed to create research session: %s", exc)
            await session.rollback()

        # Set up SSE queue and graph
        sse_queue: asyncio.Queue[str | None] = asyncio.Queue()
        graph = DeepResearchGraph(
            router=self.router,
            sse_queue=sse_queue,
            provider=provider,
            model=model,
        )
        _ACTIVE_RESEARCH[research_id] = graph

        # Initial state
        initial_state: ResearchState = {
            "query": query,
            "user_id": str(user_id),
            "thread_id": str(thread_id),
            "research_id": research_id,
            "project_id": str(project_id) if project_id else None,
            "plan": None,
            "research_tasks": [],
            "task_results": [],
            "evidence": [],
            "failed_tasks": [],
            "verified_evidence": [],
            "verification_result": None,
            "rewritten_queries": [],
            "retry_count": 0,
            "final_answer": None,
            "citations": [],
            "status": ResearchStatus.PLANNING,
            "errors": [],
            "cancelled": False,
            "metadata": {"research_id": research_id, "provider": provider, "model": model},
        }

        # Emit research_started
        yield research_started(research_id, query)
        yield message_start(provider or "groq", model or "deep_research", ConversationMode.DEEP_RESEARCH, False)

        final_state: Optional[ResearchState] = None
        graph_task: Optional[asyncio.Task] = None

        try:
            # Run graph in background, drain SSE queue in foreground
            graph_task = asyncio.create_task(self._run_graph(graph, initial_state))

            async for event in self._drain_queue(sse_queue, graph_task, is_disconnected):
                if graph.cancel if hasattr(graph, "_cancelled") and graph._cancelled else False:
                    break
                yield event

            # Collect final state
            if graph_task and not graph_task.cancelled():
                try:
                    final_state = await asyncio.wait_for(graph_task, timeout=5.0)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    final_state = None

        except asyncio.CancelledError:
            graph.cancel()
            yield research_cancelled(research_id)
            await self._update_session(session, research_id, ResearchStatus.CANCELLED, 0, 0, 0.0)
            return
        except Exception as exc:
            logger.error("Research graph error for %s: %s", research_id, exc, exc_info=True)
            yield research_error(str(exc), research_id)
            await self._update_session(session, research_id, ResearchStatus.FAILED, 0, 0, 0.0)
        finally:
            _ACTIVE_RESEARCH.pop(research_id, None)
            if sse_queue:
                await sse_queue.put(None)  # Sentinel to close queue

        if final_state is None:
            yield research_error("Research did not produce a result.", research_id)
            return

        # 1. Stream final answer in chunks (ensure every text_delta is flushed)
        final_answer = final_state.get("final_answer") or ""
        citations = final_state.get("citations", [])
        status = final_state.get("status", ResearchStatus.COMPLETED)
        verified_ev = final_state.get("verified_evidence", final_state.get("evidence", []))
        evidence_count = len(citations) if citations else len(verified_ev)
        confidence = (final_state.get("verification_result") or {}).get("confidence", 0.0)

        if final_answer:
            chunk_size = 64
            for i in range(0, len(final_answer), chunk_size):
                yield text_delta(final_answer[i : i + chunk_size])

        # 2. Persist assistant message with exact final answer
        assistant_msg_id = uuid.uuid4()
        try:
            active_prov = provider or self.router._provider_for_mode(ConversationMode.DEEP_RESEARCH).value
            active_mod = model or self.router._model_for_mode(ConversationMode.DEEP_RESEARCH)
            assistant_msg = Message(
                id=assistant_msg_id,
                thread_id=thread_id,
                role=MessageRole.ASSISTANT,
                content=final_answer or "(No research output generated)",
                mode=ConversationMode.DEEP_RESEARCH,
                generation_status=GenerationStatus.COMPLETED,
                provider=active_prov,
                model=active_mod,
            )
            session.add(assistant_msg)
            await session.commit()
            await session.refresh(assistant_msg)
            assistant_msg_id = assistant_msg.id
        except Exception as exc:
            logger.error("Failed to persist research answer: %s", exc)
            await session.rollback()

        duration_ms = int((time.perf_counter() - start_time) * 1000)
        logger.info(
            "[RESEARCH] complete research_id=%s duration_ms=%d confidence=%.2f sources=%d",
            research_id,
            duration_ms,
            confidence,
            evidence_count,
        )

        # Determine final session status based on completion criteria
        if final_answer and not final_answer.startswith("Research completed but synthesis failed"):
            session_status = ResearchStatus.COMPLETED
        else:
            session_status = status

        # 3. Update research session record
        await self._update_session(
            session, research_id, session_status, evidence_count,
            final_state.get("retry_count", 0), confidence, duration_ms,
            plan=final_state.get("plan"),
            research_metadata={
                "citations": citations,
                "errors": final_state.get("errors", []),
                "tasks_completed": len(final_state.get("task_results", [])),
                "tasks_failed": len(final_state.get("failed_tasks", [])),
            },
        )

        # 4. Emit completion metrics only AFTER all text_deltas and DB persistence
        yield research_complete(confidence, evidence_count, duration_ms)

        # 5. Emit message_end as the final terminal event
        yield message_end(str(assistant_msg_id))

    async def _run_graph(
        self,
        graph: DeepResearchGraph,
        initial_state: ResearchState,
    ) -> ResearchState:
        """Run the LangGraph graph and signal queue completion."""
        try:
            final_state = await graph.run(initial_state)
            return final_state
        finally:
            await graph.sse_queue.put(None)  # Sentinel

    async def _drain_queue(
        self,
        queue: asyncio.Queue[str | None],
        graph_task: asyncio.Task,
        is_disconnected,
    ) -> AsyncIterator[str]:
        """Drain SSE events from queue until graph completes."""
        while True:
            disconnected = is_disconnected() if callable(is_disconnected) else False
            if asyncio.iscoroutine(disconnected):
                disconnected = await disconnected
            if disconnected:
                graph_task.cancel()
                return

            try:
                event = await asyncio.wait_for(queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                # Check if graph task is done
                if graph_task.done():
                    # Drain remaining events
                    while not queue.empty():
                        ev = queue.get_nowait()
                        if ev is None:
                            return
                        yield ev
                    return
                continue

            if event is None:  # Sentinel — graph finished
                return

            yield event

    async def _update_session(
        self,
        session: AsyncSession,
        research_id: str,
        status: str,
        source_count: int,
        retry_count: int,
        confidence: float,
        duration_ms: int = 0,
        plan: Optional[dict] = None,
        research_metadata: Optional[dict] = None,
    ) -> None:
        """Update the ResearchSession record in the database."""
        try:
            rs = await session.get(ResearchSession, uuid.UUID(research_id))
            if rs:
                rs.status = status
                rs.source_count = source_count
                rs.retry_count = retry_count
                rs.confidence = confidence
                rs.duration_ms = duration_ms
                if plan:
                    rs.plan = plan
                    rs.task_count = len(plan.get("tasks", []))
                if research_metadata:
                    rs.research_metadata = research_metadata
                await session.commit()
        except Exception as exc:
            logger.error("Failed to update research session: %s", exc)
            await session.rollback()


def cancel_research(research_id: str) -> bool:
    """Cancel an active research session by ID."""
    graph = _ACTIVE_RESEARCH.get(research_id)
    if graph:
        graph.cancel()
        return True
    return False


def get_active_research_ids() -> list[str]:
    """Return list of active research session IDs."""
    return list(_ACTIVE_RESEARCH.keys())
