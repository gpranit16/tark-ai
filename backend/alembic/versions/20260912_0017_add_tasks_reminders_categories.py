"""Add tasks, task_reminders, and task_categories tables

Revision ID: a7b8c9d0e1f2
Revises: f2a8b9c1d3e5
Create Date: 2026-09-12 00:17:00.000000
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "a7b8c9d0e1f2"
down_revision: str | None = "f2a8b9c1d3e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create Enums if not exist
    task_priority = postgresql.ENUM("low", "medium", "high", "urgent", name="task_priority", create_type=False)
    task_status = postgresql.ENUM("pending", "in_progress", "completed", "cancelled", name="task_status", create_type=False)
    reminder_status = postgresql.ENUM("scheduled", "sent", "cancelled", "failed", name="reminder_status", create_type=False)

    conn = op.get_bind()
    task_priority.create(conn, checkfirst=True)
    task_status.create(conn, checkfirst=True)
    reminder_status.create(conn, checkfirst=True)

    # 2. Create task_categories table
    op.create_table(
        "task_categories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("color", sa.String(length=32), nullable=True, server_default="#D6B56A"),
        sa.Column("icon", sa.String(length=32), nullable=True, server_default="tag"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_task_categories_user_id", "task_categories", ["user_id"])
    op.create_index("ix_task_categories_user_name", "task_categories", ["user_id", "name"], unique=True)

    # 3. Create tasks table
    op.create_table(
        "tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("task_categories.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("due_time", sa.Time(), nullable=True),
        sa.Column("estimated_duration", sa.Integer(), nullable=True),
        sa.Column("priority", task_priority, nullable=False, server_default="medium"),
        sa.Column("status", task_status, nullable=False, server_default="pending"),
        sa.Column("tags", postgresql.JSON(astext_type=sa.Text()), nullable=True, server_default="[]"),
        sa.Column("is_recurring", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("recurrence_rule", sa.String(length=64), nullable=True),
        sa.Column("calendar_event_id", sa.String(length=255), nullable=True),
        sa.Column("synced_to_calendar", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_tasks_user_id", "tasks", ["user_id"])
    op.create_index("ix_tasks_category_id", "tasks", ["category_id"])
    op.create_index("ix_tasks_due_date", "tasks", ["due_date"])
    op.create_index("ix_tasks_priority", "tasks", ["priority"])
    op.create_index("ix_tasks_status", "tasks", ["status"])
    op.create_index("ix_tasks_user_status", "tasks", ["user_id", "status"])
    op.create_index("ix_tasks_user_due_date", "tasks", ["user_id", "due_date"])
    op.create_index("ix_tasks_user_priority", "tasks", ["user_id", "priority"])

    # 4. Create task_reminders table
    op.create_table(
        "task_reminders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("reminder_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", reminder_status, nullable=False, server_default="scheduled"),
        sa.Column("delivery_channel", sa.String(length=32), nullable=False, server_default="in_app"),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_task_reminders_user_id", "task_reminders", ["user_id"])
    op.create_index("ix_task_reminders_task_id", "task_reminders", ["task_id"])
    op.create_index("ix_task_reminders_reminder_time", "task_reminders", ["reminder_time"])
    op.create_index("ix_task_reminders_status", "task_reminders", ["status"])
    op.create_index("ix_task_reminders_user_status_time", "task_reminders", ["user_id", "status", "reminder_time"])
    op.create_index("ix_task_reminders_due_poll", "task_reminders", ["status", "reminder_time"])


def downgrade() -> None:
    op.drop_table("task_reminders")
    op.drop_table("tasks")
    op.drop_table("task_categories")
    
    conn = op.get_bind()
    postgresql.ENUM(name="reminder_status").drop(conn, checkfirst=True)
    postgresql.ENUM(name="task_status").drop(conn, checkfirst=True)
    postgresql.ENUM(name="task_priority").drop(conn, checkfirst=True)
