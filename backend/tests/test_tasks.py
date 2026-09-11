import uuid
from datetime import date, datetime, time, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import User
from app.models.task import ReminderStatus, Task, TaskCategory, TaskPriority, TaskReminder, TaskStatus
from app.schemas.task import (
    TaskCategoryCreate,
    TaskCreate,
    TaskListFilter,
    TaskReminderCreate,
    TaskUpdate,
)
from app.services.tasks.planner_service import DailyPlanningService
from app.services.tasks.reminder_service import ReminderService
from app.services.tasks.service import TaskService
from app.tools.base import ToolExecutionContext
from app.tools.builtins.task_tools import (
    CompleteTaskTool,
    CreateReminderTool,
    CreateTaskTool,
    DeleteTaskTool,
    ListRemindersTool,
    ListTasksTool,
    PlanDayTool,
    UpdateTaskTool,
)
from app.tools.registry import get_tool_registry

USER_A_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
USER_B_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")


@pytest.fixture
def mock_session():
    session = AsyncMock(spec=AsyncSession)
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.delete = AsyncMock()
    return session


# ---------------------------------------------------------------------------
# Task Registry Verification
# ---------------------------------------------------------------------------

def test_task_tools_registered():
    """Verify all 8 task tools and aliases are properly registered in ToolRegistry."""
    registry = get_tool_registry()
    task_tools = [
        "create_task",
        "list_tasks",
        "update_task",
        "complete_task",
        "delete_task",
        "create_reminder",
        "list_reminders",
        "plan_day",
    ]
    for name in task_tools:
        assert registry.has_tool(name), f"Tool {name} not found in registry"
        assert registry.get(name) is not None

    # Test aliases
    assert registry.get("add_task") is not None
    assert registry.get("remind_me") is not None
    assert registry.get("plan_my_day") is not None


# ---------------------------------------------------------------------------
# Task Service Unit Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_task_crud_lifecycle(mock_session):
    """Test full CRUD lifecycle for tasks."""
    service = TaskService()
    now_utc = datetime.now(timezone.utc)
    mock_task = Task(
        id=uuid.uuid4(),
        user_id=USER_A_ID,
        title="Revise DBMS Transactions",
        description="ACID properties and 2PL",
        due_date=now_utc.date(),
        due_time=time(19, 0),
        estimated_duration=45,
        priority=TaskPriority.HIGH,
        status=TaskStatus.PENDING,
    )

    # Mock get_task return
    mock_exec = MagicMock()
    mock_exec.scalar_one_or_none.return_value = mock_task
    mock_session.execute.return_value = mock_exec

    # Test get_task
    fetched = await service.get_task(USER_A_ID, mock_session, mock_task.id)
    assert fetched is not None
    assert fetched.title == "Revise DBMS Transactions"
    assert fetched.priority == TaskPriority.HIGH

    # Test complete_task
    completed = await service.complete_task(USER_A_ID, mock_session, mock_task.id)
    assert completed.status == TaskStatus.COMPLETED
    assert completed.completed_at is not None

    # Test reopen_task
    reopened = await service.reopen_task(USER_A_ID, mock_session, mock_task.id)
    assert reopened.status == TaskStatus.PENDING
    assert reopened.completed_at is None


@pytest.mark.asyncio
async def test_recurring_task_next_generation(mock_session):
    """Test that completing a recurring task automatically spawns the next occurrence."""
    service = TaskService()
    today = date(2026, 9, 12)
    mock_task = Task(
        id=uuid.uuid4(),
        user_id=USER_A_ID,
        title="Morning Schedule Review",
        due_date=today,
        due_time=time(8, 0),
        priority=TaskPriority.MEDIUM,
        status=TaskStatus.PENDING,
        is_recurring=True,
        recurrence_rule="daily",
    )

    mock_exec = MagicMock()
    mock_exec.scalar_one_or_none.return_value = mock_task
    # Also mock empty scalar for reminders
    mock_rem_scalars = MagicMock()
    mock_rem_scalars.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_rem_scalars
    mock_session.execute.side_effect = [mock_exec, mock_rem_scalars, mock_exec]

    completed = await service.complete_task(USER_A_ID, mock_session, mock_task.id)
    assert completed.status == TaskStatus.COMPLETED

    # Verify session.add was called to create the next day task
    assert mock_session.add.called
    added_objs = [call[0][0] for call in mock_session.add.call_args_list if isinstance(call[0][0], Task)]
    assert len(added_objs) > 0
    next_task = added_objs[0]
    assert next_task.due_date == today + timedelta(days=1)
    assert next_task.status == TaskStatus.PENDING


# ---------------------------------------------------------------------------
# Reminder Service Unit Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_reminder_creation_and_delivery(mock_session):
    """Test creating a scheduled reminder and processing delivery."""
    service = ReminderService()
    future_time = datetime.now(timezone.utc) + timedelta(hours=2)

    payload = TaskReminderCreate(
        title="Pay the electricity bill",
        reminder_time=future_time,
    )

    created = await service.create_reminder(USER_A_ID, mock_session, payload)
    assert created.title == "Pay the electricity bill"
    assert created.status == ReminderStatus.SCHEDULED


# ---------------------------------------------------------------------------
# User Isolation Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_user_isolation(mock_session):
    """Verify User A cannot access User B's task."""
    service = TaskService()
    task_b = Task(
        id=uuid.uuid4(),
        user_id=USER_B_ID,
        title="User B Private Task",
    )

    # Return None when User A queries User B's task
    mock_exec = MagicMock()
    mock_exec.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_exec

    result = await service.get_task(USER_A_ID, mock_session, task_b.id)
    assert result is None


# ---------------------------------------------------------------------------
# AI Tool Execution Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ai_create_task_tool(mock_session):
    """Test AI CreateTaskTool execution."""
    tool = CreateTaskTool()
    ctx = ToolExecutionContext(user_id=USER_A_ID, session=mock_session)

    with patch("app.services.tasks.service.TaskService.create_task") as mock_create:
        mock_task = Task(
            id=uuid.uuid4(),
            user_id=USER_A_ID,
            title="Finish TARK project",
            due_date=date(2026, 9, 15),
            due_time=time(18, 0),
            priority=TaskPriority.HIGH,
            status=TaskStatus.PENDING,
            estimated_duration=90,
            reminders=[],
        )
        mock_create.return_value = mock_task

        res = await tool.execute({
            "title": "Finish TARK project",
            "due_date": "2026-09-15",
            "due_time": "6:00 PM",
            "priority": "high",
            "estimated_duration": 90,
        }, ctx)

        assert res.success is True
        assert res.data["title"] == "Finish TARK project"
        assert res.data["priority"] == "high"
        assert res.data["estimated_duration"] == 90


@pytest.mark.asyncio
async def test_ai_complete_task_tool(mock_session):
    """Test AI CompleteTaskTool execution by title keyword."""
    tool = CompleteTaskTool()
    ctx = ToolExecutionContext(user_id=USER_A_ID, session=mock_session)

    with patch("app.services.tasks.service.TaskService.list_tasks") as mock_list, \
         patch("app.services.tasks.service.TaskService.complete_task") as mock_complete:
        
        task_id = uuid.uuid4()
        mock_task = Task(id=task_id, user_id=USER_A_ID, title="Buy groceries")
        mock_list.return_value = [mock_task]

        completed_task = Task(id=task_id, user_id=USER_A_ID, title="Buy groceries", status=TaskStatus.COMPLETED, completed_at=datetime.now(timezone.utc))
        mock_complete.return_value = completed_task

        res = await tool.execute({"title": "grocery"}, ctx)
        assert res.success is True
        assert res.data["status"] == "completed"
        assert res.data["title"] == "Buy groceries"


@pytest.mark.asyncio
async def test_ai_create_reminder_tool(mock_session):
    """Test AI CreateReminderTool natural language parsing."""
    tool = CreateReminderTool()
    ctx = ToolExecutionContext(user_id=USER_A_ID, session=mock_session)

    with patch("app.services.tasks.reminder_service.ReminderService.create_reminder") as mock_rem:
        rem_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        mock_rem.return_value = TaskReminder(
            id=rem_id,
            user_id=USER_A_ID,
            title="Pay electricity bill",
            reminder_time=now + timedelta(hours=1),
            status=ReminderStatus.SCHEDULED,
        )

        res = await tool.execute({
            "title": "Pay electricity bill",
            "reminder_time": "in 1 hour",
        }, ctx)

        assert res.success is True
        assert res.data["title"] == "Pay electricity bill"
        assert res.data["status"] == "scheduled"


@pytest.mark.asyncio
async def test_ai_plan_day_tool(mock_session):
    """Test AI PlanDayTool combining calendar and tasks."""
    tool = PlanDayTool()
    ctx = ToolExecutionContext(user_id=USER_A_ID, session=mock_session)

    with patch("app.services.integrations.google_calendar.GoogleCalendarService.list_events") as mock_cal, \
         patch("app.services.tasks.service.TaskService.list_tasks") as mock_tasks, \
         patch("app.services.memory.service.MemoryService.list_memories") as mock_mem:

        mock_cal.return_value = [
            {"id": "cal_1", "summary": "Team Sync", "start": "2026-09-12T10:00:00+05:30", "end": "2026-09-12T11:00:00+05:30"}
        ]
        mock_tasks.return_value = [
            Task(id=uuid.uuid4(), user_id=USER_A_ID, title="Database study", priority=TaskPriority.HIGH, status=TaskStatus.PENDING, estimated_duration=60),
            Task(id=uuid.uuid4(), user_id=USER_A_ID, title="Gym Workout", priority=TaskPriority.MEDIUM, status=TaskStatus.PENDING, estimated_duration=45),
        ]
        from app.schemas.memory import MemoryListResponse
        mock_mem.return_value = MemoryListResponse(items=[], total=0, limit=50, offset=0)

        res = await tool.execute({"target_date": "today"}, ctx)
        assert res.success is True
        assert res.data["calendar_events_count"] == 1
        assert res.data["tasks_count"] == 2
        assert len(res.data["time_blocks"]) >= 3


# ---------------------------------------------------------------------------
# Relative Time & In-App Notification Delivery Regression Tests
# ---------------------------------------------------------------------------

def test_relative_time_resolution_in_2_minutes():
    """Verify 'in 2 minutes' and relative phrases resolve to current fresh time + offset."""
    from app.tools.builtins.task_tools import _parse_reminder_timestamp
    now_utc = datetime.now(timezone.utc)

    # 1. in 2 minutes
    dt_2m = _parse_reminder_timestamp("in 2 minutes")
    diff_2m = (dt_2m - now_utc).total_seconds()
    assert 115 <= diff_2m <= 125, f"Expected ~120s offset, got {diff_2m}s"

    # 2. in 30 mins
    dt_30m = _parse_reminder_timestamp("in 30 mins")
    diff_30m = (dt_30m - now_utc).total_seconds()
    assert 1790 <= diff_30m <= 1810, f"Expected ~1800s offset, got {diff_30m}s"

    # 3. in 1 hour
    dt_1h = _parse_reminder_timestamp("in 1 hour")
    diff_1h = (dt_1h - now_utc).total_seconds()
    assert 3590 <= diff_1h <= 3610, f"Expected ~3600s offset, got {diff_1h}s"

    # 4. after 45 seconds
    dt_45s = _parse_reminder_timestamp("after 45 seconds")
    diff_45s = (dt_45s - now_utc).total_seconds()
    assert 40 <= diff_45s <= 50, f"Expected ~45s offset, got {diff_45s}s"


@pytest.mark.asyncio
async def test_past_time_reminder_rejection(mock_session):
    """Verify reminders resolving to the past are strictly rejected."""
    from app.tools.builtins.task_tools import _parse_reminder_timestamp

    # 1. Parser rejects past ISO timestamp
    with pytest.raises(ValueError, match="past"):
        _parse_reminder_timestamp("2020-01-01T12:00:00Z")

    # 2. Service rejects past reminder
    service = ReminderService()
    past_time = datetime.now(timezone.utc) - timedelta(hours=2)
    with pytest.raises(ValueError, match="past"):
        await service.create_reminder(
            USER_A_ID,
            mock_session,
            TaskReminderCreate(title="Past Test", reminder_time=past_time),
        )

    # 3. Tool execution returns error on past time
    tool = CreateReminderTool()
    ctx = ToolExecutionContext(user_id=USER_A_ID, session=mock_session)
    res = await tool.execute({
        "title": "Past reminder",
        "reminder_time": "2020-01-01T12:00:00Z",
    }, ctx)
    assert res.success is False
    assert "past" in res.error.lower()


@pytest.mark.asyncio
async def test_worker_in_app_notification_delivery():
    """Verify live in-app SSE notification delivery from reminder dispatch."""
    import asyncio
    queue = asyncio.Queue()
    ReminderService.register_subscriber(USER_A_ID, queue)

    try:
        sample_payload = {
            "event": "reminder_due",
            "reminder_id": str(uuid.uuid4()),
            "title": "Test In-App Reminder",
            "reminder_time": datetime.now(timezone.utc).isoformat(),
        }

        # Dispatch notification
        ReminderService.dispatch_in_app_notification(USER_A_ID, sample_payload)

        # Receive from queue
        received = await asyncio.wait_for(queue.get(), timeout=2.0)
        assert received["event"] == "reminder_due"
        assert received["title"] == "Test In-App Reminder"
    finally:
        ReminderService.unregister_subscriber(USER_A_ID, queue)

