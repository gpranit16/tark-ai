from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.enums import ConversationMode


class UserSettingsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    display_name: str
    theme: str
    language: str
    default_mode: ConversationMode
    chat_density: str
    animations_enabled: bool
    enter_to_send: bool
    streaming_enabled: bool
    show_timestamps: bool
    auto_scroll: bool
    compact_messages: bool
    show_citations: bool
    show_attachment_previews: bool
    smart_memory_enabled: bool
    explicit_memory_enabled: bool
    default_retrieval_mode: str
    rag_enabled: bool
    document_context_scope: str
    tool_preferences: dict[str, bool] = Field(default_factory=dict)
    crag_debug_mode: bool
    show_crag_pipeline: bool
    detailed_streaming_events: bool
    created_at: datetime
    updated_at: datetime


class UserSettingsUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=100)
    theme: str | None = None
    language: str | None = Field(default=None, max_length=20)
    default_mode: ConversationMode | None = None
    chat_density: str | None = None
    animations_enabled: bool | None = None
    enter_to_send: bool | None = None
    streaming_enabled: bool | None = None
    show_timestamps: bool | None = None
    auto_scroll: bool | None = None
    compact_messages: bool | None = None
    show_citations: bool | None = None
    show_attachment_previews: bool | None = None
    smart_memory_enabled: bool | None = None
    explicit_memory_enabled: bool | None = None
    default_retrieval_mode: str | None = None
    rag_enabled: bool | None = None
    document_context_scope: str | None = None
    tool_preferences: dict[str, bool] | None = None
    crag_debug_mode: bool | None = None
    show_crag_pipeline: bool | None = None
    detailed_streaming_events: bool | None = None

    @field_validator("theme")
    @classmethod
    def validate_theme(cls, v: str | None) -> str | None:
        if v is not None and v.lower() not in {"dark", "light", "system"}:
            raise ValueError("Theme must be one of 'dark', 'light', or 'system'")
        return v.lower() if v else None

    @field_validator("chat_density")
    @classmethod
    def validate_density(cls, v: str | None) -> str | None:
        if v is not None and v.lower() not in {"compact", "comfortable", "spacious"}:
            raise ValueError("Chat density must be one of 'compact', 'comfortable', or 'spacious'")
        return v.lower() if v else None

    @field_validator("default_retrieval_mode")
    @classmethod
    def validate_retrieval_mode(cls, v: str | None) -> str | None:
        if v is not None and v.lower() not in {"hybrid", "vector", "keyword"}:
            raise ValueError("Default retrieval mode must be one of 'hybrid', 'vector', or 'keyword'")
        return v.lower() if v else None

    @field_validator("document_context_scope")
    @classmethod
    def validate_scope(cls, v: str | None) -> str | None:
        if v is not None and v.lower() not in {"project", "global_project"}:
            raise ValueError("Document context scope must be one of 'project' or 'global_project'")
        return v.lower() if v else None


class ProviderHealthInfo(BaseModel):
    provider: str
    display_name: str
    status: str  # "available", "configured", "not_configured"
    default_model: str


class ModelModeMapping(BaseModel):
    mode: str
    display_name: str
    provider: str
    model: str
    is_default: bool


class StorageInfo(BaseModel):
    provider: str
    status: str
    documents_count: int
    storage_used_bytes: int
    storage_used_formatted: str
    max_upload_size_bytes: int
    bucket_name: str | None = None


class UserAccountStats(BaseModel):
    user_id: UUID
    display_name: str
    created_at: datetime | None = None
    projects_count: int = 0
    threads_count: int = 0
    memories_count: int = 0
    files_count: int = 0


class ToolSettingInfo(BaseModel):
    name: str
    display_name: str
    description: str
    category: str
    permission: str
    enabled: bool


class SettingsEnvelope(BaseModel):
    settings: UserSettingsRead
    modes: list[ModelModeMapping]
    providers: list[ProviderHealthInfo]
    storage: StorageInfo
    account: UserAccountStats
    tools: list[ToolSettingInfo]
