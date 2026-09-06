"""Coding REST API endpoints for Phase 12 Coding Mode."""
from __future__ import annotations

from uuid import UUID
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.services.coding.models import CodingQueryRequest, CodingQueryResponse
from app.services.coding.service import CodingService
from app.services.threads import DEV_TEST_USER_ID

router = APIRouter(prefix="/coding", tags=["coding"])


@router.post("/query", response_model=CodingQueryResponse, status_code=status.HTTP_200_OK)
async def query_coding(
    payload: CodingQueryRequest,
    session: AsyncSession = Depends(get_db_session),
) -> CodingQueryResponse:
    """Execute a coding query with code context, structured changes, and diffs."""
    user_id = payload.user_id or DEV_TEST_USER_ID
    service = CodingService()
    return await service.query_coding(session=session, req=payload, user_id=user_id)
