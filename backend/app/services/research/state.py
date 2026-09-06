"""
LangGraph-compatible ResearchState TypedDict for Phase 10 Deep Research.

All fields must be JSON-serializable.
"""
from __future__ import annotations

from typing import Any, Optional
from typing_extensions import TypedDict, Annotated
import operator


class ResearchState(TypedDict, total=False):
    """Full state schema for the Deep Research LangGraph graph."""

    # ── Input ──────────────────────────────────────────────────────────────
    query: str                            # Original user research query
    user_id: str                          # UUID string
    thread_id: str                        # UUID string
    research_id: str                      # UUID string for this session
    project_id: Optional[str]            # Optional project scope

    # ── Planning ───────────────────────────────────────────────────────────
    plan: Optional[dict]                  # Serialized ResearchPlan
    research_tasks: list[dict]            # List of serialized ResearchTask

    # ── Research Results ───────────────────────────────────────────────────
    # Annotated with operator.add so parallel branches can merge lists
    task_results: Annotated[list[dict], operator.add]   # Completed task results
    evidence: Annotated[list[dict], operator.add]        # Collected Evidence objects
    failed_tasks: Annotated[list[dict], operator.add]    # Failed task records

    # ── Verification ───────────────────────────────────────────────────────
    verified_evidence: list[dict]         # Evidence passing verification
    verification_result: Optional[dict]  # Serialized VerificationResult

    # ── Refinement ─────────────────────────────────────────────────────────
    rewritten_queries: list[str]          # Queries already tried (dedup)
    retry_count: int                      # Current retry iteration

    # ── Synthesis ──────────────────────────────────────────────────────────
    final_answer: Optional[str]          # Markdown final answer
    citations: list[dict]                 # Serialized Citation objects

    # ── Control ────────────────────────────────────────────────────────────
    status: str                           # ResearchStatus value
    errors: list[str]                     # Non-fatal error messages
    cancelled: bool                       # Cancellation flag

    # ── Observability ──────────────────────────────────────────────────────
    metadata: dict                        # Tool calls, durations, agent stats


def create_initial_research_state(
    query: str,
    thread_id: str,
    user_id: str,
    research_id: str | None = None,
    project_id: str | None = None,
    provider: str | None = None,
    model: str | None = None,
) -> ResearchState:
    """Factory function for initializing research state."""
    import uuid
    return ResearchState(
        query=query,
        user_id=str(user_id),
        thread_id=str(thread_id),
        research_id=str(research_id or uuid.uuid4()),
        project_id=str(project_id) if project_id else None,
        plan=None,
        research_tasks=[],
        task_results=[],
        evidence=[],
        failed_tasks=[],
        verified_evidence=[],
        verification_result=None,
        rewritten_queries=[],
        retry_count=0,
        final_answer=None,
        citations=[],
        status="pending",
        errors=[],
        cancelled=False,
        metadata={"provider": provider, "model": model},
    )

