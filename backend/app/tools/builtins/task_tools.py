import logging
import re
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.task import ReminderStatus, TaskPriority, TaskStatus
from app.schemas.task import TaskCategoryCreate, TaskCreate, TaskListFilter, TaskReminderCreate, TaskUpdate
from app.services.tasks.planner_service import DailyPlanningService
from app.services.tasks.reminder_service import ReminderService
from app.services.tasks.service import TaskService
from app.tools.base import BaseTool, ToolExecutionContext, ToolPermission, ToolResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tool Input Schemas
# ---------------------------------------------------------------------------

class CreateTaskInput(BaseModel):
    title: str = Field(description="Title of the task (e.g. 'Finish TARK project', 'Pay electricity bill').")
    description: Optional[str] = Field(default=None, description="Optional detailed notes for the task.")
    due_date: Optional[str] = Field(default=None, description="Due date ('today', 'tomorrow', or 'YYYY-MM-DD').")
    due_time: Optional[str] = Field(default=None, description="Due time (e.g. '18:00', '6:00 PM', '19:30').")
    priority: Optional[str] = Field(default="medium", description="Priority level: 'low', 'medium', 'high', or 'urgent'.")
    estimated_duration: Optional[int] = Field(default=None, description="Estimated duration in minutes (e.g. 15, 30, 45, 60, 90).")
    category: Optional[str] = Field(default=None, description="Category name (e.g. 'Work', 'Study', 'Personal', 'Health', 'Finance', 'Projects').")
    reminder_time: Optional[str] = Field(default=None, description="Optional reminder time ('tomorrow at 8 PM', 'today at 6 PM', or ISO timestamp).")
    is_recurring: Optional[bool] = Field(default=False, description="Whether this task repeats periodically.")
    recurrence_rule: Optional[str] = Field(default=None, description="Recurrence rule: 'daily', 'weekly', 'monthly', or 'weekdays'.")


class ListTasksInput(BaseModel):
    time_frame: Optional[str] = Field(default="all", description="Filter time frame: 'today', 'tomorrow', 'upcoming', 'overdue', 'completed', or 'all'.")
    status: Optional[str] = Field(default=None, description="Filter by status: 'pending', 'in_progress', 'completed', or 'cancelled'.")
    priority: Optional[str] = Field(default=None, description="Filter by priority: 'low', 'medium', 'high', or 'urgent'.")
    category: Optional[str] = Field(default=None, description="Filter by category name.")
    search: Optional[str] = Field(default=None, description="Keyword search in task title/description.")


class UpdateTaskInput(BaseModel):
    task_id: Optional[str] = Field(default=None, description="UUID of the task if known.")
    title_query: Optional[str] = Field(default=None, description="Title or keyword of the task to find and update.")
    title: Optional[str] = Field(default=None, description="New title for the task.")
    description: Optional[str] = Field(default=None, description="New description.")
    due_date: Optional[str] = Field(default=None, description="New due date ('today', 'tomorrow', 'Saturday', or 'YYYY-MM-DD').")
    due_time: Optional[str] = Field(default=None, description="New due time (e.g. '5:00 PM', '17:00').")
    priority: Optional[str] = Field(default=None, description="New priority ('low', 'medium', 'high', 'urgent').")
    status: Optional[str] = Field(default=None, description="New status ('pending', 'in_progress', 'completed', 'cancelled').")
    estimated_duration: Optional[int] = Field(default=None, description="Estimated duration in minutes.")


class CompleteTaskInput(BaseModel):
    task_id: Optional[str] = Field(default=None, description="UUID of the task if known.")
    title: Optional[str] = Field(default=None, description="Title or keyword of the task to complete (e.g. 'grocery', 'TARK project').")


class DeleteTaskInput(BaseModel):
    task_id: Optional[str] = Field(default=None, description="UUID of the task if known.")
    title: Optional[str] = Field(default=None, description="Title or keyword of the task to delete.")


class CreateReminderInput(BaseModel):
    title: str = Field(description="Reminder message / topic (e.g. 'Pay the electricity bill', 'Test TARK reminder').")
    reminder_time: str = Field(description="When to remind. For relative durations, pass 'in 2 minutes', 'in 30 mins', 'in 1 hour', 'in 2 hours'. For specific times, pass 'tomorrow at 8 PM', 'today at 6 PM', or ISO timestamp.")
    task_id: Optional[str] = Field(default=None, description="Optional UUID of the task to attach this reminder to.")


class ListRemindersInput(BaseModel):
    time_frame: Optional[str] = Field(default="upcoming", description="Time frame: 'today', 'upcoming', or 'all'.")
    status: Optional[str] = Field(default="scheduled", description="Status: 'scheduled', 'sent', or 'all'.")


class PlanDayInput(BaseModel):
    target_date: Optional[str] = Field(default="today", description="Date to plan: 'today', 'tomorrow', or 'YYYY-MM-DD'.")
    timezone: Optional[str] = Field(default="Asia/Kolkata", description="User timezone (e.g. 'Asia/Kolkata').")


# ---------------------------------------------------------------------------
# Helper Parsers
# ---------------------------------------------------------------------------

def _parse_natural_date(date_str: Optional[str], tz_offset_hours: float = 5.5) -> Optional[date]:
    """Parse 'today', 'tomorrow', weekday name, or 'YYYY-MM-DD' into a date object relative to local user timezone."""
    if not date_str:
        return None
    clean = str(date_str).strip().lower()
    local_tz = timezone(timedelta(hours=tz_offset_hours))
    now_local = datetime.now(local_tz)
    
    if "tomorrow" in clean:
        return (now_local + timedelta(days=1)).date()
    elif "today" in clean or "tonight" in clean:
        return now_local.date()
    
    # Check weekday names (e.g. 'monday', 'friday', 'saturday')
    weekdays = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    for idx, wd in enumerate(weekdays):
        if wd in clean:
            today_weekday = now_local.weekday()
            days_ahead = (idx - today_weekday) % 7
            if days_ahead == 0:
                days_ahead = 7
            return (now_local + timedelta(days=days_ahead)).date()

    match = re.search(r"\d{4}-\d{2}-\d{2}", clean)
    if match:
        try:
            return datetime.strptime(match.group(0), "%Y-%m-%d").date()
        except Exception:
            return None
    return None


def _parse_time_str(time_str: Optional[str]) -> Optional[time]:
    """Parse '18:00', '6 PM', '6:30 pm' into time object."""
    if not time_str:
        return None
    clean = str(time_str).strip().lower()
    ampm = re.match(r"^(\d{1,2})(?::(\d{2}))?\s*(am|pm)$", clean)
    if ampm:
        h = int(ampm.group(1))
        m = int(ampm.group(2) or 0)
        is_pm = ampm.group(3) == "pm"
        if is_pm and h < 12:
            h += 12
        elif not is_pm and h == 12:
            h = 0
        return time(h, m)

    hhmm = re.match(r"^(\d{1,2}):(\d{2})$", clean)
    if hhmm:
        return time(int(hhmm.group(1)), int(hhmm.group(2)))
    return None


def _parse_reminder_timestamp(time_str: str, tz_offset_hours: float = 5.5) -> datetime:
    """
    Parse natural reminder phrases or relative durations into timezone-aware UTC datetime.
    Resolves relative time ('in 2 minutes', 'in 1 hour') from the fresh real-time clock at execution.
    Rejects times that resolve to the past.
    """
    clean = time_str.strip().lower()
    now_utc = datetime.now(timezone.utc)
    local_tz = timezone(timedelta(hours=tz_offset_hours))
    now_local = datetime.now(local_tz)

    # 1. Check relative seconds (e.g. "in 30 seconds", "in 30s", "after 45 seconds")
    secs_match = re.search(r"(?:in|after)\s+(\d+)\s*(?:sec|second|secs|seconds|s)\b", clean)
    if secs_match:
        return now_utc + timedelta(seconds=int(secs_match.group(1)))

    # 2. Check relative minutes (e.g. "in 2 minutes", "in 2 mins", "in 2 min", "in 2m", "after 5 mins", "in 2-minutes")
    mins_match = re.search(r"(?:in|after)\s+(\d+)\s*(?:min|minute|mins|minutes|m)\b", clean)
    if mins_match:
        return now_utc + timedelta(minutes=int(mins_match.group(1)))

    # 3. Check relative hours (e.g. "in 2 hours", "in 1 hr", "in 1.5 hours", "in 2h", "after 3 hours")
    hours_match = re.search(r"(?:in|after)\s+(\d+(?:\.\d+)?)\s*(?:hr|hour|hrs|hours|h)\b", clean)
    if hours_match:
        return now_utc + timedelta(hours=float(hours_match.group(1)))

    # 4. Check relative days (e.g. "in 2 days", "after 1 day")
    days_match = re.search(r"(?:in|after)\s+(\d+)\s*(?:day|days|d)\b", clean)
    if days_match:
        return now_utc + timedelta(days=int(days_match.group(1)))

    # 5. Check ISO timestamp format (e.g. "2026-09-12T19:00:00+05:30", "2026-09-12 19:00:00", "2026-09-12")
    if re.match(r"^\d{4}-\d{2}-\d{2}", clean):
        try:
            clean_iso = clean.replace("z", "+00:00")
            dt = datetime.fromisoformat(clean_iso)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=local_tz)
            dt_utc = dt.astimezone(timezone.utc)
            if dt_utc < (now_utc - timedelta(seconds=10)):
                raise ValueError(f"Reminder time '{time_str}' resolves to the past ({dt_utc.strftime('%Y-%m-%d %H:%M:%S UTC')}). Reminders must be scheduled for a future time.")
            return dt_utc
        except ValueError:
            raise
        except Exception:
            pass

    # 6. Natural local date + time (e.g. "tomorrow at 8 PM", "today at 6 PM", "tonight at 9:30 PM", "Saturday 5 PM", "at 8 PM")
    target_date = now_local.date()
    is_explicit_today = "today" in clean or "tonight" in clean
    is_explicit_tomorrow = "tomorrow" in clean
    has_explicit_weekday = False

    if is_explicit_tomorrow:
        target_date = (now_local + timedelta(days=1)).date()
    elif is_explicit_today:
        target_date = now_local.date()
    else:
        weekdays = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        for idx, wd in enumerate(weekdays):
            if wd in clean:
                today_weekday = now_local.weekday()
                days_ahead = (idx - today_weekday) % 7
                if days_ahead == 0:
                    days_ahead = 7
                target_date = (now_local + timedelta(days=days_ahead)).date()
                has_explicit_weekday = True
                break

    # Determine time component
    t_match = _parse_time_str(clean)
    if not t_match:
        sub_match = re.search(r"(\d{1,2}(?::\d{2})?\s*(?:am|pm))", clean)
        if sub_match:
            t_match = _parse_time_str(sub_match.group(1))

    if not t_match:
        t_match = time(9, 0)  # Default to 9:00 AM

    local_dt = datetime.combine(target_date, t_match, tzinfo=local_tz)
    dt_utc = local_dt.astimezone(timezone.utc)

    # If no explicit day was specified (e.g. user just said "at 8 PM") and the time has already passed today, advance to tomorrow
    if not is_explicit_today and not is_explicit_tomorrow and not has_explicit_weekday:
        if dt_utc < now_utc:
            local_dt = datetime.combine(target_date + timedelta(days=1), t_match, tzinfo=local_tz)
            dt_utc = local_dt.astimezone(timezone.utc)

    if dt_utc < (now_utc - timedelta(seconds=10)):
        raise ValueError(f"Reminder time '{time_str}' resolves to the past ({dt_utc.strftime('%Y-%m-%d %H:%M:%S UTC')}). Reminders must be scheduled for a future time.")

    return dt_utc


# ---------------------------------------------------------------------------
# Tool Implementations
# ---------------------------------------------------------------------------

class CreateTaskTool(BaseTool):
    name = "create_task"
    description = (
        "Create a new task on the user's TARK Personal OS with title, due date/time, priority, estimated duration, category, and optional reminder."
    )
    input_schema = CreateTaskInput
    permissions = [ToolPermission.USER_DATA]
    category = "personal"

    async def execute(self, arguments: dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        if not context.user_id or not context.session:
            return ToolResult(tool_name=self.name, success=False, error="User authentication and database session required.")

        title = str(arguments.get("title") or "").strip()
        if not title:
            return ToolResult(tool_name=self.name, success=False, error="Task 'title' is required.")

        service = TaskService()
        parsed_due_date = _parse_natural_date(arguments.get("due_date"))
        parsed_due_time = _parse_time_str(arguments.get("due_time"))

        priority_str = str(arguments.get("priority") or "medium").lower()
        priority_enum = TaskPriority.MEDIUM
        for p in TaskPriority:
            if p.value == priority_str:
                priority_enum = p
                break

        # Resolve category ID if category name provided
        category_id = None
        cat_name = arguments.get("category")
        if cat_name:
            categories = await service.list_categories(context.user_id, context.session)
            for c in categories:
                if c.name.lower() == str(cat_name).lower().strip():
                    category_id = c.id
                    break
            if not category_id:
                # Create custom category
                new_cat = await service.create_category(
                    context.user_id, context.session, TaskCategoryCreate(name=str(cat_name).strip())
                )
                category_id = new_cat.id

        # Resolve optional inline reminder
        reminder_time = None
        rem_raw = arguments.get("reminder_time")
        if rem_raw:
            try:
                reminder_time = _parse_reminder_timestamp(str(rem_raw))
            except Exception as e:
                logger.warning("Could not parse inline reminder time: %s", e)

        payload = TaskCreate(
            title=title,
            description=arguments.get("description"),
            due_date=parsed_due_date,
            due_time=parsed_due_time,
            estimated_duration=arguments.get("estimated_duration"),
            priority=priority_enum,
            category_id=category_id,
            is_recurring=bool(arguments.get("is_recurring")),
            recurrence_rule=arguments.get("recurrence_rule"),
            reminder_time=reminder_time,
        )

        try:
            created = await service.create_task(context.user_id, context.session, payload)
            return ToolResult(
                tool_name=self.name,
                success=True,
                data={
                    "task_id": str(created.id),
                    "title": created.title,
                    "due_date": created.due_date.isoformat() if created.due_date else None,
                    "due_time": created.due_time.strftime("%I:%M %p") if created.due_time else None,
                    "priority": created.priority.value,
                    "status": created.status.value,
                    "estimated_duration": created.estimated_duration,
                    "category": created.category_rel.name if created.category_rel else None,
                    "is_recurring": created.is_recurring,
                    "has_reminder": bool(created.reminders),
                    "message": f"Successfully created task '{created.title}' (Priority: {created.priority.value.upper()}).",
                },
                metadata={"task_id": str(created.id), "status": created.status.value},
            )
        except Exception as exc:
            logger.error("CreateTaskTool error: %s", exc)
            return ToolResult(tool_name=self.name, success=False, error=f"Failed to create task: {exc}")


class ListTasksTool(BaseTool):
    name = "list_tasks"
    description = (
        "List tasks from user's personal task manager filtered by time frame ('today', 'tomorrow', 'upcoming', 'overdue', 'completed', 'all'), priority, or category."
    )
    input_schema = ListTasksInput
    permissions = [ToolPermission.USER_DATA]
    category = "personal"

    async def execute(self, arguments: dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        if not context.user_id or not context.session:
            return ToolResult(tool_name=self.name, success=False, error="User authentication and database session required.")

        service = TaskService()
        time_frame = str(arguments.get("time_frame") or "all").lower().strip()
        status_raw = arguments.get("status")
        priority_raw = arguments.get("priority")

        status_enum = None
        if status_raw:
            for s in TaskStatus:
                if s.value == str(status_raw).lower().strip():
                    status_enum = s
                    break

        priority_enum = None
        if priority_raw:
            for p in TaskPriority:
                if p.value == str(priority_raw).lower().strip():
                    priority_enum = p
                    break

        filters = TaskListFilter(
            status=status_enum,
            priority=priority_enum,
            time_frame=time_frame,
            search=arguments.get("search"),
        )

        try:
            tasks = await service.list_tasks(context.user_id, context.session, filters)
            items = []
            for t in tasks:
                items.append({
                    "id": str(t.id),
                    "title": t.title,
                    "status": t.status.value,
                    "priority": t.priority.value,
                    "due_date": t.due_date.isoformat() if t.due_date else None,
                    "due_time": t.due_time.strftime("%I:%M %p") if t.due_time else None,
                    "estimated_duration": t.estimated_duration,
                    "category": t.category_rel.name if t.category_rel else None,
                    "is_recurring": t.is_recurring,
                    "synced_to_calendar": t.synced_to_calendar,
                })

            return ToolResult(
                tool_name=self.name,
                success=True,
                data={
                    "tasks": items,
                    "task_count": len(items),
                    "time_frame": time_frame,
                    "status": "empty" if len(items) == 0 else "tasks_found",
                    "message": f"Retrieved {len(items)} task(s) for time frame '{time_frame}'.",
                },
                metadata={"count": len(items), "time_frame": time_frame},
            )
        except Exception as exc:
            logger.error("ListTasksTool error: %s", exc)
            return ToolResult(tool_name=self.name, success=False, error=f"Failed to list tasks: {exc}")


class UpdateTaskTool(BaseTool):
    name = "update_task"
    description = (
        "Update an existing task's title, due date, due time, priority, status, or estimated duration."
    )
    input_schema = UpdateTaskInput
    permissions = [ToolPermission.USER_DATA]
    category = "personal"

    async def execute(self, arguments: dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        if not context.user_id or not context.session:
            return ToolResult(tool_name=self.name, success=False, error="User authentication and database session required.")

        service = TaskService()
        task_id = arguments.get("task_id")
        title_query = str(arguments.get("title_query") or "").strip()

        # Find target task
        target_task = None
        if task_id:
            try:
                target_task = await service.get_task(context.user_id, context.session, UUID(str(task_id)))
            except Exception:
                pass

        if not target_task and title_query:
            all_tasks = await service.list_tasks(context.user_id, context.session)
            clean_q = title_query.lower()
            for t in all_tasks:
                if clean_q in t.title.lower() or t.title.lower() in clean_q:
                    target_task = t
                    break

        if not target_task:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=f"Task not found matching '{title_query or task_id}'.",
            )

        update_payload = TaskUpdate()
        if arguments.get("title"):
            update_payload.title = str(arguments.get("title")).strip()
        if arguments.get("description") is not None:
            update_payload.description = arguments.get("description")
        if arguments.get("due_date"):
            update_payload.due_date = _parse_natural_date(arguments.get("due_date"))
        if arguments.get("due_time"):
            update_payload.due_time = _parse_time_str(arguments.get("due_time"))
        if arguments.get("estimated_duration"):
            update_payload.estimated_duration = arguments.get("estimated_duration")
        if arguments.get("priority"):
            for p in TaskPriority:
                if p.value == str(arguments.get("priority")).lower().strip():
                    update_payload.priority = p
                    break
        if arguments.get("status"):
            for s in TaskStatus:
                if s.value == str(arguments.get("status")).lower().strip():
                    update_payload.status = s
                    break

        updated = await service.update_task(context.user_id, context.session, target_task.id, update_payload)
        return ToolResult(
            tool_name=self.name,
            success=True,
            data={
                "task_id": str(updated.id),
                "title": updated.title,
                "status": updated.status.value,
                "priority": updated.priority.value,
                "due_date": updated.due_date.isoformat() if updated.due_date else None,
                "due_time": updated.due_time.strftime("%I:%M %p") if updated.due_time else None,
                "message": f"Successfully updated task '{updated.title}'.",
            },
        )


def _match_task_by_query(query: str, tasks: list[Any]) -> Optional[Any]:
    """Find matching task by exact substring, word tokens, or stem matching."""
    clean_q = query.lower().strip()
    # 1. Exact substring check
    for t in tasks:
        t_title = t.title.lower()
        if clean_q in t_title or t_title in clean_q:
            return t
    # 2. Word tokens and stem check (e.g. grocery -> groceries)
    words = [w for w in re.split(r"\W+", clean_q) if len(w) > 2]
    for t in tasks:
        t_title = t.title.lower()
        for w in words:
            if w in t_title:
                return t
            # Stem check (strip 'ies', 'ing', 'ed', 's', 'y')
            stem = w.rstrip("s").rstrip("y")
            if len(stem) >= 3 and stem in t_title:
                return t
            if len(w) >= 4 and t_title.startswith(w[:4]):
                return t
    return None



class CompleteTaskTool(BaseTool):
    name = "complete_task"
    description = (
        "Mark a task as completed in user's personal task manager by ID or title keyword."
    )
    input_schema = CompleteTaskInput
    permissions = [ToolPermission.USER_DATA]
    category = "personal"

    async def execute(self, arguments: dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        if not context.user_id or not context.session:
            return ToolResult(tool_name=self.name, success=False, error="User authentication and database session required.")

        service = TaskService()
        task_id = arguments.get("task_id")
        title_query = str(arguments.get("title") or "").strip()

        target_task = None
        if task_id:
            try:
                target_task = await service.get_task(context.user_id, context.session, UUID(str(task_id)))
            except Exception:
                pass

        if not target_task and title_query:
            all_tasks = await service.list_tasks(context.user_id, context.session)
            target_task = _match_task_by_query(title_query, all_tasks)


        if not target_task:
            return ToolResult(tool_name=self.name, success=False, error=f"Task not found matching '{title_query or task_id}'.")

        completed = await service.complete_task(context.user_id, context.session, target_task.id)
        return ToolResult(
            tool_name=self.name,
            success=True,
            data={
                "task_id": str(completed.id),
                "title": completed.title,
                "status": "completed",
                "completed_at": completed.completed_at.isoformat() if completed.completed_at else None,
                "message": f"Marked task '{completed.title}' as completed!",
            },
            metadata={"task_id": str(completed.id), "status": "completed"},
        )


class DeleteTaskTool(BaseTool):
    name = "delete_task"
    description = (
        "Delete a task from user's personal task manager by ID or title keyword."
    )
    input_schema = DeleteTaskInput
    permissions = [ToolPermission.USER_DATA]
    category = "personal"

    async def execute(self, arguments: dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        if not context.user_id or not context.session:
            return ToolResult(tool_name=self.name, success=False, error="User authentication and database session required.")

        service = TaskService()
        task_id = arguments.get("task_id")
        title_query = str(arguments.get("title") or "").strip()

        target_task = None
        if task_id:
            try:
                target_task = await service.get_task(context.user_id, context.session, UUID(str(task_id)))
            except Exception:
                pass

        if not target_task and title_query:
            all_tasks = await service.list_tasks(context.user_id, context.session)
            target_task = _match_task_by_query(title_query, all_tasks)


        if not target_task:
            return ToolResult(tool_name=self.name, success=False, error=f"Task not found matching '{title_query or task_id}'.")

        task_title = target_task.title
        await service.delete_task(context.user_id, context.session, target_task.id)
        return ToolResult(
            tool_name=self.name,
            success=True,
            data={
                "task_id": str(target_task.id),
                "title": task_title,
                "status": "deleted",
                "message": f"Successfully deleted task '{task_title}'.",
            },
        )


class CreateReminderTool(BaseTool):
    name = "create_reminder"
    description = (
        "Schedule an explicit reminder on user's TARK Personal OS for a given time (e.g. 'tomorrow at 8 PM to pay electricity bill')."
    )
    input_schema = CreateReminderInput
    permissions = [ToolPermission.USER_DATA]
    category = "personal"

    async def execute(self, arguments: dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        if not context.user_id or not context.session:
            return ToolResult(tool_name=self.name, success=False, error="User authentication and database session required.")

        title = str(arguments.get("title") or "").strip()
        time_raw = str(arguments.get("reminder_time") or "").strip()
        if not title or not time_raw:
            return ToolResult(tool_name=self.name, success=False, error="Both 'title' and 'reminder_time' are required.")

        try:
            parsed_dt = _parse_reminder_timestamp(time_raw)
        except Exception as e:
            return ToolResult(tool_name=self.name, success=False, error=f"Could not parse reminder time '{time_raw}': {e}")

        task_id = None
        if arguments.get("task_id"):
            try:
                task_id = UUID(str(arguments.get("task_id")))
            except Exception:
                pass

        service = ReminderService()
        try:
            reminder = await service.create_reminder(
                user_id=context.user_id,
                session=context.session,
                payload=TaskReminderCreate(
                    title=title,
                    reminder_time=parsed_dt,
                    task_id=task_id,
                ),
            )
            return ToolResult(
                tool_name=self.name,
                success=True,
                data={
                    "reminder_id": str(reminder.id),
                    "title": reminder.title,
                    "reminder_time_utc": reminder.reminder_time.isoformat(),
                    "status": reminder.status.value,
                    "message": f"Scheduled reminder for '{reminder.title}' at {time_raw}.",
                },
                metadata={"reminder_id": str(reminder.id), "status": reminder.status.value},
            )
        except Exception as exc:
            logger.error("CreateReminderTool error: %s", exc)
            return ToolResult(tool_name=self.name, success=False, error=f"Failed to create reminder: {exc}")


class ListRemindersTool(BaseTool):
    name = "list_reminders"
    description = (
        "List upcoming or past scheduled reminders for the user."
    )
    input_schema = ListRemindersInput
    permissions = [ToolPermission.USER_DATA]
    category = "personal"

    async def execute(self, arguments: dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        if not context.user_id or not context.session:
            return ToolResult(tool_name=self.name, success=False, error="User authentication and database session required.")

        service = ReminderService()
        time_frame = str(arguments.get("time_frame") or "upcoming").lower()
        status_raw = str(arguments.get("status") or "scheduled").lower()

        status_enum = None
        for s in ReminderStatus:
            if s.value == status_raw:
                status_enum = s
                break

        try:
            reminders = await service.list_reminders(
                user_id=context.user_id,
                session=context.session,
                status=status_enum,
                time_frame=time_frame,
            )
            items = [
                {
                    "id": str(r.id),
                    "title": r.title,
                    "reminder_time": r.reminder_time.isoformat(),
                    "status": r.status.value,
                    "delivered_at": r.delivered_at.isoformat() if r.delivered_at else None,
                }
                for r in reminders
            ]
            return ToolResult(
                tool_name=self.name,
                success=True,
                data={
                    "reminders": items,
                    "reminder_count": len(items),
                    "time_frame": time_frame,
                    "message": f"Found {len(items)} reminder(s).",
                },
            )
        except Exception as exc:
            logger.error("ListRemindersTool error: %s", exc)
            return ToolResult(tool_name=self.name, success=False, error=f"Failed to list reminders: {exc}")


class PlanDayTool(BaseTool):
    name = "plan_day"
    description = (
        "Intelligently synthesize a complete daily plan by combining user's real Google Calendar events, pending/overdue tasks, goal memories, and daylight free time blocks."
    )
    input_schema = PlanDayInput
    permissions = [ToolPermission.USER_DATA, ToolPermission.NETWORK]
    category = "personal"

    async def execute(self, arguments: dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        if not context.user_id or not context.session:
            return ToolResult(tool_name=self.name, success=False, error="User authentication and database session required.")

        planner = DailyPlanningService()
        target_date_raw = arguments.get("target_date") or "today"
        timezone_str = arguments.get("timezone") or "Asia/Kolkata"

        try:
            plan_response = await planner.generate_daily_plan(
                user_id=context.user_id,
                session=context.session,
                target_date_raw=str(target_date_raw),
                timezone_str=str(timezone_str),
            )
            return ToolResult(
                tool_name=self.name,
                success=True,
                data=plan_response.model_dump(),
                metadata={"target_date": plan_response.target_date, "blocks_count": len(plan_response.time_blocks)},
            )
        except Exception as exc:
            logger.error("PlanDayTool error: %s", exc)
            return ToolResult(tool_name=self.name, success=False, error=f"Daily planning failed: {exc}")
