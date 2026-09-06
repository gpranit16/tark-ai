import json
from collections.abc import AsyncIterator
from dataclasses import asdict, dataclass
from uuid import UUID

from app.core.enums import ConversationMode
from app.providers.base import ProviderError, ProviderName


@dataclass(frozen=True)
class MessageCompletePayload:
    message_id: UUID
    provider: ProviderName
    model: str
    mode: ConversationMode
    finish_reason: str
    fallback_used: bool


def sse_event(event: str, data: dict[str, object] | None = None) -> str:
    if data is None:
        return f"event: {event}\n\n"
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


def _enum_value(value: object) -> object:
    return value.value if hasattr(value, "value") else value


def message_start(provider: ProviderName | str, model: str, mode: ConversationMode | str, fallback_used: bool) -> str:
    return sse_event(
        "message_start",
        {"provider": _enum_value(provider), "model": model, "mode": _enum_value(mode), "fallback_used": fallback_used},
    )


def text_delta(delta: str) -> str:
    return sse_event("text_delta", {"delta": delta})


def message_complete(payload: MessageCompletePayload) -> str:
    data = asdict(payload)
    data["provider"] = _enum_value(payload.provider)
    data["mode"] = _enum_value(payload.mode)
    return sse_event("message_complete", data)


def error_event(error: ProviderError) -> str:
    return sse_event("error", {"code": error.code.value, "message": error.message})


async def collect_sse_events(stream: AsyncIterator[str]) -> list[str]:
    return [event async for event in stream]


# ── Phase 7 RAG-specific SSE events ──────────────────────────────────────────

def rag_retrieval_started(query: str) -> str:
    return sse_event("retrieval_started", {"query": query})


def rag_retrieval_complete(count: int, attempt: int = 1) -> str:
    return sse_event("retrieval_complete", {"count": count, "attempt": attempt})


def rag_reranking_started() -> str:
    return sse_event("reranking_started", {})


def rag_reranking_complete(count: int) -> str:
    return sse_event("reranking_complete", {"count": count})


def rag_grading(confidence: float, relevant: bool, reason: str = "") -> str:
    return sse_event("grading", {"confidence": confidence, "relevant": relevant, "reason": reason})


def rag_query_rewrite(original: str, rewritten: str) -> str:
    return sse_event("query_rewrite", {"original": original, "rewritten": rewritten})


def rag_crag_retry(attempt: int, reason: str = "") -> str:
    return sse_event("crag_retry", {"attempt": attempt, "reason": reason})


def rag_generating() -> str:
    return sse_event("rag_generating", {})


def rag_citation(citation: dict) -> str:
    return sse_event("citation", citation)


def rag_stage_meta(
    stage: str,
    status: str,
    latency_ms: float = 0.0,
    confidence: float | None = None,
    details: dict | None = None,
) -> str:
    payload: dict[str, object] = {
        "stage": stage,
        "status": status,
        "latency_ms": round(latency_ms, 2),
    }
    if confidence is not None:
        payload["confidence"] = round(confidence, 4)
    if details:
        payload.update(details)
    return sse_event("rag_stage", payload)


def rag_message_complete(
    answer: str,
    citations: list[dict],
    retrieved: int,
    reranked: int,
    confidence: float,
    attempts: int,
    rewritten: bool,
    decision: str,
    latency: dict | None = None,
    reranker_used: bool = False,
    scope: str | list[str] | None = None,
    file_count: int | None = None,
) -> str:
    return sse_event(
        "message_complete",
        {
            "answer": answer,
            "citations": citations,
            "retrieval": {
                "retrieved": retrieved,
                "reranked": reranked,
                "confidence": confidence,
                "reranker_used": reranker_used,
                "scope": scope,
                "file_count": file_count,
            },
            "crag": {
                "attempts": attempts,
                "rewritten": rewritten,
                "final_decision": decision,
            },
            "latency": latency or {},
        },
    )


# ── Phase 9 Tool Calling SSE events ──────────────────────────────────────────

def tool_available(tools: list[dict]) -> str:
    """Emit list of available tools configured for this chat request."""
    return sse_event("tool_available", {"tools": tools})


def tool_started(tool_name: str, input_params: dict) -> str:
    """Emit when model decides to invoke a tool and execution begins."""
    return sse_event("tool_started", {"tool": tool_name, "input": input_params})


def tool_result_event(tool_name: str, success: bool, data: object, error: str | None = None, source: str | None = None) -> str:
    """Emit structured tool execution result."""
    return sse_event(
        "tool_result",
        {
            "tool": tool_name,
            "success": success,
            "data": data,
            "error": error,
            "source": source,
        },
    )


def tool_error_event(tool_name: str, error: str) -> str:
    """Emit when tool execution encounters an error."""
    return sse_event("tool_error", {"tool": tool_name, "error": error})


# ── Phase 12 Coding Mode SSE events ──────────────────────────────────────────

def coding_started(query: str, file_count: int = 0, project_name: str | None = None) -> str:
    """Emit when coding mode pipeline begins."""
    return sse_event(
        "coding_started",
        {"query": query, "file_count": file_count, "project_name": project_name},
    )


def coding_file(filename: str, language: str, size_bytes: int = 0) -> str:
    """Emit when a code file is loaded into the coding context."""
    return sse_event(
        "coding_file",
        {"filename": filename, "language": language, "size_bytes": size_bytes},
    )


def coding_context_ready(file_names: list[str], total_files: int, total_chars: int) -> str:
    """Emit when codebase context has been parsed and is ready for the model."""
    return sse_event(
        "coding_context_ready",
        {"file_names": file_names, "total_files": total_files, "total_chars": total_chars},
    )


def coding_generation(provider: str, model: str) -> str:
    """Emit when coding model begins code generation or review."""
    return sse_event(
        "coding_generation",
        {"provider": provider, "model": model},
    )


def coding_complete(files_analyzed: int = 0, changes_count: int = 0, tests_count: int = 0) -> str:
    """Emit when coding response generation completes."""
    return sse_event(
        "coding_complete",
        {
            "files_analyzed": files_analyzed,
            "changes_count": changes_count,
            "tests_count": tests_count,
        },
    )


def coding_error(error: str) -> str:
    """Emit when coding pipeline encounters an error."""
    return sse_event("coding_error", {"error": error})


# ── GPT-Style Memory SSE events ──────────────────────────────────────────────

def memory_saved(key: str, value: str, category: str = "preference", explicit: bool = False) -> str:
    """Emit when a durable memory is saved or updated."""
    return sse_event(
        "memory_saved",
        {
            "key": key,
            "value": value,
            "category": category,
            "explicit": explicit,
        },
    )


def memory_forgotten(key: str, value: str) -> str:
    """Emit when a memory is removed or deactivated."""
    return sse_event(
        "memory_forgotten",
        {
            "key": key,
            "value": value,
        },
    )




