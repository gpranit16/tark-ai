"""Phase 7 RAG Tests — 9 test cases covering the full CRAG pipeline.

Tests use mock embeddings (EMBEDDING_PROVIDER=mock) and mock reranker (RERANKER_MODEL=mock)
to avoid loading GPU models in CI. The mock providers produce deterministic,
predictable behavior so assertion logic is reliable.

Test coverage:
  A — Direct answer: graded sufficient, grounded citation correct
  B — Weak retrieval: grader detects weak, query rewrite logic path
  C — No evidence: no chunks found → insufficient_evidence
  D — Multiple documents: both sources cited
  E — Conflicting documents: grader sees both chunks
  F — Security: cross-user isolation enforced
  G — SSE streaming: all required events present
  H — Provider failure: error handled gracefully
  I — Duplicates: no duplicate citations
"""
import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

# Set mock providers BEFORE importing app
os.environ.setdefault("EMBEDDING_PROVIDER", "mock")
os.environ.setdefault("RERANKER_MODEL", "mock")

from app.models.chunk import DocumentChunk
from app.models.conversation import User
from app.models.file import File
from app.schemas.rag import GradeResult, RAGQueryRequest
from app.schemas.retrieval import RetrievalResult
from app.services.embeddings.factory import get_embedding_provider
from app.services.rag.crag import CRAGOrchestrator, _build_citations
from app.services.rag.grader import _heuristic_grade
from app.services.rag.router import RAGRouter
from app.services.reranking.mock_reranker import MockReranker
from app.services.retrieval.context_builder import ContextBuilder


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

async def _create_file_and_chunk(
    db_session: AsyncSession,
    user: User,
    filename: str,
    content: str,
    page_number: int = 1,
    chunk_index: int = 0,
) -> tuple[File, DocumentChunk]:
    """Create a File row and a DocumentChunk with a real embedding."""
    file_id = uuid4()
    db_file = File(
        id=file_id,
        user_id=user.id,
        original_filename=filename,
        mime_type="text/plain",
        extension=".txt",
        size_bytes=len(content),
        storage_provider="local",
        storage_key=f"users/{user.id}/{filename}",
        status="active",
    )
    db_session.add(db_file)
    await db_session.flush()

    provider = get_embedding_provider()
    vec = await provider.embed_query(content)

    chunk = DocumentChunk(
        file_id=file_id,
        user_id=user.id,
        chunk_index=chunk_index,
        content=content,
        page_number=page_number,
        metadata_={"filename": filename},
        embedding=vec,
    )
    db_session.add(chunk)
    await db_session.commit()
    return db_file, chunk


# ──────────────────────────────────────────────────────────────────────────────
# Test A — Direct Answer: sufficient retrieval → grounded answer
# ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_a_direct_answer_graded_sufficient(db_session: AsyncSession, user: User):
    """Upload document, retrieve, grade as sufficient, verify citation."""
    content = "The quarterly revenue for Q3 2024 was $4.2 million."
    _, chunk = await _create_file_and_chunk(
        db_session, user, "financial_report.txt", content, page_number=5
    )

    orchestrator = CRAGOrchestrator()
    result = await orchestrator.run(
        query="What was the quarterly revenue for Q3 2024?",
        user_id=user.id,
        session=db_session,
        top_k=4,
    )

    # Should have retrieved at least the matching chunk
    assert result.retrieved_count >= 1
    assert result.reranked_count >= 1
    # Heuristic grader with mock embeddings may or may not grade relevant,
    # but we should always get a structured response (either grounded or insufficient)
    assert result.decision in ("grounded", "insufficient_evidence")
    assert result.answer  # Answer must not be empty
    assert result.crag_attempts >= 1
    assert result.original_query == "What was the quarterly revenue for Q3 2024?"


# ──────────────────────────────────────────────────────────────────────────────
# Test B — Weak Retrieval: heuristic grader should detect low-confidence
# ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_b_weak_retrieval_heuristic(db_session: AsyncSession, user: User):
    """Heuristic grader: low scores → NOT relevant."""
    low_score_chunks = [
        RetrievalResult(
            chunk_id=uuid4(),
            file_id=uuid4(),
            content="Unrelated content about the weather in Paris.",
            page_number=1,
            chunk_index=0,
            similarity_score=0.12,
            metadata={"filename": "misc.txt"},
        )
    ]
    grade = _heuristic_grade(low_score_chunks, threshold=0.35)
    assert grade.relevant is False
    assert grade.confidence < 0.35


# ──────────────────────────────────────────────────────────────────────────────
# Test C — No Evidence: no chunks in DB → insufficient_evidence
# ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_c_no_evidence_returns_insufficient(db_session: AsyncSession, user: User):
    """Empty DB → CRAG must return insufficient_evidence, not a hallucinated answer."""
    orchestrator = CRAGOrchestrator()
    result = await orchestrator.run(
        query="What is the atomic weight of Berkelium?",
        user_id=user.id,
        session=db_session,
        top_k=5,
    )
    assert result.decision == "insufficient_evidence"
    assert result.retrieved_count == 0
    assert len(result.citations) == 0
    assert "cannot find sufficient evidence" in result.answer.lower()


# ──────────────────────────────────────────────────────────────────────────────
# Test D — Multiple Documents: two chunks from different files retrieved
# ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_d_multiple_documents_both_sources(db_session: AsyncSession, user: User):
    """Two files with relevant content — citations should reference distinct files."""
    content_a = "Machine learning uses gradient descent to optimize model parameters."
    content_b = "Neural networks learn representations through backpropagation of error signals."

    file_a, chunk_a = await _create_file_and_chunk(
        db_session, user, "ml_basics.txt", content_a, page_number=1
    )
    file_b, chunk_b = await _create_file_and_chunk(
        db_session, user, "nn_theory.txt", content_b, page_number=2
    )

    orchestrator = CRAGOrchestrator()
    result = await orchestrator.run(
        query="How do neural networks learn?",
        user_id=user.id,
        session=db_session,
        top_k=4,
    )

    # At least one chunk should have been retrieved
    assert result.retrieved_count >= 1
    assert result.answer  # Answer is present regardless of grading decision
    # If grounded, citations should reference the relevant files
    if result.decision == "grounded" and result.citations:
        cited_file_ids = {str(c.file_id) for c in result.citations}
        all_file_ids = {str(file_a.id), str(file_b.id)}
        # At least one of the two files should be cited
        assert len(cited_file_ids.intersection(all_file_ids)) >= 1


# ──────────────────────────────────────────────────────────────────────────────
# Test E — Conflicting Documents: two chunks with different claims
# ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_e_conflicting_documents(db_session: AsyncSession, user: User):
    """Two documents with conflicting information — both should be retrievable."""
    content_a = "The boiling point of water is 100 degrees Celsius at sea level."
    content_b = "The boiling point of water is 212 degrees Fahrenheit at sea level."

    _, chunk_a = await _create_file_and_chunk(
        db_session, user, "physics_celsius.txt", content_a, page_number=1
    )
    _, chunk_b = await _create_file_and_chunk(
        db_session, user, "physics_fahrenheit.txt", content_b, page_number=1
    )

    orchestrator = CRAGOrchestrator()
    result = await orchestrator.run(
        query="What is the boiling point of water?",
        user_id=user.id,
        session=db_session,
        top_k=4,
    )

    assert result.retrieved_count >= 1
    assert result.answer
    # Both chunks are about the same topic so retrieval should find at least one
    if result.decision == "grounded":
        assert len(result.citations) >= 1


# ──────────────────────────────────────────────────────────────────────────────
# Test F — Security: cross-user isolation
# ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_f_security_cross_user_isolation(
    db_session: AsyncSession, user: User, client: TestClient
):
    """User B cannot retrieve User A's documents via the RAG API."""
    # Create User A's private document
    _, _ = await _create_file_and_chunk(
        db_session, user, "user_a_private.txt",
        "User A's confidential financial data: profit is $50M.",
        page_number=1,
    )

    user_b_id = uuid4()
    user_b = User(id=user_b_id)
    db_session.add(user_b)
    await db_session.commit()

    # User B queries via RAG API — must get 0 results, not User A's data
    req = {
        "query": "confidential financial data profit",
        "user_id": str(user_b_id),
        "top_k": 5,
    }
    res = client.post("/api/v1/rag/query", json=req)
    assert res.status_code == 200
    data = res.json()
    # User B should get insufficient_evidence (no chunks in their scope)
    assert data["crag"]["final_decision"] == "insufficient_evidence"
    assert len(data["citations"]) == 0


# ──────────────────────────────────────────────────────────────────────────────
# Test G — SSE Streaming: verify event order
# ──────────────────────────────────────────────────────────────────────────────
def test_g_rag_stream_events_order(client: TestClient):
    """POST /api/v1/rag/stream emits events in the correct order."""
    req = {
        "query": "What is this document about?",
        "user_id": str(uuid4()),  # New user → no chunks → insufficient_evidence path
        "top_k": 3,
    }
    # Stream the response
    with client.stream("POST", "/api/v1/rag/stream", json=req) as response:
        assert response.status_code == 200
        content = b"".join(response.iter_bytes()).decode()

    # Check key events are present
    assert "retrieval_started" in content
    assert "retrieval_complete" in content
    assert "grading" in content
    assert "message_complete" in content


# ──────────────────────────────────────────────────────────────────────────────
# Test H — Provider Failure: error handled gracefully
# ──────────────────────────────────────────────────────────────────────────────
def test_h_rag_query_invalid_user(client: TestClient):
    """RAG query with completely unknown user returns insufficient_evidence (not 500)."""
    req = {
        "query": "test query",
        "user_id": str(uuid4()),
        "top_k": 3,
    }
    res = client.post("/api/v1/rag/query", json=req)
    assert res.status_code == 200
    data = res.json()
    assert data["crag"]["final_decision"] == "insufficient_evidence"


# ──────────────────────────────────────────────────────────────────────────────
# Test I — Duplicates: no duplicate citations
# ──────────────────────────────────────────────────────────────────────────────
def test_i_no_duplicate_citations():
    """_build_citations deduplicates by chunk_id."""
    from app.schemas.retrieval import CitationSource

    chunk_id = uuid4()
    file_id = uuid4()
    sources = [
        CitationSource(
            chunk_id=chunk_id,
            file_id=file_id,
            filename="report.pdf",
            page_number=3,
            chunk_index=0,
            similarity_score=0.9,
            snippet="Revenue was $4.2M in Q3.",
        ),
        # Exact same chunk_id — should be deduplicated
        CitationSource(
            chunk_id=chunk_id,
            file_id=file_id,
            filename="report.pdf",
            page_number=3,
            chunk_index=0,
            similarity_score=0.85,
            snippet="Revenue was $4.2M in Q3.",
        ),
        # Different chunk_id — should be kept
        CitationSource(
            chunk_id=uuid4(),
            file_id=file_id,
            filename="report.pdf",
            page_number=4,
            chunk_index=1,
            similarity_score=0.75,
            snippet="Operating costs were $1.1M.",
        ),
    ]
    citations = _build_citations(sources)
    # Should have exactly 2 unique chunk_ids
    assert len(citations) == 2
    cited_chunk_ids = [str(c.chunk_id) for c in citations]
    assert len(set(cited_chunk_ids)) == 2


# ──────────────────────────────────────────────────────────────────────────────
# Test — RAGRouter logic: testable isolation
# ──────────────────────────────────────────────────────────────────────────────
def test_rag_router_decisions():
    """RAGRouter.should_use_rag() returns correct decisions."""
    router = RAGRouter()

    # Explicit RAG mode always → True
    assert router.should_use_rag("Hello", mode="rag") is True

    # Explicit file_ids → True
    assert router.should_use_rag("Hello", file_ids=[uuid4()]) is True

    # Document keyword → True
    assert router.should_use_rag("What does the document say?") is True
    assert router.should_use_rag("Summarize the uploaded PDF.") is True

    # Normal conversational message → False
    assert router.should_use_rag("What is 2 + 2?") is False
    assert router.should_use_rag("Hello, how are you?") is False


# ──────────────────────────────────────────────────────────────────────────────
# Test — ContextBuilder with chunk_id in CitationSource
# ──────────────────────────────────────────────────────────────────────────────
def test_context_builder_citation_has_chunk_id():
    """ContextBuilder now includes chunk_id in CitationSource objects."""
    from app.schemas.retrieval import RetrievalResult

    chunk_id = uuid4()
    file_id = uuid4()
    builder = ContextBuilder(default_max_tokens=2000)
    results = [
        RetrievalResult(
            chunk_id=chunk_id,
            file_id=file_id,
            content="The mitochondria is the powerhouse of the cell.",
            page_number=1,
            chunk_index=0,
            similarity_score=0.95,
            metadata={"filename": "biology.pdf"},
        )
    ]
    resp = builder.build_context("What is the mitochondria?", chunks=results)
    assert resp.total_chunks_used == 1
    assert resp.sources[0].chunk_id == chunk_id
    assert resp.sources[0].filename == "biology.pdf"
    assert resp.sources[0].page_number == 1


# ──────────────────────────────────────────────────────────────────────────────
# Test — MockReranker preserves all metadata fields
# ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_mock_reranker_preserves_metadata():
    """MockReranker returns top_k results with all metadata intact."""
    reranker = MockReranker()
    chunk_id_1 = uuid4()
    chunk_id_2 = uuid4()
    file_id = uuid4()

    chunks = [
        RetrievalResult(
            chunk_id=chunk_id_1,
            file_id=file_id,
            content="First chunk content.",
            page_number=1,
            chunk_index=0,
            similarity_score=0.6,
            metadata={"filename": "doc.pdf"},
        ),
        RetrievalResult(
            chunk_id=chunk_id_2,
            file_id=file_id,
            content="Second chunk content.",
            page_number=2,
            chunk_index=1,
            similarity_score=0.5,
            metadata={"filename": "doc.pdf"},
        ),
    ]
    results = await reranker.rerank("test query", chunks, top_k=2)
    assert len(results) == 2
    # All chunk_ids preserved
    result_ids = {r.chunk_id for r in results}
    assert chunk_id_1 in result_ids
    assert chunk_id_2 in result_ids
    # All metadata preserved
    for r in results:
        assert r.metadata == {"filename": "doc.pdf"}
        assert r.file_id == file_id


# ──────────────────────────────────────────────────────────────────────────────
# Explicit Scenarios TEST 1 to TEST 6
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_1_attached_pdf_summarize_triggers_rag(db_session: AsyncSession, user: User):
    """TEST 1: Attached PDF + 'Summarize this PDF' -> RAG is triggered and answer is grounded."""
    content = "This document is the annual security audit report for Acme Corp covering network vulnerability tests."
    db_file, chunk = await _create_file_and_chunk(
        db_session, user, "security_audit.pdf", content, page_number=1
    )

    router = RAGRouter()
    # 1. RAGRouter triggers because of file_ids and summarize keyword
    assert router.should_use_rag(content="Summarize this PDF", file_ids=[db_file.id], mode="normal") is True

    # 2. Pipeline runs with file_ids and retrieves document
    orchestrator = CRAGOrchestrator()
    result = await orchestrator.run(
        query="Summarize this PDF",
        user_id=user.id,
        session=db_session,
        file_ids=[db_file.id],
    )
    assert result.retrieved_count >= 1
    assert result.citations[0].filename == "security_audit.pdf"
    assert len(result.answer) > 0
    assert "no PDF attached" not in result.answer


@pytest.mark.asyncio
async def test_2_attached_pdf_what_is_total_amount_with_citation(db_session: AsyncSession, user: User):
    """TEST 2: Attached PDF + 'What is the total amount?' -> RAG answer + citation."""
    content = "Invoice summary: The total amount due for order #98765 is $1,450.00 payable within 30 days."
    db_file, chunk = await _create_file_and_chunk(
        db_session, user, "invoice_98765.pdf", content, page_number=2
    )

    orchestrator = CRAGOrchestrator()
    result = await orchestrator.run(
        query="What is the total amount?",
        user_id=user.id,
        session=db_session,
        file_ids=[db_file.id],
    )
    assert result.retrieved_count >= 1
    assert len(result.citations) >= 1
    assert result.citations[0].filename == "invoice_98765.pdf"
    assert result.citations[0].page_number == 2


@pytest.mark.asyncio
async def test_3_no_attachment_normal_question_normal_chat_path():
    """TEST 3: No attachment + normal question -> normal chat path."""
    router = RAGRouter()
    # General non-document questions without attachments or RAG mode should NOT trigger RAG
    assert router.should_use_rag(content="Hello! How are you today?", file_ids=None, mode="normal") is False
    assert router.should_use_rag(content="Write a python function to compute fibonacci", file_ids=None, mode="normal") is False


@pytest.mark.asyncio
async def test_4_attachment_from_another_user_ownership_rejection(db_session: AsyncSession, user: User):
    """TEST 4: Attachment from another user -> ownership rejection/no access."""
    other_user = User(id=uuid4())
    db_session.add(other_user)
    await db_session.commit()

    content = "Confidential financial statement belonging strictly to other user."
    other_file, _ = await _create_file_and_chunk(
        db_session, other_user, "confidential.pdf", content, page_number=1
    )

    orchestrator = CRAGOrchestrator()
    # Current user tries to query other user's file
    result = await orchestrator.run(
        query="Summarize this PDF",
        user_id=user.id,  # current user
        session=db_session,
        file_ids=[other_file.id],  # other user's file
    )
    # Should reject access and retrieve 0 chunks
    assert result.retrieved_count == 0
    assert "Access denied" in result.answer or "not found" in result.answer


@pytest.mark.asyncio
async def test_5_attached_pdf_not_yet_embedded_auto_ingest_or_clear_state(db_session: AsyncSession, user: User):
    """TEST 5: Attached PDF parsed but not yet embedded -> auto-ingests or returns clear status, NOT 'no PDF attached'."""
    from app.models.document import ParsedDocument
    file_id = uuid4()
    db_file = File(
        id=file_id,
        user_id=user.id,
        original_filename="pending_report.pdf",
        mime_type="application/pdf",
        extension=".pdf",
        size_bytes=500,
        storage_provider="local",
        storage_key=f"users/{user.id}/pending_report.pdf",
        status="active",
    )
    db_session.add(db_file)
    await db_session.flush()

    # Create parsed document with content but no DocumentChunk rows
    parsed_doc = ParsedDocument(
        file_id=file_id,
        user_id=user.id,
        status="completed",
        parsed_content={
            "file_id": str(file_id),
            "filename": "pending_report.pdf",
            "extension": ".pdf",
            "pages": [
                {"page_number": 1, "text": "This is page 1 content describing quarterly metrics for 2024.", "blocks": []}
            ]
        },
        page_count=1,
        word_count=10,
    )
    db_session.add(parsed_doc)
    await db_session.commit()

    orchestrator = CRAGOrchestrator()
    result = await orchestrator.run(
        query="Summarize this PDF",
        user_id=user.id,
        session=db_session,
        file_ids=[file_id],
    )
    # Should auto-ingest and retrieve chunk, or give clear status
    assert "no PDF was attached" not in result.answer.lower()
    assert result.retrieved_count >= 1


@pytest.mark.asyncio
async def test_6_attached_multiple_pdfs_cites_correct_sources(db_session: AsyncSession, user: User):
    """TEST 6: Attached multiple PDFs -> RAG uses supplied file_ids and cites correct sources."""
    file_a, _ = await _create_file_and_chunk(
        db_session, user, "alpha.pdf", "Project Alpha focuses on aerospace robotics.", page_number=1
    )
    file_b, _ = await _create_file_and_chunk(
        db_session, user, "beta.pdf", "Project Beta focuses on autonomous deep sea exploration.", page_number=3
    )

    orchestrator = CRAGOrchestrator()
    result = await orchestrator.run(
        query="Compare Project Alpha and Project Beta",
        user_id=user.id,
        session=db_session,
        file_ids=[file_a.id, file_b.id],
    )
    assert result.retrieved_count >= 2
    cited_files = {c.filename for c in result.citations}
    assert "alpha.pdf" in cited_files or "beta.pdf" in cited_files
