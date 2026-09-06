from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class FileResponse(BaseModel):
    id: UUID
    original_filename: str
    mime_type: str
    extension: str
    size_bytes: int
    project_id: UUID | None
    project_name: str | None = None
    storage_provider: str
    status: str
    parse_status: str | None = None
    page_count: int | None = None
    word_count: int | None = None
    failure_reason: str | None = None
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)



class FileCreate(BaseModel):
    user_id: UUID
    project_id: UUID | None = None
    storage_provider: str | None = None


class StorageStatsResponse(BaseModel):
    total_files: int
    local_files: int
    b2_files: int
    total_size_bytes: int
    local_size_bytes: int
    b2_size_bytes: int
    ready_count: int
    processing_count: int
    failed_count: int
