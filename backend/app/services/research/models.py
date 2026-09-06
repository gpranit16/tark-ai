"""
Pydantic models for Deep Research — Phase 10.

These models define the structured data flowing through the LangGraph graph.
All models are JSON-serializable (no SQLAlchemy objects).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Optional

from pydantic import BaseModel, Field


class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    SKIPPED = "skipped"


class AgentType(StrEnum):
    WEB = "web"
    DOCUMENT = "document"
    FINANCE = "finance"


class ResearchTask(BaseModel):
    """A single independent research sub-task."""
    task_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    query: str
    agent_type: AgentType = AgentType.WEB
    priority: int = Field(default=1, ge=1, le=10)  # 1=lowest, 10=highest
    depends_on: list[str] = Field(default_factory=list)  # task_ids this depends on
    status: TaskStatus = TaskStatus.PENDING
    error: Optional[str] = None
    duration_ms: int = 0


class EvidenceSource(StrEnum):
    WEB = "web"
    PDF = "pdf"
    FINANCE = "finance"
    NEWS = "news"


class Evidence(BaseModel):
    """Normalized evidence unit from any research agent."""
    source_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    task_id: str = ""
    source_type: EvidenceSource = EvidenceSource.WEB
    title: str = ""
    url: Optional[str] = None
    domain: Optional[str] = None
    file_id: Optional[str] = None
    page_number: Optional[int] = None
    snippet: str = ""          # short excerpt for context
    content: str = ""          # full extracted content
    published_at: Optional[str] = None
    relevance: float = 0.5     # 0.0–1.0
    reliability: float = 0.7   # 0.0–1.0
    credibility_score: float = 0.7  # 0.0–1.0, scored by source authority
    is_official: bool = False  # True for primary/official vendor domains or docs


class VerificationResult(BaseModel):
    """Output of the VerifierAgent."""
    sufficient: bool = False
    confidence: float = 0.0
    supported_claims: list[str] = Field(default_factory=list)
    unsupported_claims: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    reasoning: str = ""


class Citation(BaseModel):
    """Structured citation for the final answer."""
    citation_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    source_type: EvidenceSource = EvidenceSource.WEB
    title: str = ""
    url: Optional[str] = None
    domain: Optional[str] = None
    file_id: Optional[str] = None
    page_number: Optional[int] = None
    published_at: Optional[str] = None
    claim_ids: list[str] = Field(default_factory=list)


class ResearchPlan(BaseModel):
    """Output of the ResearchPlanner."""
    original_query: str
    research_intent: str = ""
    tasks: list[ResearchTask] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ResearchStatus(StrEnum):
    PENDING = "pending"
    PLANNING = "planning"
    RESEARCHING = "researching"
    VERIFYING = "verifying"
    REFINING = "refining"
    SYNTHESIZING = "synthesizing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PARTIAL = "partial"
