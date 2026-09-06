"""Projects REST API endpoints for Phase 11 Workspace Context.

POST   /api/v1/projects                  — Create project
GET    /api/v1/projects                  — List user's projects
GET    /api/v1/projects/{id}             — Get project details & stats
PATCH  /api/v1/projects/{id}             — Update project
POST   /api/v1/projects/{id}/archive     — Archive project
POST   /api/v1/projects/{id}/restore     — Restore archived project
DELETE /api/v1/projects/{id}             — Delete project

Project Files:
GET    /api/v1/projects/{id}/files       — List project files
POST   /api/v1/projects/{id}/files/{file_id}   — Attach file to project
DELETE /api/v1/projects/{id}/files/{file_id}   — Detach file from project

Project Threads:
GET    /api/v1/projects/{id}/threads     — List project conversation threads
POST   /api/v1/projects/{id}/threads/{thread_id} — Move thread into project
DELETE /api/v1/projects/{id}/threads/{thread_id} — Remove thread from project

Project Memory & Research:
GET    /api/v1/projects/{id}/memory      — List project-specific memories
GET    /api/v1/projects/{id}/research    — List project research sessions
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth_deps import get_optional_current_user
from app.db.session import get_db_session
from app.models.conversation import User
from app.schemas.file import FileResponse
from app.schemas.memory import MemoryRead
from app.schemas.project import ProjectCreate, ProjectDetailResponse, ProjectResponse, ProjectUpdate
from app.schemas.thread import ThreadResponse
from app.services import projects as project_service
from app.services.threads import DEV_TEST_USER_ID

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreate,
    current_user: User | None = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ProjectResponse:
    """Create a new project workspace."""
    if current_user:
        payload.user_id = current_user.id
    project = await project_service.create_project(session, payload)
    return ProjectResponse.model_validate(project)


@router.get("", response_model=list[ProjectResponse])
async def list_projects(
    user_id: UUID | None = None,
    include_archived: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User | None = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[ProjectResponse]:
    """List projects belonging to the user."""
    effective_user_id = current_user.id if current_user else (user_id or DEV_TEST_USER_ID)
    projects = await project_service.list_projects(
        session,
        user_id=effective_user_id,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
    )
    result: list[ProjectResponse] = []
    for p in projects:
        counts = await project_service.get_project_counts(session, p.id)
        resp = ProjectResponse.model_validate(p)
        resp.thread_count = counts["thread_count"]
        resp.file_count = counts["file_count"]
        resp.memory_count = counts["memory_count"]
        resp.research_count = counts["research_count"]
        result.append(resp)
    return result


@router.get("/{project_id}", response_model=ProjectDetailResponse)
async def get_project(
    project_id: UUID,
    user_id: UUID | None = None,
    current_user: User | None = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ProjectDetailResponse:
    """Get project details and aggregated stats."""
    effective_user_id = current_user.id if current_user else user_id
    project = await project_service.get_project_or_404(session, project_id, user_id=effective_user_id)
    counts = await project_service.get_project_counts(session, project.id)
    resp = ProjectDetailResponse.model_validate(project)
    resp.thread_count = counts["thread_count"]
    resp.file_count = counts["file_count"]
    resp.memory_count = counts["memory_count"]
    resp.research_count = counts["research_count"]
    return resp


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: UUID,
    payload: ProjectUpdate,
    user_id: UUID | None = None,
    current_user: User | None = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ProjectResponse:
    """Update project name, description, custom instructions, avatar, or metadata."""
    effective_user_id = current_user.id if current_user else user_id
    project = await project_service.update_project(session, project_id, payload, user_id=effective_user_id)
    return ProjectResponse.model_validate(project)


@router.post("/{project_id}/archive", response_model=ProjectResponse)
async def archive_project(
    project_id: UUID,
    user_id: UUID | None = None,
    current_user: User | None = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ProjectResponse:
    """Archive a project."""
    effective_user_id = current_user.id if current_user else user_id
    project = await project_service.archive_project(session, project_id, user_id=effective_user_id)
    return ProjectResponse.model_validate(project)


@router.post("/{project_id}/restore", response_model=ProjectResponse)
async def restore_project(
    project_id: UUID,
    user_id: UUID | None = None,
    current_user: User | None = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ProjectResponse:
    """Restore an archived project."""
    effective_user_id = current_user.id if current_user else user_id
    project = await project_service.restore_project(session, project_id, user_id=effective_user_id)
    return ProjectResponse.model_validate(project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: UUID,
    user_id: UUID | None = None,
    current_user: User | None = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    """Permanently delete a project."""
    effective_user_id = current_user.id if current_user else user_id
    await project_service.delete_project(session, project_id, user_id=effective_user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── Project Files Endpoints ───────────────────────────────────────────────────

@router.get("/{project_id}/files", response_model=list[FileResponse])
async def list_project_files(
    project_id: UUID,
    user_id: UUID | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User | None = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[FileResponse]:
    """List files attached to this project."""
    effective_user_id = current_user.id if current_user else user_id
    files = await project_service.list_project_files(
        session, project_id, user_id=effective_user_id, limit=limit, offset=offset
    )
    return [FileResponse.model_validate(f) for f in files]


@router.post("/{project_id}/files/{file_id}", response_model=FileResponse)
async def attach_file_to_project(
    project_id: UUID,
    file_id: UUID,
    user_id: UUID | None = None,
    current_user: User | None = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> FileResponse:
    """Attach an existing file to this project."""
    effective_user_id = current_user.id if current_user else user_id
    file = await project_service.add_file_to_project(
        session, project_id, file_id, user_id=effective_user_id
    )
    return FileResponse.model_validate(file)


@router.delete("/{project_id}/files/{file_id}", response_model=FileResponse)
async def detach_file_from_project(
    project_id: UUID,
    file_id: UUID,
    user_id: UUID | None = None,
    current_user: User | None = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> FileResponse:
    """Detach a file from this project."""
    effective_user_id = current_user.id if current_user else user_id
    file = await project_service.remove_file_from_project(
        session, project_id, file_id, user_id=effective_user_id
    )
    return FileResponse.model_validate(file)


# ── Project Threads Endpoints ─────────────────────────────────────────────────

@router.get("/{project_id}/threads", response_model=list[ThreadResponse])
async def list_project_threads(
    project_id: UUID,
    user_id: UUID | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User | None = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[ThreadResponse]:
    """List threads belonging to this project."""
    effective_user_id = current_user.id if current_user else user_id
    threads = await project_service.list_project_threads(
        session, project_id, user_id=effective_user_id, limit=limit, offset=offset
    )
    return [ThreadResponse.model_validate(t) for t in threads]


@router.post("/{project_id}/threads/{thread_id}", response_model=ThreadResponse)
async def move_thread_to_project(
    project_id: UUID,
    thread_id: UUID,
    user_id: UUID | None = None,
    current_user: User | None = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ThreadResponse:
    """Move a conversation thread into this project."""
    effective_user_id = current_user.id if current_user else user_id
    thread = await project_service.move_thread_to_project(
        session, project_id, thread_id, user_id=effective_user_id
    )
    return ThreadResponse.model_validate(thread)


@router.delete("/{project_id}/threads/{thread_id}", response_model=ThreadResponse)
async def remove_thread_from_project(
    project_id: UUID,
    thread_id: UUID,
    user_id: UUID | None = None,
    current_user: User | None = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ThreadResponse:
    """Remove a thread from this project."""
    effective_user_id = current_user.id if current_user else user_id
    thread = await project_service.remove_thread_from_project(
        session, project_id, thread_id, user_id=effective_user_id
    )
    return ThreadResponse.model_validate(thread)


# ── Project Memory & Research Endpoints ───────────────────────────────────────

@router.get("/{project_id}/memory", response_model=list[MemoryRead])
async def list_project_memories(
    project_id: UUID,
    user_id: UUID | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User | None = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[MemoryRead]:
    """List memories linked to this project."""
    effective_user_id = current_user.id if current_user else user_id
    memories = await project_service.list_project_memories(
        session, project_id, user_id=effective_user_id, limit=limit, offset=offset
    )
    return [MemoryRead.model_validate(m) for m in memories]


@router.get("/{project_id}/research", response_model=list[dict])
async def list_project_research(
    project_id: UUID,
    user_id: UUID | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User | None = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[dict]:
    """List Deep Research history conducted in this project."""
    effective_user_id = current_user.id if current_user else user_id
    sessions = await project_service.list_project_research(
        session, project_id, user_id=effective_user_id, limit=limit, offset=offset
    )
    return [
        {
            "id": str(s.id),
            "thread_id": str(s.thread_id),
            "project_id": str(s.project_id) if s.project_id else None,
            "query": s.query,
            "status": s.status,
            "task_count": s.task_count,
            "source_count": s.source_count,
            "confidence": s.confidence,
            "duration_ms": s.duration_ms,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in sessions
    ]
