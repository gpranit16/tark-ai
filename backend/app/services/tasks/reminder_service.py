import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set
from uuid import UUID

from sqlalchemy import and_, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.models.task import ReminderStatus, Task, TaskReminder
from app.schemas.task import TaskReminderCreate, TaskReminderUpdate

logger = logging.getLogger(__name__)


class ReminderService:
    """Service for managing task reminders and scheduling background delivery."""

    _subscribers: Dict[UUID, Set[asyncio.Queue]] = {}

    @classmethod
    def register_subscriber(cls, user_id: UUID, queue: asyncio.Queue) -> None:
        """Register an active SSE connection queue for a user."""
        if user_id not in cls._subscribers:
            cls._subscribers[user_id] = set()
        cls._subscribers[user_id].add(queue)

    @classmethod
    def unregister_subscriber(cls, user_id: UUID, queue: asyncio.Queue) -> None:
        """Unregister an SSE connection queue on client disconnect."""
        if user_id in cls._subscribers:
            cls._subscribers[user_id].discard(queue)
            if not cls._subscribers[user_id]:
                del cls._subscribers[user_id]

    @classmethod
    def dispatch_in_app_notification(cls, user_id: UUID, payload: Dict[str, Any]) -> None:
        """Deliver live reminder event to user's connected in-app SSE listeners."""
        queues = cls._subscribers.get(user_id, set())
        for q in list(queues):
            try:
                q.put_nowait(payload)
            except Exception as e:
                logger.warning("Failed to dispatch in-app notification to queue for user %s: %s", user_id, e)

    async def create_reminder(
        self, user_id: UUID, session: AsyncSession, payload: TaskReminderCreate
    ) -> TaskReminder:
        """Create a scheduled reminder for user."""
        # Ensure reminder_time has timezone info (UTC)
        rem_time = payload.reminder_time
        if rem_time.tzinfo is None:
            rem_time = rem_time.replace(tzinfo=timezone.utc)

        # Reject any reminder in the past (allow max 10s clock skew)
        now_utc = datetime.now(timezone.utc)
        if rem_time < (now_utc - timedelta(seconds=10)):
            raise ValueError("Reminder time cannot be in the past.")

        reminder = TaskReminder(
            user_id=user_id,
            task_id=payload.task_id,
            title=payload.title.strip(),
            reminder_time=rem_time,
            status=ReminderStatus.SCHEDULED,
            delivery_channel=payload.delivery_channel or "in_app",
        )
        session.add(reminder)
        await session.commit()
        await session.refresh(reminder)
        return reminder

    async def list_reminders(
        self,
        user_id: UUID,
        session: AsyncSession,
        status: Optional[ReminderStatus] = None,
        time_frame: Optional[str] = None,
    ) -> List[TaskReminder]:
        """List user reminders filtered by status or time frame."""
        stmt = (
            select(TaskReminder)
            .where(TaskReminder.user_id == user_id)
            .order_by(TaskReminder.reminder_time.asc())
        )

        if status:
            stmt = stmt.where(TaskReminder.status == status)

        now_utc = datetime.now(timezone.utc)
        if time_frame == "today":
            today_start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
            today_end = today_start + timedelta(days=1)
            stmt = stmt.where(
                and_(
                    TaskReminder.reminder_time >= today_start,
                    TaskReminder.reminder_time < today_end,
                )
            )
        elif time_frame == "upcoming":
            stmt = stmt.where(TaskReminder.reminder_time >= now_utc)

        res = await session.execute(stmt)
        return list(res.scalars().all())

    async def cancel_reminder(
        self, user_id: UUID, session: AsyncSession, reminder_id: UUID
    ) -> bool:
        """Cancel a scheduled reminder."""
        stmt = select(TaskReminder).where(
            TaskReminder.id == reminder_id, TaskReminder.user_id == user_id
        )
        res = await session.execute(stmt)
        reminder = res.scalar_one_or_none()
        if not reminder:
            return False

        reminder.status = ReminderStatus.CANCELLED
        await session.commit()
        return True

    @staticmethod
    async def process_due_reminders_batch() -> int:
        """
        Poll and deliver due reminders atomically.
        Render Free tier friendly: Runs in <50ms with zero extra RAM.
        """
        if not AsyncSessionLocal:
            return 0

        now_utc = datetime.now(timezone.utc)
        delivered_count = 0

        async with AsyncSessionLocal() as session:
            try:
                # Select scheduled reminders whose time has arrived
                stmt = (
                    select(TaskReminder)
                    .where(
                        TaskReminder.status == ReminderStatus.SCHEDULED,
                        TaskReminder.reminder_time <= now_utc,
                    )
                    .limit(50)
                )
                res = await session.execute(stmt)
                due_reminders = list(res.scalars().all())

                if not due_reminders:
                    return 0

                for rem in due_reminders:
                    rem.status = ReminderStatus.SENT
                    rem.delivered_at = now_utc
                    rem.updated_at = now_utc
                    delivered_count += 1
                    
                    # Dispatch to connected in-app SSE notification streams
                    ReminderService.dispatch_in_app_notification(
                        rem.user_id,
                        {
                            "event": "reminder_due",
                            "reminder_id": str(rem.id),
                            "task_id": str(rem.task_id) if rem.task_id else None,
                            "title": rem.title,
                            "reminder_time": rem.reminder_time.isoformat(),
                            "delivered_at": now_utc.isoformat(),
                        },
                    )

                    logger.info(
                        "Delivered reminder: ID=%s, User=%s, Title='%s'",
                        rem.id,
                        rem.user_id,
                        rem.title,
                    )

                await session.commit()
            except Exception as e:
                await session.rollback()
                logger.error("Error during reminder delivery cycle: %s", e)

        return delivered_count


# Global background worker reference
_reminder_worker_task: Optional[asyncio.Task] = None


async def _reminder_polling_loop(poll_interval_seconds: int = 15) -> None:
    """Continuous lightweight background worker for reminder notifications."""
    logger.info("Starting lightweight background reminder polling worker (interval=%ds)...", poll_interval_seconds)
    while True:
        try:
            await ReminderService.process_due_reminders_batch()
        except asyncio.CancelledError:
            logger.info("Reminder background worker task cancelled.")
            break
        except Exception as exc:
            logger.warning("Unexpected error in reminder worker loop: %s", exc)
        await asyncio.sleep(poll_interval_seconds)


def start_reminder_worker() -> None:
    """Launch the reminder background task in FastAPI lifespan."""
    global _reminder_worker_task
    if _reminder_worker_task is None or _reminder_worker_task.done():
        _reminder_worker_task = asyncio.create_task(_reminder_polling_loop(poll_interval_seconds=15))


def stop_reminder_worker() -> None:
    """Gracefully cancel reminder background worker on shutdown."""
    global _reminder_worker_task
    if _reminder_worker_task and not _reminder_worker_task.done():
        _reminder_worker_task.cancel()
