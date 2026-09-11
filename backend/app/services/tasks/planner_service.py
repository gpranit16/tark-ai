import logging
import re
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import MemoryCategory
from app.models.task import Task, TaskPriority, TaskStatus
from app.schemas.task import DailyPlanResponse, PlannedTimeBlock, TaskListFilter
from app.services.integrations.google_calendar import GoogleCalendarService
from app.services.memory.service import MemoryService
from app.services.tasks.service import TaskService

logger = logging.getLogger(__name__)


class DailyPlanningService:
    """Intelligent daily planning and time-blocking engine combining Calendar, Tasks, Goals, and Memory."""

    def __init__(self) -> None:
        self.task_service = TaskService()
        self.calendar_service = GoogleCalendarService()


    async def generate_daily_plan(
        self,
        user_id: UUID,
        session: AsyncSession,
        target_date_raw: Optional[str] = "today",
        timezone_str: str = "Asia/Kolkata",
    ) -> DailyPlanResponse:
        """
        Synthesize a structured day plan:
        1. Fetch real Google Calendar events for the day.
        2. Fetch pending and overdue tasks.
        3. Fetch user goals and preferences from memory.
        4. Match free time blocks with top priority tasks.
        """
        now = datetime.now(timezone.utc)
        target_str = str(target_date_raw or "today").lower().strip()

        if "tomorrow" in target_str:
            plan_date = (now + timedelta(days=1)).date()
        elif "today" in target_str:
            plan_date = now.date()
        else:
            date_match = re.search(r"\d{4}-\d{2}-\d{2}", target_str)
            if date_match:
                try:
                    plan_date = datetime.strptime(date_match.group(0), "%Y-%m-%d").date()
                except Exception:
                    plan_date = now.date()
            else:
                plan_date = now.date()

        date_formatted = plan_date.strftime("%A, %B %d, %Y")

        # 1. Fetch Google Calendar events for the target day
        calendar_events: List[Dict[str, Any]] = []
        try:
            time_min = datetime.combine(plan_date, time.min).replace(tzinfo=timezone.utc)
            time_max = datetime.combine(plan_date, time.max).replace(tzinfo=timezone.utc)
            calendar_events = await self.calendar_service.list_events(
                user_id=user_id,
                session=session,
                time_min=time_min,
                time_max=time_max,
                max_results=20,
            )
        except Exception as e:
            logger.info("Google Calendar events not available for user %s: %s", user_id, e)

        # 2. Fetch User Tasks (Due today + Overdue + Pending high priority)
        all_tasks = await self.task_service.list_tasks(
            user_id=user_id,
            session=session,
            filters=TaskListFilter(sort_by="priority", order="desc"),
        )

        overdue_tasks = [
            t for t in all_tasks
            if t.due_date and t.due_date < plan_date and t.status in (TaskStatus.PENDING, TaskStatus.IN_PROGRESS)
        ]
        due_tasks = [
            t for t in all_tasks
            if t.due_date == plan_date and t.status in (TaskStatus.PENDING, TaskStatus.IN_PROGRESS)
        ]
        other_pending = [
            t for t in all_tasks
            if (not t.due_date or t.due_date > plan_date) and t.status in (TaskStatus.PENDING, TaskStatus.IN_PROGRESS)
        ]

        # Prioritize tasks: Overdue > Due Today (Urgent > High > Medium > Low) > Other Pending
        actionable_tasks: List[Task] = []
        actionable_tasks.extend(overdue_tasks)
        actionable_tasks.extend(due_tasks)
        actionable_tasks.extend(other_pending[:5])

        # 3. Fetch User Goals & Preferences from Memory
        goal_memories: List[str] = []
        pref_memories: List[str] = []
        try:
            mem_service = MemoryService(session)
            mem_resp = await mem_service.list_memories(user_id=user_id)
            goal_memories = [m.value for m in mem_resp.items if m.category == MemoryCategory.GOAL]
            pref_memories = [m.value for m in mem_resp.items if m.category == MemoryCategory.PREFERENCE]
        except Exception as mem_err:
            logger.info("Memory fetch skipped during daily planning: %s", mem_err)


        # 4. Construct Time Blocks
        time_blocks: List[PlannedTimeBlock] = []

        # Add existing calendar events first
        for ev in calendar_events:
            ev_start = self._extract_display_time(ev.get("start", ""))
            ev_end = self._extract_display_time(ev.get("end", ""))
            time_blocks.append(
                PlannedTimeBlock(
                    start_time=ev_start or "Scheduled",
                    end_time=ev_end or "Scheduled",
                    title=ev.get("summary") or "Calendar Event",
                    type="calendar_event",
                    calendar_event_id=ev.get("id"),
                    notes="Google Calendar Event",
                )
            )

        # Map available task time slots across the day (9:00 AM, 11:30 AM, 2:30 PM, 5:00 PM, 7:30 PM)
        candidate_slots = [
            ("09:00 AM", "10:00 AM"),
            ("11:00 AM", "12:00 PM"),
            ("02:00 PM", "03:00 PM"),
            ("04:30 PM", "05:30 PM"),
            ("07:00 PM", "08:00 PM"),
            ("08:30 PM", "09:30 PM"),
        ]

        task_idx = 0
        for slot_start, slot_end in candidate_slots:
            if task_idx >= len(actionable_tasks):
                break

            # Check if this slot clashes with an existing calendar event
            clashes = False
            for cb in time_blocks:
                if cb.type == "calendar_event" and (cb.start_time.startswith(slot_start[:2]) or cb.start_time == slot_start):
                    clashes = True
                    break

            if not clashes:
                current_task = actionable_tasks[task_idx]
                dur_minutes = current_task.estimated_duration or 45
                end_time_str = slot_end if dur_minutes >= 45 else self._calc_slot_end(slot_start, dur_minutes)

                notes = f"Priority: {current_task.priority.value.upper()}"
                if current_task in overdue_tasks:
                    notes += " (OVERDUE)"
                elif current_task in due_tasks:
                    notes += " (Due Today)"

                time_blocks.append(
                    PlannedTimeBlock(
                        start_time=slot_start,
                        end_time=end_time_str,
                        title=current_task.title,
                        type="task",
                        task_id=str(current_task.id),
                        priority=current_task.priority.value,
                        notes=notes,
                    )
                )
                task_idx += 1

        # Add evening review block
        time_blocks.append(
            PlannedTimeBlock(
                start_time="09:30 PM",
                end_time="10:00 PM",
                title="Daily Wrap-up & Tomorrow Planning",
                type="routine",
                notes="Review finished tasks and set top 3 goals for tomorrow.",
            )
        )

        # Sort all blocks by start time string
        time_blocks.sort(key=lambda b: b.start_time)

        # Build top priorities list
        top_priorities = [f"{t.title} ({t.priority.value.upper()})" for t in actionable_tasks[:3]]
        if goal_memories:
            top_priorities.append(f"Focus Goal: {goal_memories[0]}")

        summary = (
            f"Plan for {date_formatted}: {len(calendar_events)} calendar event(s), "
            f"{len(actionable_tasks)} prioritized task(s) scheduled into available daylight blocks."
        )

        return DailyPlanResponse(
            target_date=date_formatted,
            timezone=timezone_str,
            calendar_events_count=len(calendar_events),
            tasks_count=len(actionable_tasks),
            overdue_count=len(overdue_tasks),
            time_blocks=time_blocks,
            summary=summary,
            top_priorities=top_priorities,
        )

    def _extract_display_time(self, dt_str: str) -> str:
        """Extract readable HH:MM AM/PM from ISO string."""
        if not dt_str:
            return ""
        try:
            # Handle formats like 2026-09-12T19:00:00+05:30 or 2026-09-12T10:00:00Z
            clean = dt_str.replace("Z", "+00:00")
            dt = datetime.fromisoformat(clean)
            return dt.strftime("%I:%M %p")
        except Exception:
            return dt_str[:16]

    def _calc_slot_end(self, start_str: str, minutes: int) -> str:
        """Calculate end time string from start time like '09:00 AM'."""
        try:
            dt = datetime.strptime(start_str, "%I:%M %p")
            end_dt = dt + timedelta(minutes=minutes)
            return end_dt.strftime("%I:%M %p")
        except Exception:
            return start_str
