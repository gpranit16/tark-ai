import logging
from typing import Any, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth_deps import get_current_user
from app.db.session import get_db_session
from app.models.conversation import User
from app.models.task import ReminderStatus, TaskPriority, TaskStatus
from app.schemas.task import (
    DailyPlanResponse,
    SyncTaskCalendarRequest,
    TaskCategoryCreate,
    TaskCategoryRead,
    TaskCreate,
    TaskListFilter,
    TaskRead,
    TaskReminderCreate,
    TaskReminderRead,
    TaskUpdate,
)
from app.services.integrations.google_calendar import GoogleCalendarService
from app.services.tasks.planner_service import DailyPlanningService
from app.services.tasks.reminder_service import ReminderService
from app.services.tasks.service import TaskService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tasks", tags=["tasks"])


# ---------------------------------------------------------------------------
# Task Categories
# ---------------------------------------------------------------------------

@router.get("/categories", response_model=List[TaskCategoryRead])
async def list_categories(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """List all categories for current user."""
    service = TaskService()
    return await service.list_categories(user.id, session)


@router.post("/categories", response_model=TaskCategoryRead, status_code=status.HTTP_201_CREATED)
async def create_category(
    payload: TaskCategoryCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Create a new custom category."""
    service = TaskService()
    return await service.create_category(user.id, session, payload)


@router.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    category_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Delete a custom category."""
    service = TaskService()
    deleted = await service.delete_category(user.id, session, category_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Category not found.")


import asyncio
import json
from fastapi.responses import StreamingResponse


# ---------------------------------------------------------------------------
# Reminders
# ---------------------------------------------------------------------------

@router.get("/reminders/stream")
async def stream_reminders(
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    """SSE stream delivering live due reminders to authenticated user."""
    async def event_generator():
        queue = asyncio.Queue()
        ReminderService.register_subscriber(user.id, queue)
        try:
            # Initial connection handshake
            yield f"data: {json.dumps({'event': 'connected', 'user_id': str(user.id)})}\n\n"
            while True:
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=25.0)
                    yield f"data: {json.dumps(payload)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            ReminderService.unregister_subscriber(user.id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/reminders", response_model=List[TaskReminderRead])
async def list_reminders(
    status: Optional[ReminderStatus] = None,
    time_frame: Optional[str] = Query(None, description="today, upcoming, all"),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """List scheduled or past reminders for user."""
    service = ReminderService()
    return await service.list_reminders(user.id, session, status=status, time_frame=time_frame)


@router.post("/reminders", response_model=TaskReminderRead, status_code=status.HTTP_201_CREATED)
async def create_reminder(
    payload: TaskReminderCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Create a new reminder."""
    service = ReminderService()
    try:
        return await service.create_reminder(user.id, session, payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/reminders/{reminder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_reminder(
    reminder_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Cancel a scheduled reminder."""
    service = ReminderService()
    cancelled = await service.cancel_reminder(user.id, session, reminder_id)
    if not cancelled:
        raise HTTPException(status_code=404, detail="Reminder not found.")


# ---------------------------------------------------------------------------
# Smart Daily Plan
# ---------------------------------------------------------------------------

@router.post("/plan-day", response_model=DailyPlanResponse)
async def generate_daily_plan(
    target_date: Optional[str] = Query("today", description="today, tomorrow, or YYYY-MM-DD"),
    timezone: Optional[str] = Query("Asia/Kolkata", description="User timezone"),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Generate a combined smart daily plan combining Calendar + Tasks + Goals."""
    planner = DailyPlanningService()
    return await planner.generate_daily_plan(
        user_id=user.id,
        session=session,
        target_date_raw=target_date,
        timezone_str=timezone or "Asia/Kolkata",
    )


# ---------------------------------------------------------------------------
# Task CRUD & Actions
# ---------------------------------------------------------------------------

@router.get("", response_model=List[TaskRead])
async def list_tasks(
    status: Optional[TaskStatus] = None,
    priority: Optional[TaskPriority] = None,
    category_id: Optional[UUID] = None,
    time_frame: Optional[str] = Query(None, description="today, tomorrow, upcoming, overdue, completed, all"),
    search: Optional[str] = None,
    sort_by: Optional[str] = Query("due_time", description="due_time, priority, created_at, title"),
    order: Optional[str] = Query("asc", description="asc, desc"),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """List tasks with flexible filtering and sorting."""
    service = TaskService()
    filters = TaskListFilter(
        status=status,
        priority=priority,
        category_id=category_id,
        time_frame=time_frame,
        search=search,
        sort_by=sort_by,
        order=order,
    )
    return await service.list_tasks(user.id, session, filters)


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
async def create_task(
    payload: TaskCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Create a new task."""
    service = TaskService()
    return await service.create_task(user.id, session, payload)


@router.get("/{task_id}", response_model=TaskRead)
async def get_task(
    task_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Get a single task by ID."""
    service = TaskService()
    task = await service.get_task(user.id, session, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")
    return task


@router.patch("/{task_id}", response_model=TaskRead)
async def update_task(
    task_id: UUID,
    payload: TaskUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Update an existing task."""
    service = TaskService()
    task = await service.update_task(user.id, session, task_id, payload)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")
    return task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Delete a task and its reminders."""
    service = TaskService()
    deleted = await service.delete_task(user.id, session, task_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Task not found.")


@router.post("/{task_id}/complete", response_model=TaskRead)
async def complete_task(
    task_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Mark a task completed (and spawn next occurrence if recurring)."""
    service = TaskService()
    task = await service.complete_task(user.id, session, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")
    return task


@router.post("/{task_id}/reopen", response_model=TaskRead)
async def reopen_task(
    task_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Reopen a completed or cancelled task."""
    service = TaskService()
    task = await service.reopen_task(user.id, session, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")
    return task


@router.post("/{task_id}/sync-calendar", response_model=TaskRead)
async def sync_task_to_calendar(
    task_id: UUID,
    payload: SyncTaskCalendarRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Schedule a task onto user's Google Calendar upon user confirmation and link event ID."""
    task_service = TaskService()
    cal_service = GoogleCalendarService()

    task = await task_service.get_task(user.id, session, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")

    # Calculate end time if not provided
    end_time_str = payload.end_time
    if not end_time_str:
        from datetime import datetime, timedelta
        try:
            dt_start = datetime.fromisoformat(payload.start_time.replace("Z", "+00:00"))
            dur = task.estimated_duration or 45
            dt_end = dt_start + timedelta(minutes=dur)
            end_time_str = dt_end.isoformat()
        except Exception:
            end_time_str = payload.start_time

    try:
        event = await cal_service.create_event(
            user_id=user.id,
            session=session,
            summary=task.title,
            start_time_str=payload.start_time,
            end_time_str=end_time_str,
            timezone_str=payload.timezone or "Asia/Kolkata",
            description=task.description or f"Scheduled from TARK Task (Priority: {task.priority.value.upper()})",
        )
        task.calendar_event_id = event.get("id")
        task.synced_to_calendar = True
        await session.commit()
        return await task_service.get_task(user.id, session, task_id)
    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=f"Google Calendar not connected: {val_err}")
    except Exception as exc:
        logger.error("Failed to sync task to Google Calendar: %s", exc)
        raise HTTPException(status_code=500, detail=f"Failed to create Google Calendar event: {exc}")
