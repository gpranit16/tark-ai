from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship, backref

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ParsedDocument(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "parsed_documents"

    file_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("files.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="pending",
        index=True,
    )  # pending, processing, completed, failed
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    parsed_content: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    word_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ocr_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    file = relationship("File", backref=backref("parsed_document", uselist=False, cascade="all, delete-orphan", passive_deletes=True))
    user = relationship("User")

    __table_args__ = (
        Index("ix_parsed_documents_user_status", "user_id", "status"),
    )
