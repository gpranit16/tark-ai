from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Project, Thread, User
from app.schemas.thread import ThreadCreate, ThreadUpdate
from app.services.errors import bad_request, forbidden, not_found

DEV_TEST_USER_ID = UUID("00000000-0000-0000-0000-000000000001")


async def get_user_or_404(session: AsyncSession, user_id: UUID) -> User:
    user = await session.get(User, user_id)
    if user is None:
        if user_id == DEV_TEST_USER_ID:
            user = User(id=DEV_TEST_USER_ID)
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user
        raise not_found("User not found")
    return user


async def get_thread_or_404(session: AsyncSession, thread_id: UUID, user_id: UUID | None = None) -> Thread:
    thread = await session.get(Thread, thread_id)
    if thread is None:
        raise not_found("Thread not found")
    if user_id is not None and thread.user_id != user_id:
        raise forbidden("You do not have access to this thread")
    return thread


async def get_project_or_404(session: AsyncSession, project_id: UUID) -> Project:
    project = await session.get(Project, project_id)
    if project is None:
        raise not_found("Project not found")
    return project


async def create_thread(session: AsyncSession, payload: ThreadCreate) -> Thread:
    await get_user_or_404(session, payload.user_id)

    if payload.project_id is not None:
        project = await get_project_or_404(session, payload.project_id)
        if project.user_id != payload.user_id:
            raise bad_request("Project does not belong to the supplied user")

    thread = Thread(**payload.model_dump())
    session.add(thread)
    await session.commit()
    await session.refresh(thread)
    return thread


async def list_threads(
    session: AsyncSession,
    *,
    user_id: UUID | None = None,
    project_id: UUID | None = None,
    is_archived: bool | None = False,
    limit: int = 50,
    offset: int = 0,
) -> list[Thread]:
    stmt: Select[tuple[Thread]] = (
        select(Thread)
        .order_by(
            Thread.is_pinned.desc(),
            Thread.sort_order.desc(),
            Thread.updated_at.desc(),
            Thread.created_at.desc(),
        )
    )

    if user_id is not None:
        stmt = stmt.where(Thread.user_id == user_id)
    elif project_id is None:
        stmt = stmt.where(Thread.user_id == DEV_TEST_USER_ID)

    if is_archived is not None:
        stmt = stmt.where(Thread.is_archived == is_archived)

    if project_id is not None:
        stmt = stmt.where(Thread.project_id == project_id)

    stmt = stmt.limit(limit).offset(offset)
    result = await session.scalars(stmt)
    return list(result.all())


async def update_thread(
    session: AsyncSession,
    thread_id: UUID,
    payload: ThreadUpdate,
    user_id: UUID | None = None,
) -> Thread:
    thread = await get_thread_or_404(session, thread_id, user_id=user_id)
    updates = payload.model_dump(exclude_unset=True)

    for field, value in updates.items():
        if field == "is_archived":
            if value is True and not thread.is_archived:
                thread.archived_at = datetime.now(timezone.utc)
            elif value is False:
                thread.archived_at = None
        setattr(thread, field, value)

    await session.commit()
    await session.refresh(thread)
    return thread


async def move_thread_order(
    session: AsyncSession,
    thread_id: UUID,
    direction: Literal["up", "down"],
    user_id: UUID | None = None,
) -> Thread:
    target_thread = await get_thread_or_404(session, thread_id, user_id=user_id)

    # Fetch all sibling threads in the same user/project/archived/pinned group
    stmt = (
        select(Thread)
        .where(
            Thread.user_id == target_thread.user_id,
            Thread.is_archived == target_thread.is_archived,
            Thread.is_pinned == target_thread.is_pinned,
        )
        .order_by(
            Thread.sort_order.desc(),
            Thread.updated_at.desc(),
            Thread.created_at.desc(),
        )
    )
    if target_thread.project_id is not None:
        stmt = stmt.where(Thread.project_id == target_thread.project_id)
    else:
        stmt = stmt.where(Thread.project_id.is_(None))

    result = await session.scalars(stmt)
    siblings = list(result.all())

    # Find current index
    idx = -1
    for i, t in enumerate(siblings):
        if t.id == target_thread.id:
            idx = i
            break

    if idx == -1:
        return target_thread

    # Swap positions in list
    if direction == "up" and idx > 0:
        siblings[idx], siblings[idx - 1] = siblings[idx - 1], siblings[idx]
    elif direction == "down" and idx < len(siblings) - 1:
        siblings[idx], siblings[idx + 1] = siblings[idx + 1], siblings[idx]
    else:
        # Cannot move further up/down
        return target_thread

    # Reassign explicit distinct sort_order with generous gaps (highest at top)
    total = len(siblings)
    for i, item in enumerate(siblings):
        item.sort_order = (total - i) * 10

    await session.commit()
    await session.refresh(target_thread)
    return target_thread


async def delete_thread(session: AsyncSession, thread_id: UUID, user_id: UUID | None = None) -> None:
    thread = await get_thread_or_404(session, thread_id, user_id=user_id)
    await session.delete(thread)
    await session.commit()
