from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth_deps import get_optional_current_user
from app.db.session import get_db_session
from app.models.conversation import User
from app.schemas.document import (
    DocumentMetadataResponse,
    DocumentStatusResponse,
    ParsedDocumentResponse,
)
from app.services import document_processing

DEFAULT_DEV_USER_ID = UUID("00000000-0000-0000-0000-000000000001")

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("/{file_id}/status", response_model=DocumentStatusResponse)
async def get_document_status(
    file_id: UUID,
    user_id: UUID = Query(default=DEFAULT_DEV_USER_ID),
    current_user: User | None = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_db_session)
) -> DocumentStatusResponse:
    effective_user_id = current_user.id if current_user else user_id
    return await document_processing.get_document_status(session, file_id, effective_user_id)


@router.get("/{file_id}", response_model=ParsedDocumentResponse)
async def get_parsed_document(
    file_id: UUID,
    user_id: UUID = Query(default=DEFAULT_DEV_USER_ID),
    current_user: User | None = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_db_session)
) -> ParsedDocumentResponse:
    effective_user_id = current_user.id if current_user else user_id
    return await document_processing.get_parsed_document(session, file_id, effective_user_id)


@router.get("/{file_id}/metadata", response_model=DocumentMetadataResponse)
async def get_document_metadata(
    file_id: UUID,
    user_id: UUID = Query(default=DEFAULT_DEV_USER_ID),
    current_user: User | None = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_db_session)
) -> DocumentMetadataResponse:
    effective_user_id = current_user.id if current_user else user_id
    return await document_processing.get_document_metadata(session, file_id, effective_user_id)


@router.post("/{file_id}/retry", response_model=ParsedDocumentResponse)
async def retry_document_processing(
    file_id: UUID,
    user_id: UUID = Query(default=DEFAULT_DEV_USER_ID),
    current_user: User | None = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_db_session)
) -> ParsedDocumentResponse:
    effective_user_id = current_user.id if current_user else user_id
    return await document_processing.retry_document_processing(session, file_id, effective_user_id)

