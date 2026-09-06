"""Pydantic models for Phase 12 Coding Mode & Code Workspace."""
from __future__ import annotations

from enum import StrEnum
from typing import Any, List, Optional
from uuid import UUID
from pydantic import BaseModel, Field


class CodeChangeOperation(StrEnum):
    CREATE = "create"
    MODIFY = "modify"
    DELETE = "delete"


class CodeReviewSeverity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class CodeChange(BaseModel):
    """Normalized code-change representation."""
    file: str
    operation: str = Field(default="modify", description="create, modify, or delete")
    summary: str
    diff: Optional[str] = None
    language: Optional[str] = None
    code: Optional[str] = None


class StructuredCodeResponse(BaseModel):
    """Structured code generation/modification response."""
    summary: str
    files_changed: List[str] = Field(default_factory=list)
    changes: List[CodeChange] = Field(default_factory=list)
    tests: List[str] = Field(default_factory=list)
    notes: Optional[str] = None


class CodeReviewFinding(BaseModel):
    """Specific code review observation or issue."""
    category: str = Field(description="Bugs, Security issues, Performance, Maintainability, Correctness, Suggested changes")
    severity: CodeReviewSeverity = Field(default=CodeReviewSeverity.MEDIUM)
    file: Optional[str] = None
    line: Optional[int] = None
    title: str
    description: str
    suggestion: Optional[str] = None


class CodeReviewResponse(BaseModel):
    """Structured code review result."""
    summary: str
    findings: List[CodeReviewFinding] = Field(default_factory=list)
    score: Optional[float] = Field(default=None, description="Quality score 0.0 to 10.0")


class CodingQueryRequest(BaseModel):
    """Standalone coding endpoint request."""
    query: str
    project_id: Optional[UUID] = None
    file_ids: Optional[List[UUID]] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    user_id: Optional[UUID] = None


class CodingQueryResponse(BaseModel):
    """Standalone coding endpoint response."""
    answer: str
    language: Optional[str] = None
    files_changed: List[str] = Field(default_factory=list)
    diffs: List[CodeChange] = Field(default_factory=list)
    tests: List[str] = Field(default_factory=list)
    review: Optional[CodeReviewResponse] = None
