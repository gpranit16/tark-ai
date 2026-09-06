import re
import uuid
from typing import BinaryIO
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.file import File
from app.schemas.file import FileCreate
from app.storage.factory import get_storage_provider


ALLOWED_EXTENSIONS = {
    ".pdf", ".docx", ".pptx", ".txt", ".md", ".csv", ".xlsx",
    ".png", ".jpg", ".jpeg", ".webp",
    # Code extensions (Phase 12)
    ".py", ".js", ".jsx", ".ts", ".tsx", ".html", ".css", ".json",
    ".sql", ".yaml", ".yml", ".xml", ".java", ".cpp", ".c", ".h",
    ".hpp", ".go", ".rs", ".php", ".sh", ".bash", ".toml", ".ini",
    ".graphql",
}

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "text/plain",
    "text/markdown",
    "text/csv",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "image/png",
    "image/jpeg",
    "image/webp",
    # Code MIME types (Phase 12)
    "application/json",
    "text/javascript",
    "application/javascript",
    "text/x-python",
    "text/html",
    "text/css",
    "text/xml",
    "application/xml",
    "text/yaml",
    "application/x-yaml",
    "text/x-c",
    "text/x-c++",
    "text/x-java-source",
    "text/x-go",
    "text/x-rust",
    "text/x-sql",
    "text/x-sh",
    "application/octet-stream",
}


def sanitize_filename(filename: str) -> str:
    # Keep only alphanumeric and simple punctuation
    name = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', filename)
    return name


ALLOWED_STORAGE_PROVIDERS = {"local", "b2"}


def validate_file(filename: str, mime_type: str, size_bytes: int) -> str:
    settings = get_settings()
    
    if size_bytes > settings.max_upload_size_bytes:
        raise HTTPException(
            status_code=413, 
            detail=f"File too large. Maximum size is {settings.max_upload_size_bytes} bytes."
        )

    ext = "." + filename.split('.')[-1].lower() if '.' in filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file extension: {ext}. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )
        
    # If it's a known code extension or text/plain/octet-stream, accept it
    if mime_type not in ALLOWED_MIME_TYPES and not mime_type.startswith("text/"):
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported MIME type: {mime_type}."
        )

    return ext


async def process_and_upload_file(
    session: AsyncSession, 
    file_stream: BinaryIO, 
    filename: str, 
    mime_type: str, 
    size_bytes: int, 
    user_id: UUID,
    project_id: UUID | None = None,
    storage_provider: str | None = None,
) -> File:
    ext = validate_file(filename, mime_type, size_bytes)
    safe_filename = sanitize_filename(filename)
    unique_id = uuid.uuid4().hex[:8]
    
    project_str = str(project_id) if project_id else "default"
    storage_key = f"users/{str(user_id)}/projects/{project_str}/{unique_id}_{safe_filename}"
    
    # Validate storage provider if explicitly provided
    if storage_provider is not None:
        target_provider = storage_provider.strip().lower()
        if target_provider not in ALLOWED_STORAGE_PROVIDERS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid storage_provider '{storage_provider}'. Allowed values: {', '.join(sorted(ALLOWED_STORAGE_PROVIDERS))}"
            )
    else:
        settings = get_settings()
        target_provider = settings.storage_provider or "local"
    
    provider = get_storage_provider(target_provider)
    
    # 1. Start a database transaction
    db_file = File(
        user_id=user_id,
        project_id=project_id,
        original_filename=filename,
        mime_type=mime_type,
        extension=ext,
        size_bytes=size_bytes,
        storage_provider=provider.provider_name,
        storage_key=storage_key,
        status="uploading"
    )
    session.add(db_file)
    await session.commit()
    await session.refresh(db_file)

    try:
        # 2. Upload to storage
        await provider.upload(file_stream, storage_key, mime_type)
        
        # 3. Mark as active
        db_file.status = "active"
        await session.commit()
        await session.refresh(db_file)
        
        # 4. Start asynchronous document parsing
        from app.services.document_processing import create_and_start_parsing
        await create_and_start_parsing(session, db_file.id, user_id)
        
    except Exception as e:
        # Rollback logic if upload fails
        await session.delete(db_file)
        await session.commit()
        raise HTTPException(status_code=500, detail=f"File upload failed: {str(e)}")
        
    return db_file


from sqlalchemy.orm import selectinload


async def list_files(
    session: AsyncSession,
    user_id: UUID,
    project_id: UUID | None = None,
    storage_provider: str | None = None,
    limit: int = 50,
    offset: int = 0
) -> list[File]:
    stmt = (
        select(File)
        .options(selectinload(File.parsed_document), selectinload(File.project))
        .where(File.user_id == user_id)
        .order_by(File.created_at.desc())
    )
    if project_id:
        stmt = stmt.where(File.project_id == project_id)
    if storage_provider:
        stmt = stmt.where(File.storage_provider == storage_provider.strip().lower())
        
    stmt = stmt.limit(limit).offset(offset)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_storage_stats(
    session: AsyncSession,
    user_id: UUID,
    project_id: UUID | None = None,
) -> dict:
    """Aggregate storage metrics broken down by provider for the user."""
    stmt = (
        select(File)
        .options(selectinload(File.parsed_document))
        .where(File.user_id == user_id)
    )
    if project_id:
        stmt = stmt.where(File.project_id == project_id)
    result = await session.execute(stmt)
    files = list(result.scalars().all())

    total_files = len(files)
    local_files = 0
    b2_files = 0
    total_size_bytes = 0
    local_size_bytes = 0
    b2_size_bytes = 0
    ready_count = 0
    processing_count = 0
    failed_count = 0

    for f in files:
        size = f.size_bytes or 0
        total_size_bytes += size
        prov = (f.storage_provider or "local").lower()
        if prov == "b2":
            b2_files += 1
            b2_size_bytes += size
        else:
            local_files += 1
            local_size_bytes += size

        status = f.parse_status or (f.status if f.status == "active" else "processing")
        if status in ("completed", "ready"):
            ready_count += 1
        elif status == "failed":
            failed_count += 1
        else:
            processing_count += 1

    return {
        "total_files": total_files,
        "local_files": local_files,
        "b2_files": b2_files,
        "total_size_bytes": total_size_bytes,
        "local_size_bytes": local_size_bytes,
        "b2_size_bytes": b2_size_bytes,
        "ready_count": ready_count,
        "processing_count": processing_count,
        "failed_count": failed_count,
    }


async def get_file(session: AsyncSession, file_id: UUID, user_id: UUID) -> File:
    stmt = (
        select(File)
        .options(selectinload(File.parsed_document), selectinload(File.project))
        .where(File.id == file_id, File.user_id == user_id)
    )
    result = await session.execute(stmt)
    db_file = result.scalar_one_or_none()
    
    if not db_file:
        raise HTTPException(status_code=404, detail="File not found or access denied.")
    return db_file



async def delete_file(session: AsyncSession, file_id: UUID, user_id: UUID) -> None:
    db_file = await get_file(session, file_id, user_id)
    
    provider = get_storage_provider(db_file.storage_provider)
    
    # Try deleting from storage first
    try:
        await provider.delete(db_file.storage_key)
    except Exception as e:
        # Even if storage delete fails (e.g. file already gone), we remove DB record to not leave ghost records
        # Log this in a real system.
        pass
        
    await session.delete(db_file)
    await session.commit()
