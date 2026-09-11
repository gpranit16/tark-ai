import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, List, Optional
from uuid import UUID

from sqlalchemy import and_, delete, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.task import (
    ReminderStatus,
    Task,
    TaskCategory,
    TaskPriority,
    TaskReminder,
    TaskStatus,
)
from app.schemas.task import (
    TaskCategoryCreate,
    TaskCategoryUpdate,
    TaskCreate,
    TaskListFilter,
    TaskUpdate,
)

logger = logging.getLogger(__name__)


class TaskService:
    """Core service for managing user tasks, categories, and calendar linking."""

    # -----------------------------------------------------------------------
    # Task Categories
    # -----------------------------------------------------------------------

    async def list_categories(self, user_id: UUID, session: AsyncSession) -> List[TaskCategory]:
        """List all custom and default categories for the user."""
        stmt = (
            select(TaskCategory)
            .where(TaskCategory.user_id == user_id)
            .order_by(TaskCategory.name.asc())
        )
        res = await session.execute(stmt)
        categories = list(res.scalars().all())

        # If user has no categories yet, initialize default starter categories
        if not categories:
            default_categories = [
                TaskCategory(user_id=user_id, name="Work", color="#3B82F6", icon="briefcase"),
                TaskCategory(user_id=user_id, name="Personal", color="#D6B56A", icon="user"),
                TaskCategory(user_id=user_id, name="Study", color="#10B981", icon="book-open"),
                TaskCategory(user_id=user_id, name="Health", color="#EC4899", icon="heart"),
                TaskCategory(user_id=user_id, name="Finance", color="#F59E0B", icon="dollar-sign"),
                TaskCategory(user_id=user_id, name="Projects", color="#8B5CF6", icon="folder"),
            ]
            for cat in default_categories:
                session.add(cat)
            try:
                await session.commit()
                return default_categories
            except Exception as e:
                await session.rollback()
                logger.warning("Could not auto-seed default task categories: %s", e)
                stmt = select(TaskCategory).where(TaskCategory.user_id == user_id)
                res = await session.execute(stmt)
                return list(res.scalars().all())

        return categories

    async def create_category(
        self, user_id: UUID, session: AsyncSession, payload: TaskCategoryCreate
    ) -> TaskCategory:
        """Create a new custom category for user."""
        category = TaskCategory(
            user_id=user_id,
            name=payload.name.strip(),
            color=payload.color or "#D6B56A",
            icon=payload.icon or "tag",
        )
        session.add(category)
        await session.commit()
        await session.refresh(category)
        return category

    async def delete_category(
        self, user_id: UUID, session: AsyncSession, category_id: UUID
    ) -> bool:
        """Delete a custom category."""
        stmt = select(TaskCategory).where(
            TaskCategory.id == category_id, TaskCategory.user_id == user_id
        )
        res = await session.execute(stmt)
        category = res.scalar_one_or_none()
        if not category:
            return False
        await session.delete(category)
        await session.commit()
        return True

    # -----------------------------------------------------------------------
    # Task Operations
    # -----------------------------------------------------------------------

    async def create_task(
        self, user_id: UUID, session: AsyncSession, payload: TaskCreate
    ) -> Task:
        """Create a task for the authenticated user."""
        task = Task(
            user_id=user_id,
            category_id=payload.category_id,
            title=payload.title.strip(),
            description=payload.description.strip() if payload.description else None,
            due_date=payload.due_date,
            due_time=payload.due_time,
            estimated_duration=payload.estimated_duration,
            priority=payload.priority or TaskPriority.MEDIUM,
            status=payload.status or TaskStatus.PENDING,
            tags=payload.tags or [],
            is_recurring=payload.is_recurring,
            recurrence_rule=payload.recurrence_rule,
            calendar_event_id=payload.calendar_event_id,
            synced_to_calendar=payload.synced_to_calendar,
        )
        session.add(task)
        await session.flush()

        # Optional inline reminder creation
        if payload.reminder_time:
            reminder = TaskReminder(
                user_id=user_id,
                task_id=task.id,
                title=f"Reminder: {task.title}",
                reminder_time=payload.reminder_time,
                status=ReminderStatus.SCHEDULED,
            )
            session.add(reminder)

        await session.commit()
        return await self.get_task(user_id, session, task.id)

    async def get_task(
        self, user_id: UUID, session: AsyncSession, task_id: UUID
    ) -> Optional[Task]:
        """Fetch a single task with relationships for authenticated user."""
        stmt = (
            select(Task)
            .options(selectinload(Task.category_rel), selectinload(Task.reminders))
            .where(Task.id == task_id, Task.user_id == user_id)
        )
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_tasks(
        self, user_id: UUID, session: AsyncSession, filters: Optional[TaskListFilter] = None
    ) -> List[Task]:
        """List tasks with flexible filtering, status, priority, and date frames."""
        stmt = (
            select(Task)
            .options(selectinload(Task.category_rel), selectinload(Task.reminders))
            .where(Task.user_id == user_id)
        )

        today = datetime.now(timezone.utc).date()

        if filters:
            if filters.status:
                stmt = stmt.where(Task.status == filters.status)

            if filters.priority:
                stmt = stmt.where(Task.priority == filters.priority)

            if filters.category_id:
                stmt = stmt.where(Task.category_id == filters.category_id)

            if filters.search:
                pattern = f"%{filters.search.strip()}%"
                stmt = stmt.where(
                    or_(
                        Task.title.ilike(pattern),
                        Task.description.ilike(pattern),
                    )
                )

            # Time frame filters
            if filters.time_frame:
                tf = filters.time_frame.lower().strip()
                if tf == "today":
                    stmt = stmt.where(
                        and_(
                            Task.due_date == today,
                            Task.status != TaskStatus.COMPLETED,
                            Task.status != TaskStatus.CANCELLED,
                        )
                    )
                elif tf == "tomorrow":
                    tomorrow = today + timedelta(days=1)
                    stmt = stmt.where(
                        and_(
                            Task.due_date == tomorrow,
                            Task.status != TaskStatus.COMPLETED,
                            Task.status != TaskStatus.CANCELLED,
                        )
                    )
                elif tf == "overdue":
                    stmt = stmt.where(
                        and_(
                            Task.due_date < today,
                            Task.status.in_([TaskStatus.PENDING, TaskStatus.IN_PROGRESS]),
                        )
                    )
                elif tf == "upcoming":
                    stmt = stmt.where(
                        and_(
                            Task.due_date >= today,
                            Task.status.in_([TaskStatus.PENDING, TaskStatus.IN_PROGRESS]),
                        )
                    )
                elif tf == "completed":
                    stmt = stmt.where(Task.status == TaskStatus.COMPLETED)

            # Sorting
            sort_by = filters.sort_by or "due_time"
            is_desc = (filters.order or "asc").lower() == "desc"

            if sort_by == "priority":
                # Urgent -> High -> Medium -> Low
                order_col = Task.priority
            elif sort_by == "created_at":
                order_col = Task.created_at
            elif sort_by == "title":
                order_col = Task.title
            else:
                # Default due_date then due_time
                order_col = Task.due_date

            if is_desc:
                stmt = stmt.order_by(desc(order_col).nullslast(), desc(Task.due_time).nullslast(), desc(Task.created_at))
            else:
                stmt = stmt.order_by(order_col.nullslast(), Task.due_time.nullslast(), Task.created_at.desc())
        else:
            stmt = stmt.order_by(Task.due_date.nullslast(), Task.due_time.nullslast(), Task.created_at.desc())

        res = await session.execute(stmt)
        return list(res.scalars().all())

    async def update_task(
        self, user_id: UUID, session: AsyncSession, task_id: UUID, payload: TaskUpdate
    ) -> Optional[Task]:
        """Update an existing task."""
        task = await self.get_task(user_id, session, task_id)
        if not task:
            return None

        update_dict = payload.model_dump(exclude_unset=True)
        for field, value in update_dict.items():
            if field == "status" and value == TaskStatus.COMPLETED and task.status != TaskStatus.COMPLETED:
                task.completed_at = datetime.now(timezone.utc)
            elif field == "status" and value != TaskStatus.COMPLETED:
                task.completed_at = None
            setattr(task, field, value)

        task.updated_at = datetime.now(timezone.utc)
        await session.commit()
        return await self.get_task(user_id, session, task_id)

    async def complete_task(
        self, user_id: UUID, session: AsyncSession, task_id: UUID
    ) -> Optional[Task]:
        """
        Mark a task as completed.
        If the task is recurring, automatically spawn the next recurrence!
        """
        task = await self.get_task(user_id, session, task_id)
        if not task:
            return None

        task.status = TaskStatus.COMPLETED
        task.completed_at = datetime.now(timezone.utc)
        task.updated_at = datetime.now(timezone.utc)

        # Cancel any pending reminders on this completed task
        stmt_cancel = (
            select(TaskReminder)
            .where(
                TaskReminder.task_id == task.id,
                TaskReminder.status == ReminderStatus.SCHEDULED,
            )
        )
        rem_res = await session.execute(stmt_cancel)
        for rem in rem_res.scalars().all():
            rem.status = ReminderStatus.CANCELLED

        # Handle recurring generation for next occurrence
        if task.is_recurring and task.recurrence_rule:
            next_due_date = self._compute_next_recurrence_date(
                base_date=task.due_date or datetime.now(timezone.utc).date(),
                rule=task.recurrence_rule,
            )
            if next_due_date:
                next_task = Task(
                    user_id=task.user_id,
                    category_id=task.category_id,
                    title=task.title,
                    description=task.description,
                    due_date=next_due_date,
                    due_time=task.due_time,
                    estimated_duration=task.estimated_duration,
                    priority=task.priority,
                    status=TaskStatus.PENDING,
                    tags=task.tags,
                    is_recurring=True,
                    recurrence_rule=task.recurrence_rule,
                )
                session.add(next_task)
                logger.info(
                    "Generated next recurring task for '%s' on %s (rule=%s)",
                    task.title,
                    next_due_date,
                    task.recurrence_rule,
                )

        await session.commit()
        return await self.get_task(user_id, session, task_id)

    async def reopen_task(
        self, user_id: UUID, session: AsyncSession, task_id: UUID
    ) -> Optional[Task]:
        """Reopen a completed or cancelled task back to pending."""
        task = await self.get_task(user_id, session, task_id)
        if not task:
            return None

        task.status = TaskStatus.PENDING
        task.completed_at = None
        task.updated_at = datetime.now(timezone.utc)
        await session.commit()
        return await self.get_task(user_id, session, task_id)

    async def delete_task(
        self, user_id: UUID, session: AsyncSession, task_id: UUID
    ) -> bool:
        """Delete a task and its associated reminders."""
        task = await self.get_task(user_id, session, task_id)
        if not task:
            return False

        await session.delete(task)
        await session.commit()
        return True

    def _compute_next_recurrence_date(self, base_date: date, rule: str) -> Optional[date]:
        """Compute the next occurrence date based on recurrence rule."""
        clean_rule = rule.lower().strip()
        if clean_rule == "daily":
            return base_date + timedelta(days=1)
        elif clean_rule == "weekdays":
            next_date = base_date + timedelta(days=1)
            # Monday=0, Friday=4, Saturday=5, Sunday=6
            while next_date.weekday() >= 5:
                next_date += timedelta(days=1)
            return next_date
        elif clean_rule == "weekly":
            return base_date + timedelta(weeks=1)
        elif clean_rule == "monthly":
            # Rough 30-day month advance
            year = base_date.year + (base_date.month // 12)
            month = (base_date.month % 12) + 1
            day = min(base_date.day, 28)
            try:
                return date(year, month, day)
            except Exception:
                return base_date + timedelta(days=30)
        else:
            return base_date + timedelta(days=1)
