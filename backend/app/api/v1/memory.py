from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth_deps import get_optional_current_user
from app.core.enums import MemoryCategory
from app.db.session import get_db_session
from app.models.conversation import User
from app.schemas.memory import (
    MemoryCreate,
    MemoryExtractionResult,
    MemoryListResponse,
    MemoryRead,
    MemorySearchRequest,
    MemoryUpdate,
)
from app.services.memory.extractor import MemoryExtractor
from app.services.memory.service import MemoryService

DEFAULT_DEV_USER_ID = UUID("00000000-0000-0000-0000-000000000001")

router = APIRouter(prefix="/memory", tags=["memory"])


class ExtractRequest(BaseModel):
    text: str
    is_rag_query: bool = False


@router.get("", response_model=MemoryListResponse)
async def list_memories(
    user_id: UUID = Query(default=DEFAULT_DEV_USER_ID),
    project_id: UUID | None = Query(default=None),
    include_global: bool = Query(default=True),
    category: MemoryCategory | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User | None = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> MemoryListResponse:
    effective_user_id = current_user.id if current_user else user_id
    service = MemoryService(session)
    return await service.list_memories(
        user_id=effective_user_id,
        project_id=project_id,
        include_global=include_global,
        category=category,
        is_active=is_active,
        search_query=search,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=MemoryRead, status_code=status.HTTP_201_CREATED)
async def create_memory(
    payload: MemoryCreate,
    user_id: UUID = Query(default=DEFAULT_DEV_USER_ID),
    current_user: User | None = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> MemoryRead:
    effective_user_id = current_user.id if current_user else user_id
    service = MemoryService(session)
    return await service.create_memory(user_id=effective_user_id, payload=payload)


@router.get("/{memory_id}", response_model=MemoryRead)
async def get_memory(
    memory_id: UUID,
    user_id: UUID = Query(default=DEFAULT_DEV_USER_ID),
    current_user: User | None = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> MemoryRead:
    effective_user_id = current_user.id if current_user else user_id
    service = MemoryService(session)
    return await service.get_memory(memory_id=memory_id, user_id=effective_user_id)


@router.patch("/{memory_id}", response_model=MemoryRead)
async def update_memory(
    memory_id: UUID,
    payload: MemoryUpdate,
    user_id: UUID = Query(default=DEFAULT_DEV_USER_ID),
    current_user: User | None = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> MemoryRead:
    effective_user_id = current_user.id if current_user else user_id
    service = MemoryService(session)
    return await service.update_memory(memory_id=memory_id, user_id=effective_user_id, payload=payload)


@router.delete("/clear/all", status_code=status.HTTP_200_OK)
async def clear_all_memories(
    user_id: UUID = Query(default=DEFAULT_DEV_USER_ID),
    project_id: UUID | None = Query(default=None),
    current_user: User | None = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, int]:
    effective_user_id = current_user.id if current_user else user_id
    service = MemoryService(session)
    count = await service.delete_all_memories(user_id=effective_user_id, project_id=project_id)
    return {"deleted_count": count}


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory(
    memory_id: UUID,
    user_id: UUID = Query(default=DEFAULT_DEV_USER_ID),
    current_user: User | None = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    effective_user_id = current_user.id if current_user else user_id
    service = MemoryService(session)
    await service.delete_memory(memory_id=memory_id, user_id=effective_user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)



@router.post("/search", response_model=list[MemoryRead])
async def search_memories(
    payload: MemorySearchRequest,
    user_id: UUID = Query(default=DEFAULT_DEV_USER_ID),
    current_user: User | None = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[MemoryRead]:
    effective_user_id = current_user.id if current_user else user_id
    service = MemoryService(session)
    return await service.search_memories(user_id=effective_user_id, payload=payload)


@router.post("/extract", response_model=MemoryExtractionResult)
async def extract_memories(
    payload: ExtractRequest,
) -> MemoryExtractionResult:
    extractor = MemoryExtractor()
    return extractor.extract(text=payload.text, is_rag_query=payload.is_rag_query)
