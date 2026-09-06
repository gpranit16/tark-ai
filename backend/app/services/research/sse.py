"""
SSE event helpers for Phase 10 Deep Research.
Reuses the existing sse_event() formatter from app.services.chat.sse.
"""
from __future__ import annotations
from app.services.chat.sse import sse_event


# ── Research lifecycle events ──────────────────────────────────────────────

def research_started(research_id: str, query: str) -> str:
    return sse_event("research_started", {"research_id": research_id, "query": query})


def research_planning(status: str = "Analyzing your research query...") -> str:
    return sse_event("research_planning", {"status": status})


def research_plan_created(tasks: list[dict], task_count: int) -> str:
    return sse_event("research_plan_created", {"tasks": tasks, "task_count": task_count})


def research_task_started(task_id: str, task_query: str, agent_type: str) -> str:
    return sse_event("research_task_started", {
        "task_id": task_id,
        "query": task_query,
        "agent_type": agent_type,
    })


def research_task_progress(task_id: str, sources_found: int, message: str = "") -> str:
    return sse_event("research_task_progress", {
        "task_id": task_id,
        "sources_found": sources_found,
        "message": message,
    })


def research_task_completed(task_id: str, evidence_count: int) -> str:
    return sse_event("research_task_completed", {
        "task_id": task_id,
        "evidence_count": evidence_count,
    })


def research_task_failed(task_id: str, error: str) -> str:
    return sse_event("research_task_failed", {"task_id": task_id, "error": error})


def research_evidence_collected(total_sources: int) -> str:
    return sse_event("research_evidence_collected", {"total_sources": total_sources})


def research_verification_started() -> str:
    return sse_event("research_verification_started", {})


def research_verification_complete(sufficient: bool, confidence: float, conflicts: list[str]) -> str:
    return sse_event("research_verification_complete", {
        "sufficient": sufficient,
        "confidence": confidence,
        "conflict_count": len(conflicts),
    })


def research_retry(retry_count: int, reason: str = "") -> str:
    return sse_event("research_retry", {"retry_count": retry_count, "reason": reason})


def research_synthesis_started() -> str:
    return sse_event("research_synthesis_started", {})


def research_citation(citation: dict) -> str:
    return sse_event("research_citation", citation)


def research_complete(confidence: float, source_count: int, duration_ms: int) -> str:
    return sse_event("research_complete", {
        "confidence": confidence,
        "source_count": source_count,
        "duration_ms": duration_ms,
    })


def research_cancelled(research_id: str) -> str:
    return sse_event("research_cancelled", {"research_id": research_id})


def research_error(error: str, research_id: str = "") -> str:
    return sse_event("research_error", {"error": error, "research_id": research_id})


def message_end(message_id: str = "") -> str:
    return sse_event("message_end", {"message_id": str(message_id)})

