from uuid import UUID

from sqlalchemy import ForeignKey, Index, Integer, String, inspect
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class File(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "files"

    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    extension: Mapped[str] = mapped_column(String(20), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_provider: Mapped[str] = mapped_column(String(50), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False, unique=True, index=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")

    user = relationship("User")
    project = relationship("Project", back_populates="files")

    @property
    def parse_status(self) -> str | None:
        try:
            insp = inspect(self)
            if insp and "parsed_document" in insp.attrs and "parsed_document" not in insp.unloaded:
                pd = self.__dict__.get("parsed_document")
                return pd.status if pd else None
        except Exception:
            pass
        return None

    @property
    def page_count(self) -> int | None:
        try:
            insp = inspect(self)
            if insp and "parsed_document" in insp.attrs and "parsed_document" not in insp.unloaded:
                pd = self.__dict__.get("parsed_document")
                return pd.page_count if pd else None
        except Exception:
            pass
        return None

    @property
    def word_count(self) -> int | None:
        try:
            insp = inspect(self)
            if insp and "parsed_document" in insp.attrs and "parsed_document" not in insp.unloaded:
                pd = self.__dict__.get("parsed_document")
                return pd.word_count if pd else None
        except Exception:
            pass
        return None

    @property
    def failure_reason(self) -> str | None:
        try:
            insp = inspect(self)
            if insp and "parsed_document" in insp.attrs and "parsed_document" not in insp.unloaded:
                pd = self.__dict__.get("parsed_document")
                return pd.failure_reason if pd else None
        except Exception:
            pass
        return None

    @property
    def project_name(self) -> str | None:
        try:
            insp = inspect(self)
            if insp and "project" in insp.attrs and "project" not in insp.unloaded:
                proj = self.__dict__.get("project")
                return proj.name if proj else None
        except Exception:
            pass
        return None

    __table_args__ = (
        Index("ix_files_user_created_at", "user_id", "created_at"),
        Index("ix_files_project_created_at", "project_id", "created_at"),
    )

