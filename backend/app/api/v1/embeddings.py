from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.schemas.retrieval import IngestionStatusResponse
from app.services.embeddings.ingestion import EmbeddingIngestionService

router = APIRouter(prefix="/embeddings", tags=["embeddings"])
ingestion_service = EmbeddingIngestionService()


@router.post("/ingest/{file_id}", response_model=IngestionStatusResponse)
async def ingest_file(
    file_id: UUID,
    user_id: UUID = Query(...),
    session: AsyncSession = Depends(get_db_session)
) -> IngestionStatusResponse:
    return await ingestion_service.ingest_file(session, file_id, user_id)


@router.get("/status/{file_id}", response_model=IngestionStatusResponse)
async def get_ingestion_status(
    file_id: UUID,
    user_id: UUID = Query(...),
    session: AsyncSession = Depends(get_db_session)
) -> IngestionStatusResponse:
    return await ingestion_service.get_ingestion_status(session, file_id, user_id)


@router.post("/retry/{file_id}", response_model=IngestionStatusResponse)
async def retry_ingestion(
    file_id: UUID,
    user_id: UUID = Query(...),
    session: AsyncSession = Depends(get_db_session)
) -> IngestionStatusResponse:
    return await ingestion_service.retry_ingestion(session, file_id, user_id)
