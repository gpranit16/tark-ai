"""
Deep Research API endpoints — Phase 10.

POST /api/v1/research/stream          — Stream research via SSE (standalone endpoint)
POST /api/v1/research/{id}/cancel     — Cancel active research
GET  /api/v1/research/{id}            — Get research session status
GET  /api/v1/research/                — List user's research sessions
"""
from __future__ import annotations

import uuid
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.session import AsyncSessionLocal, get_db_session
from app.models.research import ResearchSession
from app.services.research.manager import ResearchManager, cancel_research

router = APIRouter(prefix="/research", tags=["research"])

DEV_USER_ID = UUID("00000000-0000-0000-0000-000000000001")


class ResearchStreamRequest(BaseModel):
    thread_id: UUID
    query: str = Field(..., min_length=1, max_length=2000)
    user_id: UUID | None = None
    project_id: UUID | None = None
    provider: str | None = None
    model: str | None = None


class ResearchCancelResponse(BaseModel):
    research_id: str
    cancelled: bool
    message: str


@router.post("/stream")
async def stream_research(
    payload: ResearchStreamRequest,
    request: Request,
) -> StreamingResponse:
    """Stream a Deep Research run via Server-Sent Events."""
    manager = ResearchManager()
    user_id = payload.user_id or DEV_USER_ID

    async def event_stream():
        async with AsyncSessionLocal() as stream_session:
            async for event in manager.stream_research(
                session=stream_session,
                thread_id=payload.thread_id,
                user_id=user_id,
                project_id=payload.project_id,
                query=payload.query,
                provider=payload.provider,
                model=payload.model,
                is_disconnected=request.is_disconnected,
            ):
                yield event

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.post("/{research_id}/cancel", response_model=ResearchCancelResponse)
async def cancel_research_session(
    research_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> ResearchCancelResponse:
    """Cancel an active research session."""
    cancelled = cancel_research(research_id)
    return ResearchCancelResponse(
        research_id=research_id,
        cancelled=cancelled,
        message="Research cancelled" if cancelled else "Research not found or already completed",
    )


@router.get("/{research_id}")
async def get_research_session(
    research_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Get status and metadata for a research session."""
    try:
        rs_uuid = UUID(research_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid research_id format")

    rs = await session.get(ResearchSession, rs_uuid)
    if not rs:
        raise HTTPException(status_code=404, detail="Research session not found")

    return {
        "research_id": str(rs.id),
        "thread_id": str(rs.thread_id),
        "user_id": str(rs.user_id),
        "query": rs.query,
        "status": rs.status,
        "task_count": rs.task_count,
        "source_count": rs.source_count,
        "retry_count": rs.retry_count,
        "confidence": rs.confidence,
        "duration_ms": rs.duration_ms,
        "plan": rs.plan,
        "research_metadata": rs.research_metadata,
        "created_at": rs.created_at.isoformat() if rs.created_at else None,
        "updated_at": rs.updated_at.isoformat() if rs.updated_at else None,
    }


@router.get("/")
async def list_research_sessions(
    user_id: UUID | None = None,
    limit: int = 20,
    session: AsyncSession = Depends(get_db_session),
) -> list[dict]:
    """List research sessions for a user."""
    effective_user_id = user_id or DEV_USER_ID
    stmt = (
        select(ResearchSession)
        .where(ResearchSession.user_id == effective_user_id)
        .order_by(ResearchSession.created_at.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    sessions = result.scalars().all()

    return [
        {
            "research_id": str(rs.id),
            "thread_id": str(rs.thread_id),
            "query": rs.query,
            "status": rs.status,
            "confidence": rs.confidence,
            "source_count": rs.source_count,
            "created_at": rs.created_at.isoformat() if rs.created_at else None,
        }
        for rs in sessions
    ]
