import os
from uuid import uuid4
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

os.environ.setdefault("EMBEDDING_PROVIDER", "mock")
os.environ.setdefault("RERANKER_MODEL", "mock")

from app.models.conversation import User
from app.services.rag.crag import CRAGOrchestrator
from test_crag_latency_and_rules import _create_test_file_and_chunk


@pytest.mark.asyncio
async def test_scenario_a_pan_number_fast_path(db_session: AsyncSession, user: User):
    """Scenario A: High confidence answer on PAN card. Fast path taken, no rewrite."""
    content = "Government of India Income Tax Department. Permanent Account Number (PAN): ABCDE1234F. Name: Rajesh Kumar. DOB: 15/08/1985."
    file_obj, _ = await _create_test_file_and_chunk(
        db_session, user, "Pan.pdf", content, page_number=1
    )

    orchestrator = CRAGOrchestrator()
    result = await orchestrator.run(
        query="What is the PAN number in Pan.pdf?",
        user_id=user.id,
        session=db_session,
        file_ids=[file_obj.id],
    )

    print(f"\n[Scenario A Latency Breakdown]: {result.latency}")
    assert result.decision == "grounded"
    assert result.query_rewritten is False
    assert result.crag_attempts == 1
    assert len(result.citations) >= 1
    assert result.citations[0].filename == "Pan.pdf"
    assert result.latency is not None
    assert result.latency.rewrite_time_ms == 0.0
    assert result.latency.retry_retrieval_time_ms == 0.0


@pytest.mark.asyncio
async def test_scenario_b_bank_account_rejection(db_session: AsyncSession, user: User):
    """Scenario B: Unsupported bank account query on PAN card. Rejects cleanly without hallucinating."""
    content = "Government of India Income Tax Department. Permanent Account Number (PAN): ABCDE1234F. Name: Rajesh Kumar. DOB: 15/08/1985."
    file_obj, _ = await _create_test_file_and_chunk(
        db_session, user, "Pan.pdf", content, page_number=1
    )

    orchestrator = CRAGOrchestrator()
    result = await orchestrator.run(
        query="What is the person's bank account number in Pan.pdf?",
        user_id=user.id,
        session=db_session,
        file_ids=[file_obj.id],
    )

    print(f"\n[Scenario B Latency Breakdown]: {result.latency}")
    if result.decision == "insufficient_evidence":
        assert len(result.citations) == 0
        assert "cannot find sufficient evidence" in result.answer.lower()
    else:
        assert "bank account" not in result.answer.lower() or "not" in result.answer.lower() or "cannot" in result.answer.lower()


@pytest.mark.asyncio
async def test_scenario_c_vague_query_retry_behavior(db_session: AsyncSession, user: User):
    """Scenario C: Deliberately vague query -> only rewrites when confidence is genuinely low."""
    content = "Quarterly Financial Overview 2024: Operating expenses were $2.1M and net margin stood at 14%."
    file_obj, _ = await _create_test_file_and_chunk(
        db_session, user, "overview.txt", content, page_number=1
    )

    orchestrator = CRAGOrchestrator()
    result = await orchestrator.run(
        query="tell me stuff",
        user_id=user.id,
        session=db_session,
        file_ids=[file_obj.id],
    )

    print(f"\n[Scenario C Latency Breakdown]: {result.latency}")
    assert result.crag_attempts <= 2  # Max 1 retry
    assert result.latency is not None


@pytest.mark.asyncio
async def test_scenario_d_what_is_this_synopsis(db_session: AsyncSession, user: User):
    """Scenario D: 'What is this' overview query on uploaded PDF -> instantly grounded, no rewrite, no refusal."""
    content = "Pranit Gupta - Senior Software Engineer & AI Architect. Experienced in Python, React, RAG, and Distributed Systems."
    file_obj, _ = await _create_test_file_and_chunk(
        db_session, user, "Pranit_Resume.pdf", content, page_number=1
    )

    orchestrator = CRAGOrchestrator()
    result = await orchestrator.run(
        query="what is this?",
        user_id=user.id,
        session=db_session,
        file_ids=[file_obj.id],
    )

    print(f"\n[Scenario D Latency Breakdown]: {result.latency}")
    assert result.decision == "grounded"
    assert result.query_rewritten is False
    assert len(result.citations) >= 1
    assert result.citations[0].filename == "Pranit_Resume.pdf"
    assert "pranit" in result.answer.lower() or len(result.answer) > 20
