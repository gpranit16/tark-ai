from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import MemoryCategory


class MemoryBase(BaseModel):
    category: MemoryCategory = MemoryCategory.OTHER
    key: str = Field(..., max_length=255)
    value: str
    source: str = Field(default="conversation", max_length=255)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    importance: float = Field(default=0.7, ge=0.0, le=1.0)
    is_active: bool = True
    project_id: UUID | None = None
    metadata: dict | None = None


class MemoryCreate(BaseModel):
    category: MemoryCategory = MemoryCategory.OTHER
    key: str = Field(..., min_length=1, max_length=255)
    value: str = Field(..., min_length=1)
    project_id: UUID | None = None
    source: str = Field(default="manual", max_length=255)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    importance: float = Field(default=0.7, ge=0.0, le=1.0)
    metadata: dict | None = None


class MemoryUpdate(BaseModel):
    category: MemoryCategory | None = None
    key: str | None = Field(default=None, min_length=1, max_length=255)
    value: str | None = Field(default=None, min_length=1)
    project_id: UUID | None = None
    source: str | None = Field(default=None, max_length=255)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    importance: float | None = Field(default=None, ge=0.0, le=1.0)
    is_active: bool | None = None
    metadata: dict | None = None


class MemoryRead(BaseModel):
    id: UUID
    user_id: UUID
    project_id: UUID | None
    category: MemoryCategory
    key: str
    value: str
    source: str
    confidence: float
    importance: float
    is_active: bool
    last_accessed_at: datetime | None = None
    metadata: dict | None = Field(default=None, validation_alias="metadata_")
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class MemoryListResponse(BaseModel):
    items: list[MemoryRead]
    total: int
    limit: int
    offset: int


class MemorySearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    project_id: UUID | None = None
    category: MemoryCategory | None = None
    top_k: int = Field(default=5, ge=1, le=50)


class MemoryCandidate(BaseModel):
    category: MemoryCategory
    key: str
    value: str
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    importance: float = Field(default=0.7, ge=0.0, le=1.0)
    reasoning: str | None = None


class MemoryExtractionResult(BaseModel):
    candidates: list[MemoryCandidate] = []
    skipped_reason: str | None = None
