import uuid
import pytest
from unittest.mock import AsyncMock, patch
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import uuid4

from app.models.chunk import DocumentChunk
from app.models.conversation import User
from app.models.file import File
from app.schemas.rag import GradeResult
from app.schemas.retrieval import CitationSource, ContextBuildResponse, RetrievalResult
from app.services.embeddings.factory import get_embedding_provider
from app.services.rag.crag import CRAGOrchestrator
from app.services.retrieval.context_builder import ContextBuilder
from app.services.retrieval.hybrid import HybridRetriever, clear_retrieval_cache


async def _create_test_file_and_chunk(
    db_session: AsyncSession,
    user: User,
    filename: str,
    content: str,
    page_number: int = 1,
    chunk_index: int = 0,
) -> tuple[File, DocumentChunk]:
    file_id = uuid4()
    db_file = File(
        id=file_id,
        user_id=user.id,
        original_filename=filename,
        mime_type="application/pdf",
        extension=".pdf",
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
        embedding=vec,
        metadata_={"filename": filename},
    )
    db_session.add(chunk)
    await db_session.commit()
    await db_session.refresh(db_file)
    await db_session.refresh(chunk)
    return db_file, chunk


def test_context_builder_rejects_out_of_scope_chunks():
    """ContextBuilder invariant: chunks not in allowed_file_ids must be dropped."""
    builder = ContextBuilder()
    scoped_file_id = uuid.uuid4()
    foreign_file_id = uuid.uuid4()

    valid_chunk = RetrievalResult(
        chunk_id=uuid.uuid4(),
        file_id=scoped_file_id,
        project_id=None,
        content="PAN Number: ABCDE1234F",
        page_number=1,
        chunk_index=0,
        similarity_score=0.92,
        metadata={"filename": "Pan.pdf"},
    )
    foreign_chunk = RetrievalResult(
        chunk_id=uuid.uuid4(),
        file_id=foreign_file_id,
        project_id=None,
        content="Revaluation course list: Math 101, Physics 102",
        page_number=1,
        chunk_index=0,
        similarity_score=0.95,
        metadata={"filename": "RevaluationCourses.pdf"},
    )

    # When allowed_file_ids is set to [scoped_file_id]
    context = builder.build_context(
        query="What is the PAN number?",
        chunks=[valid_chunk, foreign_chunk],
        allowed_file_ids=[scoped_file_id],
    )

    assert context.total_chunks_used == 1
    assert "ABCDE1234F" in context.context_text
    assert "Revaluation" not in context.context_text
    assert len(context.sources) == 1
    assert context.sources[0].file_id == scoped_file_id
    assert context.sources[0].filename == "Pan.pdf"


@pytest.mark.asyncio
async def test_crag_scoped_no_evidence_refusal(db_session: AsyncSession, user: User):
    """When a document is scoped but evidence is absent, refusal mentions the document name."""
    pan_file, chunk = await _create_test_file_and_chunk(
        db_session, user, "Pan.pdf", "Income Tax Dept PAN: ABCDE1234F Name: Rahul", page_number=1
    )

    mock_retriever = AsyncMock()
    # Simulate retriever returning 0 chunks for out-of-scope query on Pan.pdf
    mock_retriever.search.return_value = []

    mock_rewriter = AsyncMock()
    mock_rewriter.rewrite.return_value = "President of France in Pan.pdf"

    orchestrator = CRAGOrchestrator(
        hybrid_retriever=mock_retriever,
        query_rewriter=mock_rewriter,
    )

    result = await orchestrator.run(
        query="According to Pan.pdf, who is the President of France?",
        user_id=user.id,
        session=db_session,
    )

    assert result.decision == "insufficient_evidence"
    assert "Pan.pdf" in result.answer
    assert result.citations == []
    # Verify retry preserved the file_ids
    for call_args in mock_retriever.search.call_args_list:
        assert call_args.kwargs.get("file_ids") == [pan_file.id]


@pytest.mark.asyncio
async def test_crag_scoped_citations_only_from_scoped_document(db_session: AsyncSession, user: User):
    """Grounded answer from scoped document only contains scoped citations."""
    pan_file, chunk = await _create_test_file_and_chunk(
        db_session, user, "Pan.pdf", "Permanent Account Number: ABCDE1234F. Name: Rahul Sharma. DOB: 12/07/2006.", page_number=1
    )

    pan_chunk = RetrievalResult(
        chunk_id=chunk.id,
        file_id=pan_file.id,
        project_id=None,
        content=chunk.content,
        page_number=1,
        chunk_index=0,
        similarity_score=0.90,
        metadata={"filename": "Pan.pdf"},
    )

    mock_retriever = AsyncMock()
    mock_retriever.search.return_value = [pan_chunk]

    mock_grader = AsyncMock()
    mock_grader.grade.return_value = GradeResult(
        relevant=True,
        confidence=0.90,
        reason="Found PAN number in document",
        selected_chunk_indices=[0],
    )

    mock_generator = AsyncMock()
    mock_generator.generate_answer.return_value = (
        "The PAN number in Pan.pdf is ABCDE1234F [Source: Pan.pdf | Page: 1]."
    )

    orchestrator = CRAGOrchestrator(
        hybrid_retriever=mock_retriever,
        grader=mock_grader,
        answer_generator=mock_generator,
    )

    result = await orchestrator.run(
        query="What is the PAN number in Pan.pdf?",
        user_id=user.id,
        session=db_session,
    )

    assert result.decision == "grounded"
    assert "ABCDE1234F" in result.answer
    assert len(result.citations) == 1
    assert result.citations[0].filename == "Pan.pdf"
    assert result.citations[0].file_id == pan_file.id
    assert "screenshot" not in str(result.citations)


@pytest.mark.asyncio
async def test_retrieval_cache_scoped_isolation(db_session: AsyncSession, user: User):
    """Retrieval cache must isolate scoped queries from global queries."""
    clear_retrieval_cache()
    retriever = HybridRetriever()

    file_id = uuid.uuid4()

    mock_vector = AsyncMock()
    mock_keyword = AsyncMock()

    retriever.vector_retriever = mock_vector
    retriever.keyword_retriever = mock_keyword

    mock_vector.search.return_value = []
    mock_keyword.search.return_value = []

    # 1. Execute query with explicit file scope
    await retriever.search(
        session=db_session,
        query="Pan number",
        user_id=user.id,
        file_ids=[file_id],
        use_cache=True,
    )

    # 2. Execute same query globally (file_ids=None)
    await retriever.search(
        session=db_session,
        query="Pan number",
        user_id=user.id,
        file_ids=None,
        use_cache=True,
    )

    # Both must invoke underlying retrievers because cache keys are strictly distinct
    assert mock_vector.search.call_count == 2
    assert mock_keyword.search.call_count == 2
