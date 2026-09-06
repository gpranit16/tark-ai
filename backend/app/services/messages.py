from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Message, Thread
from app.schemas.message import MessageCreate
from app.services.errors import bad_request, not_found
from app.services.threads import get_thread_or_404


async def get_message_or_404(session: AsyncSession, message_id: UUID) -> Message:
    message = await session.get(Message, message_id)
    if message is None:
        raise not_found("Message not found")
    return message


async def create_message(session: AsyncSession, thread_id: UUID, payload: MessageCreate) -> Message:
    thread = await get_thread_or_404(session, thread_id)

    if payload.parent_message_id is not None:
        parent = await get_message_or_404(session, payload.parent_message_id)
        if parent.thread_id != thread.id:
            raise bad_request("Parent message must belong to the same thread")

    message = Message(thread_id=thread.id, **payload.model_dump())
    thread.updated_at = datetime.now(timezone.utc)
    session.add(message)
    await session.commit()
    await session.refresh(message)
    return message


async def list_messages(
    session: AsyncSession,
    *,
    thread_id: UUID,
    limit: int,
    offset: int,
) -> list[Message]:
    thread = await session.get(Thread, thread_id)
    if thread is None:
        raise not_found("Thread not found")

    stmt = (
        select(Message)
        .where(Message.thread_id == thread_id)
        .order_by(Message.created_at.asc(), Message.id.asc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.scalars(stmt)
    return list(result.all())
