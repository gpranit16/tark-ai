"""Project schemas for Phase 11."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreate(BaseModel):
    user_id: UUID | None = None
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    custom_instructions: str | None = None
    avatar: str | None = Field(default=None, max_length=64)
    project_metadata: dict | None = None


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    custom_instructions: str | None = None
    avatar: str | None = Field(default=None, max_length=64)
    is_archived: bool | None = None
    project_metadata: dict | None = None


class ProjectResponse(BaseModel):
    id: UUID
    user_id: UUID
    name: str
    description: str | None = None
    custom_instructions: str | None = None
    avatar: str | None = None
    is_archived: bool = False
    project_metadata: dict | None = None
    created_at: datetime
    updated_at: datetime

    # Summary counts (optional)
    thread_count: int = 0
    file_count: int = 0
    memory_count: int = 0
    research_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class ProjectDetailResponse(ProjectResponse):
    """Detailed project view including summary stats."""
    pass
