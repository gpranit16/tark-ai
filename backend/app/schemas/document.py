from datetime import datetime
from typing import Any, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class Block(BaseModel):
    block_type: str = Field(..., description="Type of block: heading, paragraph, list, table, image, code")
    content: str = Field(..., description="Text content of block")
    page_number: int = Field(1, description="Source page or slide number")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional block metadata")


class TableData(BaseModel):
    page_number: int = 1
    headers: List[str] = Field(default_factory=list)
    rows: List[List[str]] = Field(default_factory=list)


class ImageData(BaseModel):
    page_number: int = 1
    image_index: int = 0
    format: str = "png"
    ocr_text: Optional[str] = None
    description: Optional[str] = None


class Page(BaseModel):
    page_number: int = Field(..., description="1-based page or slide number")
    text: str = Field("", description="Full raw text of page")
    blocks: List[Block] = Field(default_factory=list)
    tables: List[TableData] = Field(default_factory=list)
    images: List[ImageData] = Field(default_factory=list)


class ParsedDocumentData(BaseModel):
    file_id: UUID
    filename: str
    extension: str
    pages: List[Page] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    summary: Optional[str] = None


class DocumentStatusResponse(BaseModel):
    file_id: UUID
    status: str  # pending, processing, completed, failed
    failure_reason: Optional[str] = None
    page_count: int = 0
    word_count: int = 0
    ocr_used: bool = False
    created_at: datetime
    updated_at: datetime


class DocumentMetadataResponse(BaseModel):
    file_id: UUID
    filename: str
    extension: str
    status: str
    page_count: int
    word_count: int
    ocr_used: bool
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class ParsedDocumentResponse(BaseModel):
    id: UUID
    file_id: UUID
    user_id: UUID
    status: str
    failure_reason: Optional[str] = None
    parsed_content: Optional[ParsedDocumentData] = None
    page_count: int
    word_count: int
    ocr_used: bool
    created_at: datetime
    updated_at: datetime
