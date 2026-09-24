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
    query: str = ""            # Query that found this evidence
    published_at: Optional[str] = None
    relevance: float = 0.5     # 0.0–1.0
    recency: float = 0.5       # 0.0–1.0, recency score based on query freshness needs
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


class ResearchRouterResult(BaseModel):
    """Output of the ResearchRouter."""
    mode: str = "open_book"  # closed_book, hybrid, open_book
    requires_research: bool = True
    reason: str = ""
    recency_days: int = 30
    queries_needed: int = 5


class ResearchQuery(BaseModel):
    """A targeted search query generated during Query Planning."""
    query: str
    purpose: str = ""
    recency_days: int = 30


class SectionTask(BaseModel):
    """A research section task for LangGraph fanout."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    title: str
    goal: str
    key_questions: list[str] = Field(default_factory=list)
    target_words: int = 300
    required_citations: bool = True
    evidence_tags: list[str] = Field(default_factory=list)
    needs_code: bool = False


class SectionResult(BaseModel):
    """Output of an individual section worker."""
    section_title: str
    content: str
    citations: list[dict] = Field(default_factory=list)
    unsupported_claims: list[str] = Field(default_factory=list)


class ImageItem(BaseModel):
    """An image candidate proposed by the Image Planner."""
    purpose: str
    placement: str
    prompt: str
    image_url: Optional[str] = None
    caption: Optional[str] = None


class ImagePlan(BaseModel):
    """Output of the Image Planner."""
    should_generate: bool = False
    images: list[ImageItem] = Field(default_factory=list)


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
