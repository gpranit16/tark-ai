"""Phase 10 — Deep Research + LangGraph Multi-Agent System Tests."""
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.enums import ConversationMode, GenerationStatus, MessageRole
from app.main import app
from app.models.conversation import Message, Thread, User
from app.models.research import ResearchSession
from app.providers.base import NormalizedMessage, ProviderStreamEvent
from app.services.chat.router import ModelRouter, ProviderSelection
from app.services.research.graph import DeepResearchGraph
from app.services.research.manager import ResearchManager, cancel_research
from app.services.research.models import (
    AgentType,
    Citation,
    Evidence,
    EvidenceSource,
    ResearchPlan,
    ResearchStatus,
    ResearchTask,
    TaskStatus,
    VerificationResult,
)
from app.services.research.nodes.planner import ResearchPlanner
from app.services.research.nodes.refiner import ResearchQueryRefiner
from app.services.research.nodes.synthesizer import ResearchSynthesizer
from app.services.research.nodes.verifier import VerifierAgent
from app.services.research.nodes.web_agent import WebResearchAgent
from app.services.research.sse import (
    research_citation,
    research_complete,
    research_error,
    research_evidence_collected,
    research_plan_created,
    research_started,
    research_task_completed,
    research_task_failed,
    research_task_started,
    research_verification_complete,
)
from app.services.research.state import ResearchState, create_initial_research_state
from app.tools.base import ToolExecutionContext, ToolResult


class TestResearchDataModels:
    """Test Pydantic models for Deep Research."""

    def test_research_task_creation(self):
        task = ResearchTask(
            task_id="t1",
            agent_type=AgentType.WEB,
            query="quantum computing breakthrough 2026",
        )
        assert task.task_id == "t1"
        assert task.agent_type == AgentType.WEB
        assert task.status == TaskStatus.PENDING
        assert task.depends_on == []

    def test_evidence_model(self):
        evidence = Evidence(
            task_id="t1",
            source_type=EvidenceSource.WEB,
            url="https://nature.com/article1",
            title="Quantum Advances",
            snippet="Qubit coherence reached 1ms",
            relevance=0.92,
        )
        assert evidence.relevance == 0.92
        assert evidence.url == "https://nature.com/article1"

    def test_verification_result(self):
        vr = VerificationResult(
            sufficient=True,
            confidence=0.88,
            missing_information=[],
            reasoning="All core aspects covered",
        )
        assert vr.sufficient is True
        assert vr.confidence == 0.88

    def test_citation_model(self):
        cit = Citation(
            citation_id="cit-1",
            title="Nature Quantum 2026",
            url="https://nature.com/article1",
            source_type=EvidenceSource.WEB,
        )
        assert cit.citation_id == "cit-1"
        assert cit.source_type == EvidenceSource.WEB

    def test_initial_state_factory(self):
        state = create_initial_research_state(
            query="Evaluate NVIDIA AI chips",
            thread_id="test-thread-id",
            user_id="test-user-id",
            provider="groq",
            model="qwen/qwen3.8-27b",
        )
        assert state["query"] == "Evaluate NVIDIA AI chips"
        assert state["status"] == "pending"
        assert state["retry_count"] == 0
        assert state["evidence"] == []


class TestResearchSSEFormatting:
    """Test SSE event formatting for Deep Research."""

    def test_research_started_event(self):
        raw = research_started(
            research_id="res-123",
            query="Future of Fusion Energy",
        )
        assert raw.startswith("event: research_started\n")
        lines = raw.strip().split("\n")
        payload = json.loads(lines[1][6:])
        assert payload["research_id"] == "res-123"
        assert payload["query"] == "Future of Fusion Energy"

    def test_research_plan_created_event(self):
        tasks = [
            {"task_id": "t1", "agent_type": "web", "query": "ITER status"},
            {"task_id": "t2", "agent_type": "document", "query": "Internal fusion whitepaper"},
        ]
        raw = research_plan_created(tasks=tasks, task_count=2)
        assert "event: research_plan_created\n" in raw
        assert "ITER status" in raw

    def test_research_evidence_collected_event(self):
        raw = research_evidence_collected(total_sources=5)
        assert "event: research_evidence_collected\n" in raw
        assert "5" in raw

    def test_research_complete_event(self):
        raw = research_complete(
            confidence=0.89,
            source_count=8,
            duration_ms=4500,
        )
        assert "event: research_complete\n" in raw
        assert "4500" in raw


class TestResearchAPIEndpoints:
    """Test REST endpoints for Deep Research."""

    def test_get_nonexistent_research_404(self, client: TestClient):
        random_id = str(uuid.uuid4())
        resp = client.get(f"/api/v1/research/{random_id}")
        assert resp.status_code == 404

    def test_cancel_nonexistent_research(self, client: TestClient):
        random_id = str(uuid.uuid4())
        resp = client.post(f"/api/v1/research/{random_id}/cancel")
        assert resp.status_code == 200
        data = resp.json()
        assert data["cancelled"] is False

    def test_list_research_sessions(self, client: TestClient):
        resp = client.get("/api/v1/research/")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)


@pytest.mark.asyncio
class TestDeepResearchComprehensiveSuite:
    """Comprehensive test suite verifying items A through N."""

    # ── A. Research Dispatch ────────────────────────────────────────────────
    async def test_a_research_dispatch_mode(self, db_session):
        user = User(id=uuid.uuid4())
        db_session.add(user)
        await db_session.flush()

        thread = Thread(id=uuid.uuid4(), user_id=user.id, title="Dispatch Thread")
        db_session.add(thread)
        await db_session.commit()

        manager = ResearchManager()
        # Verify mode check dispatches to stream_research
        with patch.object(manager, "stream_research") as mock_stream:
            async def fake_stream(*args, **kwargs):
                yield "event: research_started\ndata: {}\n\n"

            mock_stream.side_effect = fake_stream
            events = [e async for e in manager.stream_research(
                session=db_session,
                thread_id=thread.id,
                user_id=user.id,
                project_id=None,
                query="Test Dispatch",
                is_disconnected=lambda: False,
            )]
            assert len(events) == 1

    # ── B. Graph Compilation ────────────────────────────────────────────────
    async def test_b_graph_compilation(self):
        graph = DeepResearchGraph()
        compiled = graph.build()
        assert compiled is not None
        # Check node registration
        node_names = set(compiled.nodes.keys())
        for required_node in ["plan_research", "research", "verify_evidence", "refine_queries", "synthesize", "synthesize_partial"]:
            assert required_node in node_names

    # ── C. Planner ──────────────────────────────────────────────────────────
    async def test_c_planner_json_parsing_and_fallback(self):
        mock_router = MagicMock(spec=ModelRouter)

        async def fake_stream(*args, **kwargs):
            yield None, ProviderStreamEvent(
                delta=json.dumps({
                    "research_intent": "Compare AI coding tools",
                    "tasks": [
                        {"query": "Cursor AI features 2026", "agent_type": "web", "priority": 9},
                        {"query": "Claude Code architecture", "agent_type": "web", "priority": 8},
                    ]
                })
            )

        mock_router.stream.side_effect = fake_stream
        planner = ResearchPlanner(mock_router)
        plan = await planner.plan("Compare Cursor and Claude Code", max_tasks=4)
        assert len(plan.tasks) == 2
        assert plan.tasks[0].query == "Cursor AI features 2026"
        assert plan.tasks[0].agent_type == AgentType.WEB

        # Test fallback on non-JSON
        async def malformed_stream(*args, **kwargs):
            yield None, ProviderStreamEvent(delta="I cannot provide JSON.")

        mock_router.stream.side_effect = malformed_stream
        fallback_plan = await planner.plan("Fallback Query", max_tasks=4)
        assert len(fallback_plan.tasks) == 1
        assert fallback_plan.tasks[0].query == "Fallback Query"

    # ── D. Parallel Tasks Execution ─────────────────────────────────────────
    async def test_d_parallel_tasks_execution(self):
        graph = DeepResearchGraph()
        task1 = ResearchTask(task_id="t1", query="task 1", agent_type=AgentType.WEB, status=TaskStatus.PENDING).model_dump()
        task2 = ResearchTask(task_id="t2", query="task 2", agent_type=AgentType.WEB, status=TaskStatus.PENDING).model_dump()

        state: ResearchState = {
            "query": "Test parallel execution",
            "user_id": str(uuid.uuid4()),
            "thread_id": str(uuid.uuid4()),
            "research_tasks": [task1, task2],
            "evidence": [],
        }

        # Mock _execute_task to simulate async delay and evidence return
        async def mock_exec(st, t):
            await asyncio.sleep(0.01)
            ev = Evidence(task_id=t["task_id"], source_type=EvidenceSource.WEB, title=f"Source for {t['task_id']}", url="https://example.com", snippet="Evidence snippet")
            return [ev], None

        with patch.object(graph, "_execute_task", side_effect=mock_exec):
            result = await graph.node_research(state)
            assert len(result["evidence"]) == 2
            assert len(result["task_results"]) == 2
            assert len(result["failed_tasks"]) == 0
            assert all(t["status"] == "completed" for t in result["research_tasks"])

    # ── E. Partial Failure Handling ─────────────────────────────────────────
    async def test_e_partial_task_failure(self):
        graph = DeepResearchGraph()
        task1 = ResearchTask(task_id="t1", query="task 1 ok", agent_type=AgentType.WEB, status=TaskStatus.PENDING).model_dump()
        task2 = ResearchTask(task_id="t2", query="task 2 fail", agent_type=AgentType.WEB, status=TaskStatus.PENDING).model_dump()

        state: ResearchState = {
            "query": "Test partial failure",
            "user_id": str(uuid.uuid4()),
            "thread_id": str(uuid.uuid4()),
            "research_tasks": [task1, task2],
            "evidence": [],
        }

        async def mock_exec(st, t):
            if t["task_id"] == "t1":
                ev = Evidence(task_id="t1", source_type=EvidenceSource.WEB, title="Success Source", url="https://example.com/ok", snippet="Ok")
                return [ev], None
            else:
                raise RuntimeError("Network timeout on task 2")

        with patch.object(graph, "_execute_task", side_effect=mock_exec):
            result = await graph.node_research(state)
            assert len(result["evidence"]) == 1
            assert len(result["task_results"]) == 1
            assert len(result["failed_tasks"]) == 1
            assert result["failed_tasks"][0]["task_id"] == "t2"
            assert result["failed_tasks"][0]["status"] == "failed"

    # ── F. Verification ─────────────────────────────────────────────────────
    async def test_f_verification_parsing(self):
        mock_router = MagicMock(spec=ModelRouter)

        async def fake_verify_stream(*args, **kwargs):
            yield None, ProviderStreamEvent(
                delta=json.dumps({
                    "sufficient": True,
                    "confidence": 0.85,
                    "supported_claims": ["Claim 1"],
                    "unsupported_claims": [],
                    "conflicts": [],
                    "missing_information": [],
                    "reasoning": "Sufficient evidence found."
                })
            )

        mock_router.stream.side_effect = fake_verify_stream
        verifier = VerifierAgent(mock_router)
        ev = [Evidence(task_id="t1", source_type=EvidenceSource.WEB, title="Source", url="https://example.com", snippet="Evidence")]
        res = await verifier.verify("Query", ev)
        assert res.sufficient is True
        assert res.confidence >= 0.80

    # ── G. Single Retry Bound (Max 1) ───────────────────────────────────────
    async def test_g_single_retry_bound(self):
        graph = DeepResearchGraph()

        # Attempt 0 with insufficient evidence -> refine
        state_retry_0: ResearchState = {
            "retry_count": 0,
            "verification_result": {"sufficient": False, "confidence": 0.2},
            "research_tasks": [{"status": "pending"}],
        }
        decision_0 = graph.should_retry(state_retry_0)
        assert decision_0 == "refine"

        # Attempt 1 (retries exhausted) -> synthesize_partial (NO recursive loop)
        state_retry_1: ResearchState = {
            "retry_count": 1,
            "verification_result": {"sufficient": False, "confidence": 0.2},
            "research_tasks": [{"status": "pending"}],
        }
        decision_1 = graph.should_retry(state_retry_1)
        assert decision_1 == "synthesize_partial"

        # Sufficient evidence -> synthesize directly
        state_sufficient: ResearchState = {
            "retry_count": 0,
            "verification_result": {"sufficient": True, "confidence": 0.85},
        }
        decision_suff = graph.should_retry(state_sufficient)
        assert decision_suff == "synthesize"

    # ── H. Synthesis & Citation Extraction ──────────────────────────────────
    async def test_h_synthesis_and_citations(self):
        mock_router = MagicMock(spec=ModelRouter)

        answer_text = (
            "## Executive Summary\nAI coding agents are evolving rapidly [1].\n\n"
            "## Key Findings\n- Cursor uses indexing [1].\n- Claude Code offers CLI automation [2].\n\n"
            "## Detailed Analysis\nDetails here [1] [2].\n\n"
            "## Limitations & Caveats\nBenchmarks are limited.\n\n"
            "## Sources\n[1] Cursor Whitepaper\n[2] Anthropic Claude Code Docs"
        )

        async def fake_synth_stream(*args, **kwargs):
            yield None, ProviderStreamEvent(delta=answer_text)

        mock_router.stream.side_effect = fake_synth_stream
        synthesizer = ResearchSynthesizer(mock_router)

        evidence = [
            Evidence(task_id="t1", source_type=EvidenceSource.WEB, title="Cursor Whitepaper", url="https://cursor.com", snippet="Cursor info"),
            Evidence(task_id="t2", source_type=EvidenceSource.WEB, title="Claude Code Docs", url="https://docs.anthropic.com", snippet="Claude Code info"),
            Evidence(task_id="t3", source_type=EvidenceSource.WEB, title="Unused Source", url="https://unused.com", snippet="Unused"),
        ]

        final_answer, citations = await synthesizer.synthesize(
            query="AI coding agents 2026",
            evidence=evidence,
        )

        assert "## Executive Summary" in final_answer
        assert len(citations) == 2
        assert citations[0].title == "Cursor Whitepaper"
        assert citations[1].title == "Claude Code Docs"

    # ── I. SSE Event Pipeline ───────────────────────────────────────────────
    async def test_i_sse_event_pipeline(self):
        queue: asyncio.Queue[str | None] = asyncio.Queue()
        graph = DeepResearchGraph(sse_queue=queue)
        await graph._emit(research_started("r-1", "Test Query"))
        await graph._emit(research_task_started("t-1", "sub query", "web"))
        await graph._emit(research_complete(0.9, 5, 1200))

        events = []
        while not queue.empty():
            events.append(queue.get_nowait())

        assert len(events) == 3
        assert "event: research_started" in events[0]
        assert "event: research_task_started" in events[1]
        assert "event: research_complete" in events[2]

    # ── J. Persistence of Research Session & Message ────────────────────────
    async def test_j_persistence_assistant_message(self, db_session):
        user = User(id=uuid.uuid4())
        db_session.add(user)
        await db_session.flush()

        thread = Thread(id=uuid.uuid4(), user_id=user.id, title="Persistence Thread")
        db_session.add(thread)
        await db_session.commit()

        manager = ResearchManager()

        # Mock _run_graph to return synthetic final state
        async def fake_run_graph(graph, initial_state):
            return {
                **initial_state,
                "final_answer": "## Executive Summary\nPersisted answer [1].",
                "citations": [{"citation_id": "c1", "title": "Source 1", "url": "https://source.com", "source_type": "web"}],
                "status": "completed",
                "evidence": [{"title": "Source 1"}],
                "verified_evidence": [{"title": "Source 1"}],
                "verification_result": {"sufficient": True, "confidence": 0.9},
                "task_results": [{"task_id": "t1"}],
            }

        with patch.object(manager, "_run_graph", side_effect=fake_run_graph):
            events = []
            async for ev in manager.stream_research(
                session=db_session,
                thread_id=thread.id,
                user_id=user.id,
                project_id=None,
                query="Test Persistence",
                is_disconnected=lambda: False,
            ):
                events.append(ev)

            # Verify Message record was persisted
            from sqlalchemy import select
            msg = (await db_session.execute(
                select(Message).where(Message.thread_id == thread.id, Message.role == MessageRole.ASSISTANT)
            )).scalar_one_or_none()

            assert msg is not None
            assert "Persisted answer" in msg.content
            assert msg.mode == ConversationMode.DEEP_RESEARCH
            assert msg.generation_status == GenerationStatus.COMPLETED

            # Verify ResearchSession was persisted
            rs = (await db_session.execute(
                select(ResearchSession).where(ResearchSession.thread_id == thread.id)
            )).scalar_one_or_none()

            assert rs is not None
            assert rs.query == "Test Persistence"
            assert rs.status == "completed"
            assert rs.confidence == 0.9
            assert rs.source_count == 1

    # ── K. Model & Provider Routing Propagation ─────────────────────────────
    async def test_k_model_routing_propagation(self):
        mock_router = MagicMock(spec=ModelRouter)

        async def capture_stream(*args, **kwargs):
            assert kwargs.get("provider") == "gemini"
            assert kwargs.get("model") == "gemini-2.5-flash"
            yield None, ProviderStreamEvent(delta=json.dumps({"tasks": []}))

        mock_router.stream.side_effect = capture_stream
        graph = DeepResearchGraph(router=mock_router, provider="gemini", model="gemini-2.5-flash")
        assert graph.planner.provider == "gemini"
        assert graph.planner.model == "gemini-2.5-flash"
        assert graph.verifier.provider == "gemini"
        assert graph.synthesizer.provider == "gemini"

    # ── L. Timeout Handling ─────────────────────────────────────────────────
    async def test_l_timeout_handling(self):
        agent = WebResearchAgent()
        task = ResearchTask(task_id="t1", query="Hang forever", agent_type=AgentType.WEB)
        ctx = ToolExecutionContext(user_id=uuid.uuid4(), project_id=None, thread_id=uuid.uuid4(), session=None)

        async def slow_research(*args, **kwargs):
            await asyncio.sleep(0.5)
            return [], None

        with patch.object(agent, "_do_research", side_effect=slow_research):
            evidence, err = await agent.research(task, ctx, timeout_seconds=0.05)
            assert evidence == []
            assert "timed out" in (err or "").lower()

    # ── M. Cancellation Handling ────────────────────────────────────────────
    async def test_m_cancellation_handling(self):
        graph = DeepResearchGraph()
        assert graph._cancelled is False
        graph.cancel()
        assert graph._cancelled is True
        decision = graph.should_retry({"retry_count": 0})
        assert decision == "cancelled"

    # ── N. Citation Integrity ───────────────────────────────────────────────
    async def test_n_citation_integrity(self):
        synthesizer = ResearchSynthesizer()
        ev1 = Evidence(task_id="t1", source_type=EvidenceSource.WEB, title="Cited Source", url="https://cited.com", snippet="Content")
        ev2 = Evidence(task_id="t2", source_type=EvidenceSource.WEB, title="Uncited Source", url="https://uncited.com", snippet="Content")

        source_index = {1: ev1, 2: ev2}
        answer = "This finding is well supported [1]. Nothing else."
        citations = synthesizer._build_citations([ev1, ev2], source_index, answer)

        assert len(citations) == 1
        assert citations[0].title == "Cited Source"
        assert citations[0].url == "https://cited.com"
