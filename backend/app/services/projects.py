"""Project service for Phase 11 Workspace Context."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Message, Project, Thread, User
from app.models.file import File
from app.models.memory import Memory
from app.models.research import ResearchSession
from app.schemas.project import ProjectCreate, ProjectResponse, ProjectUpdate
from app.services.errors import bad_request, forbidden, not_found
from app.services.threads import DEV_TEST_USER_ID, get_user_or_404


async def get_project_or_404(
    session: AsyncSession,
    project_id: UUID,
    user_id: UUID | None = None,
) -> Project:
    """Fetch project by ID, optionally validating user ownership."""
    project = await session.get(Project, project_id)
    if project is None:
        raise not_found("Project not found")
    if user_id is not None and project.user_id != user_id:
        raise forbidden("You do not have access to this project")
    return project


async def create_project(
    session: AsyncSession,
    payload: ProjectCreate,
    user_id: UUID | None = None,
) -> Project:
    """Create a new project workspace for the user."""
    effective_user_id = payload.user_id or user_id or DEV_TEST_USER_ID
    await get_user_or_404(session, effective_user_id)

    data = payload.model_dump(exclude_unset=True)
    data["user_id"] = effective_user_id

    project = Project(**data)
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return project


async def list_projects(
    session: AsyncSession,
    *,
    user_id: UUID,
    include_archived: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> list[Project]:
    """List projects belonging to the user."""
    stmt: Select[tuple[Project]] = select(Project).where(Project.user_id == user_id)
    if not include_archived:
        stmt = stmt.where(Project.is_archived == False)  # noqa: E712
    stmt = stmt.order_by(Project.updated_at.desc(), Project.created_at.desc())
    stmt = stmt.limit(limit).offset(offset)
    result = await session.scalars(stmt)
    return list(result.all())


async def update_project(
    session: AsyncSession,
    project_id: UUID,
    payload: ProjectUpdate,
    user_id: UUID | None = None,
) -> Project:
    """Update project metadata, name, custom instructions, avatar, or archive state."""
    project = await get_project_or_404(session, project_id, user_id=user_id)
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(project, field, value)
    await session.commit()
    await session.refresh(project)
    return project


async def archive_project(
    session: AsyncSession,
    project_id: UUID,
    user_id: UUID | None = None,
) -> Project:
    """Archive a project (soft-archive)."""
    project = await get_project_or_404(session, project_id, user_id=user_id)
    project.is_archived = True
    await session.commit()
    await session.refresh(project)
    return project


async def restore_project(
    session: AsyncSession,
    project_id: UUID,
    user_id: UUID | None = None,
) -> Project:
    """Restore an archived project."""
    project = await get_project_or_404(session, project_id, user_id=user_id)
    project.is_archived = False
    await session.commit()
    await session.refresh(project)
    return project


async def delete_project(
    session: AsyncSession,
    project_id: UUID,
    user_id: UUID | None = None,
) -> None:
    """Permanently delete a project."""
    project = await get_project_or_404(session, project_id, user_id=user_id)
    await session.delete(project)
    await session.commit()


async def get_project_counts(
    session: AsyncSession,
    project_id: UUID,
) -> dict[str, int]:
    """Get count of threads, files, memories, and research sessions in project."""
    threads_count = await session.scalar(
        select(func.count(Thread.id)).where(Thread.project_id == project_id)
    ) or 0
    files_count = await session.scalar(
        select(func.count(File.id)).where(File.project_id == project_id)
    ) or 0
    memories_count = await session.scalar(
        select(func.count(Memory.id)).where(Memory.project_id == project_id, Memory.is_active == True)  # noqa: E712
    ) or 0
    research_count = await session.scalar(
        select(func.count(ResearchSession.id)).where(ResearchSession.project_id == project_id)
    ) or 0

    return {
        "thread_count": threads_count,
        "file_count": files_count,
        "memory_count": memories_count,
        "research_count": research_count,
    }


# ── Project Files ─────────────────────────────────────────────────────────────

async def list_project_files(
    session: AsyncSession,
    project_id: UUID,
    user_id: UUID | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[File]:
    """List all files attached to this project workspace."""
    await get_project_or_404(session, project_id, user_id=user_id)
    stmt = (
        select(File)
        .where(File.project_id == project_id)
        .order_by(File.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.scalars(stmt)
    return list(result.all())


async def add_file_to_project(
    session: AsyncSession,
    project_id: UUID,
    file_id: UUID,
    user_id: UUID | None = None,
) -> File:
    """Link an existing file to this project workspace."""
    project = await get_project_or_404(session, project_id, user_id=user_id)
    file = await session.get(File, file_id)
    if file is None:
        raise not_found("File not found")
    if file.user_id != project.user_id:
        raise forbidden("File belongs to a different user")

    file.project_id = project.id
    await session.commit()
    await session.refresh(file)
    return file


async def remove_file_from_project(
    session: AsyncSession,
    project_id: UUID,
    file_id: UUID,
    user_id: UUID | None = None,
) -> File:
    """Unlink a file from this project (sets project_id to NULL)."""
    await get_project_or_404(session, project_id, user_id=user_id)
    file = await session.get(File, file_id)
    if file is None:
        raise not_found("File not found")
    if file.project_id != project_id:
        raise bad_request("File is not part of this project")

    file.project_id = None
    await session.commit()
    await session.refresh(file)
    return file


# ── Project Threads ───────────────────────────────────────────────────────────

async def list_project_threads(
    session: AsyncSession,
    project_id: UUID,
    user_id: UUID | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Thread]:
    """List all conversation threads within a project."""
    await get_project_or_404(session, project_id, user_id=user_id)
    stmt = (
        select(Thread)
        .where(Thread.project_id == project_id)
        .order_by(Thread.updated_at.desc(), Thread.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.scalars(stmt)
    return list(result.all())


async def move_thread_to_project(
    session: AsyncSession,
    project_id: UUID,
    thread_id: UUID,
    user_id: UUID | None = None,
) -> Thread:
    """Move a conversation thread into a project."""
    project = await get_project_or_404(session, project_id, user_id=user_id)
    thread = await session.get(Thread, thread_id)
    if thread is None:
        raise not_found("Thread not found")
    if thread.user_id != project.user_id:
        raise forbidden("Thread belongs to a different user")

    thread.project_id = project.id
    await session.commit()
    await session.refresh(thread)
    return thread


async def remove_thread_from_project(
    session: AsyncSession,
    project_id: UUID,
    thread_id: UUID,
    user_id: UUID | None = None,
) -> Thread:
    """Remove a conversation thread from a project (makes it standalone)."""
    await get_project_or_404(session, project_id, user_id=user_id)
    thread = await session.get(Thread, thread_id)
    if thread is None:
        raise not_found("Thread not found")
    if thread.project_id != project_id:
        raise bad_request("Thread is not part of this project")

    thread.project_id = None
    await session.commit()
    await session.refresh(thread)
    return thread


# ── Project Memories ──────────────────────────────────────────────────────────

async def list_project_memories(
    session: AsyncSession,
    project_id: UUID,
    user_id: UUID | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Memory]:
    """List long-term memories belonging to this project."""
    await get_project_or_404(session, project_id, user_id=user_id)
    stmt = (
        select(Memory)
        .where(Memory.project_id == project_id, Memory.is_active == True)  # noqa: E712
        .order_by(Memory.updated_at.desc(), Memory.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.scalars(stmt)
    return list(result.all())


# ── Project Research ──────────────────────────────────────────────────────────

async def list_project_research(
    session: AsyncSession,
    project_id: UUID,
    user_id: UUID | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[ResearchSession]:
    """List Deep Research history conducted in this project."""
    await get_project_or_404(session, project_id, user_id=user_id)
    stmt = (
        select(ResearchSession)
        .where(ResearchSession.project_id == project_id)
        .order_by(ResearchSession.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.scalars(stmt)
    return list(result.all())
