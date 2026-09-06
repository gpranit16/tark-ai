from datetime import datetime
from typing import Any, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ChunkResponse(BaseModel):
    id: UUID
    file_id: UUID
    user_id: UUID
    project_id: Optional[UUID] = None
    parsed_document_id: Optional[UUID] = None
    chunk_index: int
    content: str
    page_number: int
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class RetrievalQueryRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Search query string")
    user_id: UUID = Field(..., description="User ID for ownership scoping")
    project_id: Optional[UUID] = Field(default=None, description="Optional project ID scope")
    file_ids: Optional[List[UUID]] = Field(default=None, description="Optional list of file IDs to restrict search")
    top_k: int = Field(default=5, ge=1, le=50, description="Number of top chunks to return")


class RetrievalResult(BaseModel):
    chunk_id: UUID
    file_id: UUID
    project_id: Optional[UUID] = None
    content: str
    page_number: int
    chunk_index: int
    similarity_score: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetrievalResponse(BaseModel):
    query: str
    results: List[RetrievalResult]
    retrieval_type: str  # "vector", "keyword", "hybrid"
    count: int


class ContextBuildRequest(BaseModel):
    query: str = Field(..., min_length=1)
    user_id: UUID
    project_id: Optional[UUID] = None
    file_ids: Optional[List[UUID]] = None
    top_k: int = Field(default=5, ge=1, le=50)
    max_tokens: Optional[int] = Field(default=4000, ge=100, le=32000)
    retrieval_type: str = Field(default="hybrid", description="vector, keyword, or hybrid")


class CitationSource(BaseModel):
    chunk_id: UUID
    file_id: UUID
    filename: str
    page_number: int
    chunk_index: int
    similarity_score: float
    snippet: str


class ContextBuildResponse(BaseModel):
    query: str
    context_text: str
    sources: List[CitationSource]
    total_chunks_used: int


class IngestionStatusResponse(BaseModel):
    file_id: UUID
    status: str  # "pending", "processing", "completed", "failed"
    chunk_count: int = 0
    failure_reason: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
