import enum
import uuid
from datetime import date, datetime, time, timezone
from typing import Any, List, Optional

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Time,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import relationship

from app.db.base import Base


class TaskPriority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ReminderStatus(str, enum.Enum):
    SCHEDULED = "scheduled"
    SENT = "sent"
    CANCELLED = "cancelled"
    FAILED = "failed"


class TaskCategory(Base):
    __tablename__ = "task_categories"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(64), nullable=False)
    color = Column(String(32), nullable=True, default="#D6B56A")
    icon = Column(String(32), nullable=True, default="tag")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    tasks = relationship("Task", back_populates="category_rel", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_task_categories_user_name", "user_id", "name", unique=True),
    )


class Task(Base):
    __tablename__ = "tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    category_id = Column(UUID(as_uuid=True), ForeignKey("task_categories.id", ondelete="SET NULL"), nullable=True, index=True)
    
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    
    due_date = Column(Date, nullable=True, index=True)
    due_time = Column(Time, nullable=True)
    estimated_duration = Column(Integer, nullable=True)  # in minutes (e.g. 15, 30, 45, 60, 90)
    
    priority = Column(
        Enum(TaskPriority, name="task_priority", values_callable=lambda x: [e.value for e in x]),
        default=TaskPriority.MEDIUM,
        nullable=False,
        index=True,
    )
    status = Column(
        Enum(TaskStatus, name="task_status", values_callable=lambda x: [e.value for e in x]),
        default=TaskStatus.PENDING,
        nullable=False,
        index=True,
    )
    
    tags = Column(JSON, nullable=True, default=list)
    
    is_recurring = Column(Boolean, default=False, nullable=False)
    recurrence_rule = Column(String(64), nullable=True)  # daily, weekly, monthly, weekdays
    
    calendar_event_id = Column(String(255), nullable=True)
    synced_to_calendar = Column(Boolean, default=False, nullable=False)
    
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    category_rel = relationship("TaskCategory", back_populates="tasks")
    reminders = relationship("TaskReminder", back_populates="task", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_tasks_user_status", "user_id", "status"),
        Index("ix_tasks_user_due_date", "user_id", "due_date"),
        Index("ix_tasks_user_priority", "user_id", "priority"),
    )


class TaskReminder(Base):
    __tablename__ = "task_reminders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    task_id = Column(UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=True, index=True)
    
    title = Column(String(255), nullable=False)
    reminder_time = Column(DateTime(timezone=True), nullable=False, index=True)
    
    status = Column(
        Enum(ReminderStatus, name="reminder_status", values_callable=lambda x: [e.value for e in x]),
        default=ReminderStatus.SCHEDULED,
        nullable=False,
        index=True,
    )
    delivery_channel = Column(String(32), default="in_app", nullable=False)
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    task = relationship("Task", back_populates="reminders")

    __table_args__ = (
        Index("ix_task_reminders_user_status_time", "user_id", "status", "reminder_time"),
        Index("ix_task_reminders_due_poll", "status", "reminder_time"),
    )
