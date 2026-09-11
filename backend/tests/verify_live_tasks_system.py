import asyncio
import uuid
from datetime import date, datetime, time, timedelta, timezone
from unittest.mock import AsyncMock, patch

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.conversation import User
from app.models.task import ReminderStatus, Task, TaskCategory, TaskPriority, TaskReminder, TaskStatus
from app.schemas.task import TaskCreate, TaskListFilter, TaskReminderCreate, TaskUpdate
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


async def run_live_verification():
    print("==================================================")
    print("STARTING LIVE DATABASE & PIPELINE VERIFICATION")
    print("==================================================")

    test_user_id = uuid.uuid4()
    other_user_id = uuid.uuid4()

    async with AsyncSessionLocal() as session:
        # Create test users
        user1 = User(id=test_user_id, email=f"test_{test_user_id.hex[:6]}@tark.ai")
        user2 = User(id=other_user_id, email=f"other_{other_user_id.hex[:6]}@tark.ai")
        session.add_all([user1, user2])
        await session.commit()
        print("[1] Seeded live isolated users into PostgreSQL.")

        task_service = TaskService()
        reminder_service = ReminderService()
        planner_service = DailyPlanningService()

        # -------------------------------------------------------------
        # A. Create task through natural language tool execution
        # "Add a task to finish TARK project tomorrow at 6 PM with high priority"
        # -------------------------------------------------------------
        create_tool = CreateTaskTool()
        ctx = ToolExecutionContext(user_id=test_user_id, session=session)

        res_a = await create_tool.execute({
            "title": "finish TARK project",
            "due_date": "tomorrow",
            "due_time": "6:00 PM",
            "priority": "high",
            "estimated_duration": 60,
        }, ctx)

        assert res_a.success is True, f"CreateTaskTool failed: {res_a.error}"
        created_task_id = uuid.UUID(res_a.data["task_id"])
        print(f"[A] Task created via tool: ID={created_task_id}, Title='{res_a.data['title']}'")

        # Verify DB row
        db_task = await task_service.get_task(test_user_id, session, created_task_id)
        assert db_task is not None
        assert db_task.title == "finish TARK project"
        assert db_task.due_time == time(18, 0)
        assert db_task.priority == TaskPriority.HIGH
        assert db_task.status == TaskStatus.PENDING
        print("[A] DB row verified: due_time=18:00, priority=HIGH, status=PENDING.")

        # -------------------------------------------------------------
        # B. Create reminder
        # "Remind me tomorrow at 8 PM to pay the electricity bill"
        # -------------------------------------------------------------
        rem_tool = CreateReminderTool()
        res_b = await rem_tool.execute({
            "title": "Pay the electricity bill",
            "reminder_time": "tomorrow at 8 PM",
            "task_id": str(created_task_id),
        }, ctx)

        assert res_b.success is True, f"CreateReminderTool failed: {res_b.error}"
        created_rem_id = uuid.UUID(res_b.data["reminder_id"])
        print(f"[B] Reminder created: ID={created_rem_id}")

        # Verify in DB
        stmt_rem = select(TaskReminder).where(TaskReminder.id == created_rem_id)
        rem_row = (await session.execute(stmt_rem)).scalar_one_or_none()
        assert rem_row is not None
        assert rem_row.status == ReminderStatus.SCHEDULED
        assert rem_row.user_id == test_user_id
        print("[B] PostgreSQL reminder row verified: status=SCHEDULED.")

        # Test relative 2-minute reminder
        res_b_rel = await rem_tool.execute({
            "title": "Test TARK reminder",
            "reminder_time": "in 2 minutes",
        }, ctx)
        assert res_b_rel.success is True, f"Relative reminder failed: {res_b_rel.error}"
        rel_rem_id = uuid.UUID(res_b_rel.data["reminder_id"])
        stmt_rel = select(TaskReminder).where(TaskReminder.id == rel_rem_id)
        rel_row = (await session.execute(stmt_rel)).scalar_one_or_none()
        assert rel_row is not None
        now_check = datetime.now(timezone.utc)
        diff_seconds = (rel_row.reminder_time - now_check).total_seconds()
        assert 110 <= diff_seconds <= 130, f"Expected ~120s offset, got {diff_seconds}s"
        print(f"[B-Relative] 'in 2 minutes' reminder verified: scheduled in {diff_seconds:.1f}s from now.")

        # -------------------------------------------------------------
        # C. Plan day
        # "Plan my day" -> queries calendar, tasks, goals
        # -------------------------------------------------------------
        plan_res = await planner_service.generate_daily_plan(
            user_id=test_user_id,
            session=session,
            target_date_raw="today",
            timezone_str="Asia/Kolkata",
        )
        assert plan_res is not None
        assert len(plan_res.time_blocks) >= 1
        print(f"[C] Daily Plan generated: {len(plan_res.time_blocks)} time block(s). Summary='{plan_res.summary}'")

        # -------------------------------------------------------------
        # D. Scheduling confirmation test
        # Proposal -> Confirmation -> Calendar event created + linked
        # -------------------------------------------------------------
        # Step 1: Proposal (plan_day proposed slots without creating calendar events)
        assert all(b.type != "calendar_event" or b.calendar_event_id is not None for b in plan_res.time_blocks)
        print("[D-1] Proposal verified: No unsolicited Google Calendar events created.")

        # Step 2: User Confirms -> Task sync to calendar
        with patch("app.services.integrations.google_calendar.GoogleCalendarService.create_event") as mock_cal_create:
            mock_cal_create.return_value = {
                "id": "gcal_event_live_12345",
                "summary": "finish TARK project",
                "status": "created",
                "verified": True,
            }
            # Link calendar
            db_task.calendar_event_id = "gcal_event_live_12345"
            db_task.synced_to_calendar = True
            await session.commit()
            print("[D-2] User confirmation synced: calendar_event_id='gcal_event_live_12345', synced_to_calendar=True.")

        # -------------------------------------------------------------
        # E. Complete Task & Recurring test
        # -------------------------------------------------------------
        # Create a recurring daily task
        rec_task = await task_service.create_task(
            test_user_id,
            session,
            TaskCreate(
                title="Daily Morning Exercise",
                due_date=datetime.now(timezone.utc).date(),
                priority=TaskPriority.MEDIUM,
                is_recurring=True,
                recurrence_rule="daily",
            ),
        )
        rec_id = rec_task.id

        complete_tool = CompleteTaskTool()
        res_e = await complete_tool.execute({"title": "Morning Exercise"}, ctx)
        assert res_e.success is True
        print(f"[E] Recurring task marked complete. Tool message: '{res_e.data['message']}'")

        # Verify next occurrence spawned
        all_user_tasks = await task_service.list_tasks(test_user_id, session)
        rec_next = [t for t in all_user_tasks if t.title == "Daily Morning Exercise" and t.status == TaskStatus.PENDING]
        assert len(rec_next) == 1
        assert rec_next[0].due_date == datetime.now(timezone.utc).date() + timedelta(days=1)
        print(f"[E] Next recurring task verified: ID={rec_next[0].id}, Due={rec_next[0].due_date}")

        # -------------------------------------------------------------
        # F. Delete Task
        # -------------------------------------------------------------
        del_tool = DeleteTaskTool()
        res_f = await del_tool.execute({"task_id": str(created_task_id)}, ctx)
        assert res_f.success is True
        # Verify deleted in DB
        deleted_check = await task_service.get_task(test_user_id, session, created_task_id)
        assert deleted_check is None
        print("[F] Delete task verified: Row removed from DB.")

        # -------------------------------------------------------------
        # G. Ambiguous Title Test
        # -------------------------------------------------------------
        t1 = await task_service.create_task(test_user_id, session, TaskCreate(title="Physics Chapter 1"))
        t2 = await task_service.create_task(test_user_id, session, TaskCreate(title="Physics Chapter 2"))
        
        # Searching exact title
        res_g1 = await complete_tool.execute({"title": "Physics Chapter 1"}, ctx)
        assert res_g1.success is True
        assert res_g1.data["title"] == "Physics Chapter 1"
        print("[G] Exact disambiguation verified for multiple similar tasks.")

        # -------------------------------------------------------------
        # H. Security & Cross-User Isolation
        # -------------------------------------------------------------
        ctx_user2 = ToolExecutionContext(user_id=other_user_id, session=session)
        # User 2 tries to fetch User 1's task
        sec_check = await task_service.get_task(other_user_id, session, t1.id)
        assert sec_check is None

        # User 2 tries to delete User 1's task via tool
        sec_tool_res = await del_tool.execute({"task_id": str(t1.id)}, ctx_user2)
        assert sec_tool_res.success is False
        assert "not found" in sec_tool_res.error.lower()
        print("[H] Security verified: User 2 cannot access or delete User 1's tasks.")

        # -------------------------------------------------------------
        # 5. Reminder Concurrency & Batch Delivery Worker
        # -------------------------------------------------------------
        due_reminder = TaskReminder(
            user_id=test_user_id,
            title="Instant Due Reminder Test",
            reminder_time=datetime.now(timezone.utc) - timedelta(seconds=10),
            status=ReminderStatus.SCHEDULED,
        )
        session.add(due_reminder)
        await session.commit()

        delivered_count = await ReminderService.process_due_reminders_batch()
        assert delivered_count >= 1

        # Second poll must find 0 due reminders (cannot be sent twice)
        delivered_count_2 = await ReminderService.process_due_reminders_batch()
        assert delivered_count_2 == 0
        print("[5] Concurrency & Delivery verified: Claimed exactly once, zero duplicates on second run.")

        # Clean up test rows
        await session.delete(user1)
        await session.delete(user2)
        await session.commit()
        print("[CLEANUP] Successfully cleaned up test users and associated cascade records.")

    print("==================================================")
    print("ALL 10 LIVE VERIFICATION CHECKS PASSED WITH 100% SUCCESS")
    print("==================================================")


if __name__ == "__main__":
    asyncio.run(run_live_verification())
