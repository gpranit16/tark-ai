from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import ConversationMode, MessageRole


class MessageCreate(BaseModel):
    role: MessageRole
    content: str = Field(min_length=1)
    parent_message_id: UUID | None = None
    model: str | None = Field(default=None, max_length=255)
    mode: ConversationMode = ConversationMode.NORMAL


class MessageResponse(BaseModel):
    id: UUID
    thread_id: UUID
    parent_message_id: UUID | None = None
    role: str | MessageRole
    content: str
    model: str | None = None
    provider: str | None = None
    mode: str | ConversationMode = ConversationMode.NORMAL
    generation_status: str | None = None
    attachments: list[dict] | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    latency_ms: int | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
