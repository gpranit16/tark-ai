import io
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chunk import DocumentChunk
from app.models.conversation import Project, User
from app.models.document import ParsedDocument
from app.models.file import File
from app.schemas.document import Block, Page, ParsedDocumentData
from app.schemas.retrieval import RetrievalQueryRequest
from app.services.chunking.document_chunker import DocumentChunker
from app.services.embeddings.factory import get_embedding_provider
from app.services.embeddings.ingestion import EmbeddingIngestionService
from app.services.retrieval.context_builder import ContextBuilder
from app.services.retrieval.hybrid import HybridRetriever
from app.services.retrieval.keyword import KeywordRetriever
from app.services.retrieval.vector import VectorRetriever


@pytest.fixture
def mock_storage(monkeypatch):
    storage_dict = {}

    class MockStorage:
        @property
        def provider_name(self): return "mock"
        async def upload(self, stream, key, mime): storage_dict[key] = stream.read()
        async def download(self, key): return storage_dict.get(key, b"sample content")
        async def delete(self, key): storage_dict.pop(key, None)
        async def exists(self, key): return key in storage_dict

    monkeypatch.setattr("app.services.files.get_storage_provider", lambda *args, **kwargs: MockStorage())
    monkeypatch.setattr("app.services.document_processing.get_storage_provider", lambda *args, **kwargs: MockStorage())


# 1. Test Document Chunker
def test_document_chunker():
    file_id = uuid4()
    doc_data = ParsedDocumentData(
        file_id=file_id,
        filename="ai_report.pdf",
        extension=".pdf",
        pages=[
            Page(
                page_number=1,
                text="Artificial Intelligence (AI) is transforming modern computing.",
                blocks=[
                    Block(block_type="heading", content="1. Introduction to AI", page_number=1),
                    Block(block_type="paragraph", content="Artificial Intelligence is the simulation of human intelligence.", page_number=1),
                ]
            ),
            Page(
                page_number=2,
                text="Vector databases enable scalable semantic retrieval.",
                blocks=[
                    Block(block_type="heading", content="2. Vector Search", page_number=2),
                    Block(block_type="paragraph", content="pgvector is an open-source vector similarity extension for PostgreSQL.", page_number=2),
                ]
            )
        ]
    )

    chunker = DocumentChunker(default_chunk_size=100, default_chunk_overlap=20)
    chunks = chunker.chunk_document(doc_data)

    assert len(chunks) >= 2
    assert chunks[0]["chunk_index"] == 0
    assert chunks[0]["page_number"] == 1
    assert "source_file_id" in chunks[0]["metadata"]
    assert chunks[0]["metadata"]["filename"] == "ai_report.pdf"


# 2. Test Embedding Provider (Dimension = 1024)
@pytest.mark.asyncio
async def test_embedding_provider_dimension():
    provider = get_embedding_provider()
    assert provider.dimension == 1024

    texts = ["PostgreSQL pgvector similarity search", "BGE-M3 multi-lingual dense embedding model"]
    embeddings = await provider.embed_documents(texts)

    assert len(embeddings) == 2
    assert len(embeddings[0]) == 1024
    assert len(embeddings[1]) == 1024

    query_vec = await provider.embed_query("search query")
    assert len(query_vec) == 1024


# 3. Test Ingestion Pipeline & Database Storage
@pytest.mark.asyncio
async def test_ingestion_pipeline_and_idempotency(db_session: AsyncSession, user: User, project: Project):
    file_id = uuid4()
    doc_id = uuid4()

    db_file = File(
        id=file_id,
        user_id=user.id,
        project_id=project.id,
        original_filename="sample_guide.txt",
        mime_type="text/plain",
        extension=".txt",
        size_bytes=100,
        storage_provider="local",
        storage_key=f"users/{user.id}/sample_guide.txt",
        status="active"
    )
    db_session.add(db_file)

    parsed_data = ParsedDocumentData(
        file_id=file_id,
        filename="sample_guide.txt",
        extension=".txt",
        pages=[
            Page(
                page_number=1,
                text="Section 1: Quantum Computing basics.\nSection 2: Qubits and Superposition.",
                blocks=[
                    Block(block_type="heading", content="Quantum Computing basics", page_number=1),
                    Block(block_type="paragraph", content="Qubits can exist in superposition of states.", page_number=1),
                ]
            )
        ]
    )

    parsed_doc = ParsedDocument(
        id=doc_id,
        file_id=file_id,
        user_id=user.id,
        status="completed",
        parsed_content=parsed_data.model_dump(mode="json"),
        page_count=1,
        word_count=10,
    )
    db_session.add(parsed_doc)
    await db_session.commit()

    ingestion_service = EmbeddingIngestionService()

    # Ingest 1st time
    status_resp = await ingestion_service.ingest_file(db_session, file_id, user.id)
    assert status_resp.status == "completed"
    assert status_resp.chunk_count >= 1

    # Ingest 2nd time (Idempotency check: should not duplicate chunks)
    status_resp2 = await ingestion_service.ingest_file(db_session, file_id, user.id)
    assert status_resp2.status == "completed"
    assert status_resp2.chunk_count == status_resp.chunk_count


# 4. Test Vector Retrieval & Keyword Retrieval & Hybrid Retrieval
@pytest.mark.asyncio
async def test_retrieval_methods(db_session: AsyncSession, user: User, project: Project):
    file_id = uuid4()
    db_file = File(
        id=file_id,
        user_id=user.id,
        project_id=project.id,
        original_filename="db_overview.txt",
        mime_type="text/plain",
        extension=".txt",
        size_bytes=200,
        storage_provider="local",
        storage_key=f"users/{user.id}/db_overview.txt",
        status="active"
    )
    db_session.add(db_file)
    await db_session.flush()

    provider = get_embedding_provider()

    content_a = "PostgreSQL is an advanced relational database with JSON and vector extensions."
    content_b = "Python is a high-level programming language used extensively in data science."

    vec_a = await provider.embed_query(content_a)
    vec_b = await provider.embed_query(content_b)

    chunk_a = DocumentChunk(
        file_id=file_id,
        user_id=user.id,
        project_id=project.id,
        chunk_index=0,
        content=content_a,
        page_number=1,
        metadata_={"filename": "db_overview.txt"},
        embedding=vec_a
    )
    chunk_b = DocumentChunk(
        file_id=file_id,
        user_id=user.id,
        project_id=project.id,
        chunk_index=1,
        content=content_b,
        page_number=2,
        metadata_={"filename": "db_overview.txt"},
        embedding=vec_b
    )
    db_session.add_all([chunk_a, chunk_b])
    await db_session.commit()

    # 4a. Vector Search
    vector_retriever = VectorRetriever()
    v_results = await vector_retriever.search(
        session=db_session,
        query="relational database pgvector",
        user_id=user.id,
        top_k=2
    )
    assert len(v_results) == 2
    assert v_results[0].chunk_id == chunk_a.id
    assert v_results[0].similarity_score > 0.0

    # 4b. Keyword Search
    keyword_retriever = KeywordRetriever()
    k_results = await keyword_retriever.search(
        session=db_session,
        query="relational database",
        user_id=user.id,
        top_k=2
    )
    assert len(k_results) >= 1
    assert k_results[0].chunk_id == chunk_a.id

    # 4c. Hybrid Search
    hybrid_retriever = HybridRetriever(vector_retriever, keyword_retriever)
    h_results = await hybrid_retriever.search(
        session=db_session,
        query="relational database",
        user_id=user.id,
        top_k=2
    )
    assert len(h_results) >= 1
    assert h_results[0].chunk_id == chunk_a.id


# 5. Test ContextBuilder & Source Citations
def test_context_builder():
    file_id = uuid4()
    builder = ContextBuilder(default_max_tokens=500)

    from app.schemas.retrieval import RetrievalResult
    results = [
        RetrievalResult(
            chunk_id=uuid4(),
            file_id=file_id,
            content="Neural networks consist of interconnected layers of nodes.",
            page_number=3,
            chunk_index=2,
            similarity_score=0.92,
            metadata={"filename": "deep_learning.pdf"}
        ),
        RetrievalResult(
            chunk_id=uuid4(),
            file_id=file_id,
            content="Backpropagation computes the gradient of the loss function.",
            page_number=4,
            chunk_index=3,
            similarity_score=0.88,
            metadata={"filename": "deep_learning.pdf"}
        )
    ]

    context_resp = builder.build_context(query="neural networks", chunks=results)

    assert context_resp.total_chunks_used == 2
    assert "Neural networks consist" in context_resp.context_text
    assert "Backpropagation computes" in context_resp.context_text
    assert len(context_resp.sources) == 2
    assert context_resp.sources[0].filename == "deep_learning.pdf"
    assert context_resp.sources[0].page_number == 3
    assert context_resp.sources[0].chunk_index == 2


# 6. Test User Ownership Isolation in Retrieval APIs
@pytest.mark.asyncio
async def test_retrieval_ownership_isolation(client: TestClient, db_session: AsyncSession, user: User):
    user_a = user
    user_b_id = uuid4()
    user_b = User(id=user_b_id)
    db_session.add(user_b)

    file_a_id = uuid4()
    db_file_a = File(
        id=file_a_id,
        user_id=user_a.id,
        original_filename="secret.txt",
        mime_type="text/plain",
        extension=".txt",
        size_bytes=100,
        storage_provider="local",
        storage_key=f"users/{user_a.id}/secret.txt",
        status="active"
    )
    db_session.add(db_file_a)
    await db_session.flush()

    provider = get_embedding_provider()
    content_private = "Confidential secret keys for User A."
    vec = await provider.embed_query(content_private)

    chunk = DocumentChunk(
        file_id=file_a_id,
        user_id=user_a.id,
        chunk_index=0,
        content=content_private,
        page_number=1,
        metadata_={"filename": "secret.txt"},
        embedding=vec
    )
    db_session.add(chunk)
    await db_session.commit()

    # User A searches -> finds chunk
    req_a = {
        "query": "Confidential secret keys",
        "user_id": str(user_a.id),
        "top_k": 3
    }
    res_a = client.post("/api/v1/retrieval/vector", json=req_a)
    assert res_a.status_code == 200
    assert len(res_a.json()["results"]) == 1

    # User B searches -> finds NOTHING
    req_b = {
        "query": "Confidential secret keys",
        "user_id": str(user_b_id),
        "top_k": 3
    }
    res_b = client.post("/api/v1/retrieval/vector", json=req_b)
    assert res_b.status_code == 200
    assert len(res_b.json()["results"]) == 0

    # Hybrid search for User B -> 0 results
    res_b_hybrid = client.post("/api/v1/retrieval/hybrid", json=req_b)
    assert res_b_hybrid.status_code == 200
    assert len(res_b_hybrid.json()["results"]) == 0


# 7. Test Context Preview API Endpoint
@pytest.mark.asyncio
async def test_context_preview_api(client: TestClient, db_session: AsyncSession, user: User):
    file_id = uuid4()
    db_file = File(
        id=file_id,
        user_id=user.id,
        original_filename="arch.md",
        mime_type="text/markdown",
        extension=".md",
        size_bytes=100,
        storage_provider="local",
        storage_key=f"users/{user.id}/arch.md",
        status="active"
    )
    db_session.add(db_file)
    await db_session.flush()

    provider = get_embedding_provider()
    vec = await provider.embed_query("FastAPI async backend architecture.")

    chunk = DocumentChunk(
        file_id=file_id,
        user_id=user.id,
        chunk_index=0,
        content="FastAPI async backend architecture.",
        page_number=1,
        metadata_={"filename": "arch.md"},
        embedding=vec
    )
    db_session.add(chunk)
    await db_session.commit()

    req = {
        "query": "FastAPI architecture",
        "user_id": str(user.id),
        "top_k": 2,
        "retrieval_type": "hybrid"
    }
    res = client.post("/api/v1/retrieval/context", json=req)
    assert res.status_code == 200
    data = res.json()
    assert "FastAPI async backend" in data["context_text"]
    assert len(data["sources"]) == 1
    assert data["sources"][0]["filename"] == "arch.md"
