from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import ConversationMode, GenerationStatus, MessageRole
from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.file import File
    from app.models.memory import Memory
    from app.models.research import ResearchSession
    from app.models.settings import UserSettings


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")

    projects: Mapped[list["Project"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    threads: Mapped[list["Thread"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    memories: Mapped[list["Memory"]] = relationship(
        "Memory",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    settings: Mapped["UserSettings | None"] = relationship(
        "UserSettings",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )
    auth_tokens: Mapped[list["AuthToken"]] = relationship(
        "AuthToken",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class AuthToken(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "auth_tokens"

    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    token_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # "password_reset", "email_verification"
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")

    user: Mapped["User"] = relationship("User", back_populates="auth_tokens")


class Project(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "projects"

    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    custom_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    avatar: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    project_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    user: Mapped[User] = relationship(back_populates="projects")
    threads: Mapped[list["Thread"]] = relationship(
        back_populates="project",
        passive_deletes=True,
    )
    memories: Mapped[list["Memory"]] = relationship(
        "Memory",
        back_populates="project",
        passive_deletes=True,
    )
    files: Mapped[list["File"]] = relationship(
        "File",
        back_populates="project",
        passive_deletes=True,
    )
    research_sessions: Mapped[list["ResearchSession"]] = relationship(
        "ResearchSession",
        back_populates="project",
        passive_deletes=True,
    )

    __table_args__ = (
        Index("ix_projects_user_created_at", "user_id", "created_at"),
        Index("ix_projects_user_archived", "user_id", "is_archived"),
    )


class Thread(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "threads"

    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    default_mode: Mapped[ConversationMode] = mapped_column(
        Enum(ConversationMode, name="conversation_mode", values_callable=lambda enum: [item.value for item in enum]),
        nullable=False,
        default=ConversationMode.NORMAL,
    )
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    summarized_message_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    summary_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_temporary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="threads")
    project: Mapped[Project | None] = relationship(back_populates="threads")
    messages: Mapped[list["Message"]] = relationship(
        back_populates="thread",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Message.created_at",
    )

    __table_args__ = (
        Index("ix_threads_user_updated_at", "user_id", "updated_at"),
        Index("ix_threads_project_updated_at", "project_id", "updated_at"),
        Index("ix_threads_user_archived_pinned", "user_id", "is_archived", "is_pinned", "sort_order"),
    )


class Message(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "messages"

    thread_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("threads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    parent_message_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("messages.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    role: Mapped[MessageRole] = mapped_column(
        Enum(MessageRole, name="message_role", values_callable=lambda enum: [item.value for item in enum]),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    mode: Mapped[ConversationMode] = mapped_column(
        Enum(ConversationMode, name="conversation_mode", values_callable=lambda enum: [item.value for item in enum]),
        nullable=False,
        default=ConversationMode.NORMAL,
    )
    generation_status: Mapped[GenerationStatus | None] = mapped_column(
        Enum(GenerationStatus, name="generation_status", values_callable=lambda enum: [item.value for item in enum]),
        nullable=True,
    )
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    attachments: Mapped[list[dict] | None] = mapped_column(
        JSONB,
        nullable=True,
        default=list,
    )

    thread: Mapped[Thread] = relationship(back_populates="messages")
    parent: Mapped["Message | None"] = relationship(
        remote_side="Message.id",
        back_populates="children",
    )
    children: Mapped[list["Message"]] = relationship(back_populates="parent")

    __table_args__ = (
        Index("ix_messages_thread_created_at", "thread_id", "created_at"),
        Index("ix_messages_parent_created_at", "parent_message_id", "created_at"),
    )
