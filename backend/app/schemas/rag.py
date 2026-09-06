from typing import Any, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class RAGQueryRequest(BaseModel):
    """Request schema for POST /api/v1/rag/query and /api/v1/rag/stream."""

    query: str = Field(..., min_length=1, description="User query string")
    user_id: UUID = Field(..., description="User ID for ownership scoping")
    project_id: Optional[UUID] = Field(default=None, description="Optional project scope")
    file_ids: Optional[List[UUID]] = Field(
        default=None, description="Restrict retrieval to these file IDs"
    )
    top_k: int = Field(default=8, ge=1, le=50, description="Candidates to retrieve before reranking")


class RAGCitation(BaseModel):
    """Structured citation pointing to an exact document chunk."""

    chunk_id: UUID
    file_id: UUID
    filename: str
    page_number: int
    chunk_index: int
    similarity_score: float
    reference: str = Field(description="Human-readable reference string, e.g. 'report.pdf p.3'")
    snippet: str


class GradeResult(BaseModel):
    """Output of RetrievalGrader — determines if evidence is sufficient."""

    relevant: bool
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str
    selected_chunk_indices: List[int] = Field(
        default_factory=list,
        description="Indices into the input chunk list that are relevant",
    )


class CRAGDecision(str):
    GROUNDED = "grounded"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class RAGLatencyBreakdown(BaseModel):
    """Detailed timing metrics (in ms) for pipeline stages. Safe: does not log secrets or contents."""

    embedding_time_ms: float = 0.0
    retrieval_time_ms: float = 0.0
    rerank_time_ms: float = 0.0
    grader_time_ms: float = 0.0
    rewrite_time_ms: float = 0.0
    retry_retrieval_time_ms: float = 0.0
    generation_time_ms: float = 0.0
    total_time_ms: float = 0.0
    reranker_used: bool = False


class CRAGResult(BaseModel):
    """Full result from the CRAG orchestrator."""

    decision: str  # "grounded" | "insufficient_evidence"
    answer: str
    citations: List[RAGCitation]
    context_text: str

    # Retrieval metadata
    retrieved_count: int
    reranked_count: int
    grading_confidence: float
    reranker_used: bool = False

    # CRAG metadata
    crag_attempts: int
    query_rewritten: bool
    original_query: str
    final_query: str

    # Timing / Latency instrumentation
    latency: Optional[RAGLatencyBreakdown] = None


class RAGRetrievalMeta(BaseModel):
    retrieved: int
    reranked: int
    confidence: float
    reranker_used: bool = False
    latency: Optional[RAGLatencyBreakdown] = None


class RAGCRAGMeta(BaseModel):
    attempts: int
    rewritten: bool
    final_decision: str


class RAGQueryResponse(BaseModel):
    """JSON response for POST /api/v1/rag/query."""

    answer: str
    citations: List[RAGCitation]
    retrieval: RAGRetrievalMeta
    crag: RAGCRAGMeta
