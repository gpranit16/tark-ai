from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import ConversationMode


from typing import Literal

DEV_USER_ID = UUID("00000000-0000-0000-0000-000000000001")


class ThreadCreate(BaseModel):
    user_id: UUID = Field(default=DEV_USER_ID)
    project_id: UUID | None = None
    title: str | None = Field(default=None, max_length=255)
    default_mode: ConversationMode = ConversationMode.NORMAL
    is_temporary: bool = False
    is_pinned: bool = False
    is_archived: bool = False
    sort_order: int = 0


class ThreadUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    default_mode: ConversationMode | None = None
    archived_at: datetime | None = None
    summary: str | None = None
    is_temporary: bool | None = None
    is_pinned: bool | None = None
    is_archived: bool | None = None
    sort_order: int | None = None


class ThreadMoveRequest(BaseModel):
    direction: Literal["up", "down"]


class ThreadResponse(BaseModel):
    id: UUID
    user_id: UUID
    project_id: UUID | None
    title: str | None
    default_mode: ConversationMode
    summary: str | None = None
    summary_updated_at: datetime | None = None
    is_temporary: bool = False
    is_pinned: bool = False
    is_archived: bool = False
    sort_order: int = 0
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None

    model_config = ConfigDict(from_attributes=True)
