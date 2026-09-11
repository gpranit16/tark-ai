from datetime import date, datetime, time
from typing import Any, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.task import ReminderStatus, TaskPriority, TaskStatus


# ---------------------------------------------------------------------------
# Category Schemas
# ---------------------------------------------------------------------------

class TaskCategoryBase(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    color: Optional[str] = Field(default="#D6B56A", max_length=32)
    icon: Optional[str] = Field(default="tag", max_length=32)


class TaskCategoryCreate(TaskCategoryBase):
    pass


class TaskCategoryUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=64)
    color: Optional[str] = Field(default=None, max_length=32)
    icon: Optional[str] = Field(default=None, max_length=32)


class TaskCategoryRead(TaskCategoryBase):
    id: UUID
    user_id: UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Reminder Schemas
# ---------------------------------------------------------------------------

class TaskReminderBase(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    reminder_time: datetime
    delivery_channel: str = Field(default="in_app", max_length=32)


class TaskReminderCreate(TaskReminderBase):
    task_id: Optional[UUID] = None


class TaskReminderUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    reminder_time: Optional[datetime] = None
    status: Optional[ReminderStatus] = None
    delivery_channel: Optional[str] = None


class TaskReminderRead(TaskReminderBase):
    id: UUID
    user_id: UUID
    task_id: Optional[UUID] = None
    status: ReminderStatus
    delivered_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Task Schemas
# ---------------------------------------------------------------------------

class TaskBase(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    due_date: Optional[date] = None
    due_time: Optional[time] = None
    estimated_duration: Optional[int] = Field(default=None, ge=1, le=1440)  # minutes
    priority: TaskPriority = TaskPriority.MEDIUM
    status: TaskStatus = TaskStatus.PENDING
    category_id: Optional[UUID] = None
    tags: Optional[List[str]] = Field(default_factory=list)
    is_recurring: bool = False
    recurrence_rule: Optional[str] = None  # daily, weekly, monthly, weekdays
    calendar_event_id: Optional[str] = None
    synced_to_calendar: bool = False


class TaskCreate(TaskBase):
    reminder_time: Optional[datetime] = None  # Optional inline reminder creation


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None
    due_date: Optional[date] = None
    due_time: Optional[time] = None
    estimated_duration: Optional[int] = Field(default=None, ge=1, le=1440)
    priority: Optional[TaskPriority] = None
    status: Optional[TaskStatus] = None
    category_id: Optional[UUID] = None
    tags: Optional[List[str]] = None
    is_recurring: Optional[bool] = None
    recurrence_rule: Optional[str] = None
    calendar_event_id: Optional[str] = None
    synced_to_calendar: Optional[bool] = None


class TaskRead(TaskBase):
    id: UUID
    user_id: UUID
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    category: Optional[TaskCategoryRead] = None
    reminders: List[TaskReminderRead] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class TaskListFilter(BaseModel):
    status: Optional[TaskStatus] = None
    priority: Optional[TaskPriority] = None
    category_id: Optional[UUID] = None
    time_frame: Optional[str] = None  # today, tomorrow, this_week, upcoming, overdue, completed, all
    search: Optional[str] = None
    sort_by: Optional[str] = "due_time"  # due_time, priority, created_at, title
    order: Optional[str] = "asc"  # asc, desc


# ---------------------------------------------------------------------------
# Daily Plan & Smart Scheduling Schemas
# ---------------------------------------------------------------------------

class PlannedTimeBlock(BaseModel):
    start_time: str  # e.g. "09:00" or "09:00 AM"
    end_time: str    # e.g. "10:00" or "10:00 AM"
    title: str
    type: str  # "calendar_event", "task", "break", "routine", "goal_focus"
    task_id: Optional[str] = None
    calendar_event_id: Optional[str] = None
    priority: Optional[str] = None
    notes: Optional[str] = None


class DailyPlanResponse(BaseModel):
    target_date: str
    timezone: str
    calendar_events_count: int
    tasks_count: int
    overdue_count: int
    time_blocks: List[PlannedTimeBlock]
    summary: str
    top_priorities: List[str] = Field(default_factory=list)


class SyncTaskCalendarRequest(BaseModel):
    start_time: str  # ISO timestamp
    end_time: Optional[str] = None  # ISO timestamp or auto-calculated from duration
    timezone: Optional[str] = "Asia/Kolkata"
