"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-08-31 00:00:00.000000
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


conversation_mode = postgresql.ENUM(
    "fast",
    "normal",
    "reasoning",
    "rag",
    "deep_research",
    "coding",
    name="conversation_mode",
    create_type=False,
)
message_role = postgresql.ENUM(
    "system",
    "user",
    "assistant",
    "tool",
    name="message_role",
    create_type=False,
)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    conversation_mode.create(op.get_bind(), checkfirst=True)
    message_role.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_created_at"), "users", ["created_at"], unique=False)

    op.create_table(
        "projects",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_projects_created_at"), "projects", ["created_at"], unique=False)
    op.create_index(op.f("ix_projects_user_id"), "projects", ["user_id"], unique=False)
    op.create_index("ix_projects_user_created_at", "projects", ["user_id", "created_at"], unique=False)

    op.create_table(
        "threads",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("default_mode", conversation_mode, nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_threads_created_at"), "threads", ["created_at"], unique=False)
    op.create_index(op.f("ix_threads_project_id"), "threads", ["project_id"], unique=False)
    op.create_index(op.f("ix_threads_user_id"), "threads", ["user_id"], unique=False)
    op.create_index("ix_threads_project_updated_at", "threads", ["project_id", "updated_at"], unique=False)
    op.create_index("ix_threads_user_updated_at", "threads", ["user_id", "updated_at"], unique=False)

    op.create_table(
        "messages",
        sa.Column("thread_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parent_message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("role", message_role, nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=True),
        sa.Column("mode", conversation_mode, nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["parent_message_id"], ["messages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["thread_id"], ["threads.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_messages_created_at"), "messages", ["created_at"], unique=False)
    op.create_index(op.f("ix_messages_parent_message_id"), "messages", ["parent_message_id"], unique=False)
    op.create_index(op.f("ix_messages_thread_id"), "messages", ["thread_id"], unique=False)
    op.create_index("ix_messages_parent_created_at", "messages", ["parent_message_id", "created_at"], unique=False)
    op.create_index("ix_messages_thread_created_at", "messages", ["thread_id", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_messages_thread_created_at", table_name="messages")
    op.drop_index("ix_messages_parent_created_at", table_name="messages")
    op.drop_index(op.f("ix_messages_thread_id"), table_name="messages")
    op.drop_index(op.f("ix_messages_parent_message_id"), table_name="messages")
    op.drop_index(op.f("ix_messages_created_at"), table_name="messages")
    op.drop_table("messages")
    op.drop_index("ix_threads_user_updated_at", table_name="threads")
    op.drop_index("ix_threads_project_updated_at", table_name="threads")
    op.drop_index(op.f("ix_threads_user_id"), table_name="threads")
    op.drop_index(op.f("ix_threads_project_id"), table_name="threads")
    op.drop_index(op.f("ix_threads_created_at"), table_name="threads")
    op.drop_table("threads")
    op.drop_index("ix_projects_user_created_at", table_name="projects")
    op.drop_index(op.f("ix_projects_user_id"), table_name="projects")
    op.drop_index(op.f("ix_projects_created_at"), table_name="projects")
    op.drop_table("projects")
    op.drop_index(op.f("ix_users_created_at"), table_name="users")
    op.drop_table("users")
    message_role.drop(op.get_bind(), checkfirst=True)
    conversation_mode.drop(op.get_bind(), checkfirst=True)
