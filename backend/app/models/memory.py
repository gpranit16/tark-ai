from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import MemoryCategory
from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Memory(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "memories"

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
    category: Mapped[MemoryCategory] = mapped_column(
        Enum(MemoryCategory, name="memory_category", values_callable=lambda enum: [item.value for item in enum]),
        nullable=False,
        default=MemoryCategory.OTHER,
        index=True,
    )
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(255), nullable=False, default="conversation")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    importance: Mapped[float] = mapped_column(Float, nullable=False, default=0.7)
    last_accessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)

    user = relationship("User", back_populates="memories")
    project = relationship("Project", back_populates="memories")

    __table_args__ = (
        Index("ix_memories_user_active_updated", "user_id", "is_active", "updated_at"),
        Index("ix_memories_user_project_active", "user_id", "project_id", "is_active"),
        Index("ix_memories_user_category_active", "user_id", "category", "is_active"),
        Index("ix_memories_user_key", "user_id", "key"),
    )
