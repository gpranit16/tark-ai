from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth_deps import get_optional_current_user
from app.db.session import get_db_session
from app.models.conversation import User
from app.schemas.chat import ChatRequest
from app.schemas.message import MessageCreate, MessageResponse
from app.schemas.thread import ThreadCreate, ThreadMoveRequest, ThreadResponse, ThreadUpdate
from app.services import messages as message_service
from app.services import threads as thread_service
from app.services.chat.service import ChatService
from app.services.threads import DEV_TEST_USER_ID

router = APIRouter(prefix="/threads", tags=["threads"])


@router.post("", response_model=ThreadResponse, status_code=status.HTTP_201_CREATED)
async def create_thread(
    payload: ThreadCreate,
    current_user: User | None = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ThreadResponse:
    if current_user:
        payload.user_id = current_user.id
    return await thread_service.create_thread(session, payload)


@router.get("", response_model=list[ThreadResponse])
async def list_threads(
    user_id: UUID | None = None,
    project_id: UUID | None = None,
    is_archived: bool | None = Query(default=False),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User | None = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[ThreadResponse]:
    effective_user_id = current_user.id if current_user else user_id
    return await thread_service.list_threads(
        session,
        user_id=effective_user_id,
        project_id=project_id,
        is_archived=is_archived,
        limit=limit,
        offset=offset,
    )


@router.get("/{thread_id}", response_model=ThreadResponse)
async def get_thread(
    thread_id: UUID,
    user_id: UUID | None = None,
    current_user: User | None = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ThreadResponse:
    effective_user_id = current_user.id if current_user else user_id
    return await thread_service.get_thread_or_404(session, thread_id, user_id=effective_user_id)


@router.patch("/{thread_id}", response_model=ThreadResponse)
async def update_thread(
    thread_id: UUID,
    payload: ThreadUpdate,
    user_id: UUID | None = None,
    current_user: User | None = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ThreadResponse:
    effective_user_id = current_user.id if current_user else user_id
    return await thread_service.update_thread(session, thread_id, payload, user_id=effective_user_id)


@router.post("/{thread_id}/move", response_model=ThreadResponse)
async def move_thread(
    thread_id: UUID,
    payload: ThreadMoveRequest,
    user_id: UUID | None = None,
    current_user: User | None = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ThreadResponse:
    effective_user_id = current_user.id if current_user else user_id
    return await thread_service.move_thread_order(session, thread_id, direction=payload.direction, user_id=effective_user_id)


@router.delete("/{thread_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_thread(
    thread_id: UUID,
    user_id: UUID | None = None,
    current_user: User | None = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    effective_user_id = current_user.id if current_user else user_id
    await thread_service.delete_thread(session, thread_id, user_id=effective_user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{thread_id}/messages", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def create_message(
    thread_id: UUID,
    payload: MessageCreate,
    session: AsyncSession = Depends(get_db_session),
) -> MessageResponse:
    return await message_service.create_message(session, thread_id, payload)


@router.get("/{thread_id}/messages", response_model=list[MessageResponse])
async def list_messages(
    thread_id: UUID,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db_session),
) -> list[MessageResponse]:
    return await message_service.list_messages(session, thread_id=thread_id, limit=limit, offset=offset)


@router.post("/{thread_id}/chat")
async def chat(
    thread_id: UUID,
    payload: ChatRequest,
    request: Request,
    current_user: User | None = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> StreamingResponse:
    from app.services.rag.router import RAGRouter
    from app.services.chat.service import get_thread_or_404

    service = ChatService()
    rag_router = RAGRouter()

    thread = await get_thread_or_404(session, thread_id)
    user_id = current_user.id if current_user else (payload.user_id or thread.user_id)

    from app.db.session import AsyncSessionLocal

    # ── Phase 10: Deep Research mode dispatch ─────────────────────────────
    mode_value = payload.mode.value if hasattr(payload.mode, "value") else str(payload.mode)
    if mode_value == "deep_research":
        from app.services.research.manager import ResearchManager

        # Persist user message first
        from app.core.enums import GenerationStatus, MessageRole
        from app.models.conversation import Message
        from app.models.file import File
        from sqlalchemy import select

        attachments_data = []
        if payload.file_ids:
            records = (await session.execute(
                select(File).where(File.id.in_(payload.file_ids))
            )).scalars().all()
            attachments_data = [
                {
                    "file_id": str(f.id),
                    "filename": f.original_filename,
                    "mime_type": f.mime_type,
                    "size_bytes": f.size_bytes,
                    "storage_key": f.storage_key,
                }
                for f in records
            ]

        user_msg = Message(
            thread_id=thread.id,
            role=MessageRole.USER,
            content=payload.content,
            mode=payload.mode,
            attachments=attachments_data,
            generation_status=GenerationStatus.COMPLETED,
        )
        session.add(user_msg)
        await session.commit()

        research_manager = ResearchManager()

        async def research_stream():
            async with AsyncSessionLocal() as stream_session:
                async for event in research_manager.stream_research(
                    session=stream_session,
                    thread_id=thread_id,
                    user_id=user_id,
                    project_id=thread.project_id,
                    query=payload.content,
                    provider=payload.provider,
                    model=payload.model,
                    is_disconnected=request.is_disconnected,
                ):
                    yield event

        return StreamingResponse(
            research_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )

    # ── Phase 12: Coding Mode dispatch ────────────────────────────────────
    if mode_value == "coding":
        from app.services.coding.service import CodingService

        coding_service = CodingService()

        async def coding_event_stream():
            async with AsyncSessionLocal() as stream_session:
                async for event in coding_service.stream_coding_chat(
                    session=stream_session,
                    thread_id=thread_id,
                    payload=payload,
                    is_disconnected=request.is_disconnected,
                    user_id=user_id or DEV_TEST_USER_ID,
                ):
                    yield event

        return StreamingResponse(
            coding_event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )

    # Determine if this request should use the RAG pipeline
    use_rag = rag_router.should_use_rag(
        content=payload.content,
        file_ids=payload.file_ids,
        mode=payload.mode.value if hasattr(payload.mode, "value") else str(payload.mode),
    )

    # RAG mode requires user_id for ownership scoping
    if use_rag and user_id is not None:
        async def rag_event_stream():
            async with AsyncSessionLocal() as stream_session:
                async for event in service.stream_rag_chat(
                    session=stream_session,
                    thread_id=thread_id,
                    payload=payload,
                    is_disconnected=request.is_disconnected,
                    user_id=user_id,
                ):
                    yield event

        return StreamingResponse(
            rag_event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )

    # Normal (non-RAG) chat path
    async def event_stream():
        async with AsyncSessionLocal() as stream_session:
            async for event in service.stream_chat(
                session=stream_session,
                thread_id=thread_id,
                payload=payload,
                is_disconnected=request.is_disconnected,
            ):
                yield event

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


