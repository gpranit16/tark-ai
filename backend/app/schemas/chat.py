from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.enums import ConversationMode


class ChatRequest(BaseModel):
    content: str = Field(min_length=1)
    provider: str | None = None
    model: str | None = None
    mode: ConversationMode = ConversationMode.NORMAL
    # RAG-specific fields
    file_ids: Optional[List[UUID]] = Field(
        default=None,
        description="File IDs to scope RAG retrieval. Presence signals RAG intent.",
    )
    user_id: Optional[UUID] = Field(
        default=None,
        description="User ID for RAG ownership scoping.",
    )
    is_temporary: Optional[bool] = Field(
        default=False,
        description="Temporary chat mode - disables long-term memory recording.",
    )

