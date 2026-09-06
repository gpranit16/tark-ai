from uuid import UUID

from fastapi import APIRouter, Depends, Query, UploadFile, File as FastAPIFile, Form, status, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth_deps import get_optional_current_user
from app.db.session import get_db_session
from app.models.conversation import User
from app.schemas.file import FileResponse, StorageStatsResponse
from app.services import files as file_service
from app.storage.factory import get_storage_provider


DEFAULT_DEV_USER_ID = UUID("00000000-0000-0000-0000-000000000001")

router = APIRouter(prefix="/files", tags=["files"])


@router.post("/upload", response_model=FileResponse, status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: UploadFile = FastAPIFile(...),
    user_id: UUID = Form(default=DEFAULT_DEV_USER_ID),
    project_id: UUID | None = Form(None),
    storage_provider: str | None = Form(None),
    current_user: User | None = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_db_session)
) -> FileResponse:
    size_bytes = file.size or 0
    effective_user_id = current_user.id if current_user else user_id

    return await file_service.process_and_upload_file(
        session=session,
        file_stream=file.file,
        filename=file.filename or "unknown",
        mime_type=file.content_type or "application/octet-stream",
        size_bytes=size_bytes,
        user_id=effective_user_id,
        project_id=project_id,
        storage_provider=storage_provider,
    )


@router.get("", response_model=list[FileResponse])
async def list_files(
    user_id: UUID = Query(default=DEFAULT_DEV_USER_ID),
    project_id: UUID | None = None,
    storage_provider: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User | None = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_db_session)
) -> list[FileResponse]:
    effective_user_id = current_user.id if current_user else user_id
    return await file_service.list_files(
        session,
        user_id=effective_user_id,
        project_id=project_id,
        storage_provider=storage_provider,
        limit=limit,
        offset=offset,
    )


@router.get("/stats", response_model=StorageStatsResponse)
async def get_storage_stats(
    user_id: UUID = Query(default=DEFAULT_DEV_USER_ID),
    project_id: UUID | None = None,
    current_user: User | None = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_db_session)
) -> StorageStatsResponse:
    effective_user_id = current_user.id if current_user else user_id
    stats = await file_service.get_storage_stats(session, user_id=effective_user_id, project_id=project_id)
    return StorageStatsResponse(**stats)


@router.get("/{file_id}", response_model=FileResponse)
async def get_file(
    file_id: UUID, 
    user_id: UUID = Query(default=DEFAULT_DEV_USER_ID),
    current_user: User | None = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_db_session)
) -> FileResponse:
    effective_user_id = current_user.id if current_user else user_id
    return await file_service.get_file(session, file_id, effective_user_id)


@router.get("/{file_id}/content")
async def get_file_content(
    file_id: UUID,
    user_id: UUID = Query(default=DEFAULT_DEV_USER_ID),
    current_user: User | None = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    """Stream raw file content for browser preview / download."""
    effective_user_id = current_user.id if current_user else user_id
    db_file = await file_service.get_file(session, file_id, effective_user_id)
    provider = get_storage_provider(db_file.storage_provider)
    content_bytes = await provider.download(db_file.storage_key)
    return Response(
        content=content_bytes,
        media_type=db_file.mime_type,
        headers={"Content-Disposition": f'inline; filename="{db_file.original_filename}"'},
    )


@router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_file(
    file_id: UUID, 
    user_id: UUID = Query(default=DEFAULT_DEV_USER_ID),
    current_user: User | None = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_db_session)
) -> Response:
    effective_user_id = current_user.id if current_user else user_id
    await file_service.delete_file(session, file_id, effective_user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

