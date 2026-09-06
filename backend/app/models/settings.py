from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, Enum, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import ConversationMode
from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.conversation import User


class UserSettings(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "user_settings"

    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    display_name: Mapped[str] = mapped_column(String(100), nullable=False, default="Developer", server_default="Developer")
    theme: Mapped[str] = mapped_column(String(20), nullable=False, default="dark", server_default="dark")
    language: Mapped[str] = mapped_column(String(20), nullable=False, default="en", server_default="en")
    default_mode: Mapped[ConversationMode] = mapped_column(
        Enum(ConversationMode, name="conversation_mode", values_callable=lambda enum: [item.value for item in enum]),
        nullable=False,
        default=ConversationMode.NORMAL,
        server_default="normal",
    )
    chat_density: Mapped[str] = mapped_column(String(20), nullable=False, default="comfortable", server_default="comfortable")
    animations_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    enter_to_send: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    streaming_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    show_timestamps: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    auto_scroll: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    compact_messages: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    show_citations: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    show_attachment_previews: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    smart_memory_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    explicit_memory_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    default_retrieval_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="hybrid", server_default="hybrid")
    rag_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    document_context_scope: Mapped[str] = mapped_column(String(20), nullable=False, default="project", server_default="project")
    tool_preferences: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    crag_debug_mode: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    show_crag_pipeline: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    detailed_streaming_events: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")

    user: Mapped["User"] = relationship("User", back_populates="settings")

    __table_args__ = (
        Index("ix_user_settings_user_id", "user_id"),
    )
