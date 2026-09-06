import asyncio
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.models.document import ParsedDocument
from app.models.file import File
from app.schemas.document import (
    DocumentMetadataResponse,
    DocumentStatusResponse,
    ParsedDocumentResponse,
)
from app.services.parsers.factory import get_parser_for_extension
from app.storage.factory import get_storage_provider


async def _run_parser_job(file_id: UUID, user_id: UUID) -> None:
    async with AsyncSessionLocal() as session:
        stmt = select(ParsedDocument).where(
            ParsedDocument.file_id == file_id,
            ParsedDocument.user_id == user_id
        )
        res = await session.execute(stmt)
        doc = res.scalar_one_or_none()
        if not doc:
            return

        doc.status = "processing"
        doc.failure_reason = None
        await session.commit()

        file_stmt = select(File).where(File.id == file_id, File.user_id == user_id)
        file_res = await session.execute(file_stmt)
        db_file = file_res.scalar_one_or_none()

        if not db_file:
            doc.status = "failed"
            doc.failure_reason = "Associated file record not found"
            await session.commit()
            return

        try:
            storage = get_storage_provider(db_file.storage_provider)
            content_bytes = await storage.download(db_file.storage_key)
            parser = get_parser_for_extension(db_file.extension)
            
            doc_data, ocr_used = await parser.parse(
                content_bytes,
                file_id=db_file.id,
                filename=db_file.original_filename,
                extension=db_file.extension
            )

            # Calculate word count across pages
            total_words = 0
            for page in doc_data.pages:
                total_words += len(page.text.split())

            doc.parsed_content = doc_data.model_dump(mode="json")
            doc.page_count = len(doc_data.pages)
            doc.word_count = total_words
            doc.ocr_used = ocr_used
            doc.status = "completed"
            doc.failure_reason = None
            await session.commit()

            # Automatically trigger embedding ingestion
            try:
                from app.services.embeddings.ingestion import EmbeddingIngestionService
                ingestion_svc = EmbeddingIngestionService()
                await ingestion_svc.ingest_file(session, file_id, user_id)
            except Exception as ing_err:
                # Ingestion error can be retried via /api/v1/embeddings/retry/{file_id}
                pass

        except Exception as e:
            doc.status = "failed"
            doc.failure_reason = str(e)
            await session.commit()



def dispatch_parse_job(file_id: UUID, user_id: UUID) -> None:
    asyncio.create_task(_run_parser_job(file_id, user_id))


async def create_and_start_parsing(
    session: AsyncSession, file_id: UUID, user_id: UUID
) -> ParsedDocument:
    stmt = select(ParsedDocument).where(
        ParsedDocument.file_id == file_id, ParsedDocument.user_id == user_id
    )
    res = await session.execute(stmt)
    existing = res.scalar_one_or_none()

    if existing:
        existing.status = "pending"
        existing.failure_reason = None
        doc = existing
    else:
        doc = ParsedDocument(
            file_id=file_id,
            user_id=user_id,
            status="pending"
        )
        session.add(doc)

    await session.commit()
    await session.refresh(doc)
    dispatch_parse_job(file_id, user_id)
    return doc


async def get_document_record(
    session: AsyncSession, file_id: UUID, user_id: UUID
) -> ParsedDocument:
    # Ownership verification: ensure file exists and belongs to user
    file_stmt = select(File).where(File.id == file_id, File.user_id == user_id)
    file_res = await session.execute(file_stmt)
    db_file = file_res.scalar_one_or_none()
    if not db_file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found or access denied."
        )

    doc_stmt = select(ParsedDocument).where(
        ParsedDocument.file_id == file_id, ParsedDocument.user_id == user_id
    )
    doc_res = await session.execute(doc_stmt)
    doc = doc_res.scalar_one_or_none()

    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Parsed document not found."
        )
    return doc


async def get_document_status(
    session: AsyncSession, file_id: UUID, user_id: UUID
) -> DocumentStatusResponse:
    doc = await get_document_record(session, file_id, user_id)
    return DocumentStatusResponse(
        file_id=doc.file_id,
        status=doc.status,
        failure_reason=doc.failure_reason,
        page_count=doc.page_count,
        word_count=doc.word_count,
        ocr_used=doc.ocr_used,
        created_at=doc.created_at,
        updated_at=doc.updated_at
    )


async def get_parsed_document(
    session: AsyncSession, file_id: UUID, user_id: UUID
) -> ParsedDocumentResponse:
    doc = await get_document_record(session, file_id, user_id)
    return ParsedDocumentResponse(
        id=doc.id,
        file_id=doc.file_id,
        user_id=doc.user_id,
        status=doc.status,
        failure_reason=doc.failure_reason,
        parsed_content=doc.parsed_content,
        page_count=doc.page_count,
        word_count=doc.word_count,
        ocr_used=doc.ocr_used,
        created_at=doc.created_at,
        updated_at=doc.updated_at
    )


async def get_document_metadata(
    session: AsyncSession, file_id: UUID, user_id: UUID
) -> DocumentMetadataResponse:
    file_stmt = select(File).where(File.id == file_id, File.user_id == user_id)
    file_res = await session.execute(file_stmt)
    db_file = file_res.scalar_one_or_none()
    if not db_file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found or access denied."
        )

    doc = await get_document_record(session, file_id, user_id)
    parsed_meta = (
        doc.parsed_content.get("metadata", {})
        if doc.parsed_content and isinstance(doc.parsed_content, dict)
        else {}
    )

    return DocumentMetadataResponse(
        file_id=doc.file_id,
        filename=db_file.original_filename,
        extension=db_file.extension,
        status=doc.status,
        page_count=doc.page_count,
        word_count=doc.word_count,
        ocr_used=doc.ocr_used,
        metadata=parsed_meta,
        created_at=doc.created_at
    )


async def retry_document_processing(
    session: AsyncSession, file_id: UUID, user_id: UUID
) -> ParsedDocumentResponse:
    doc = await get_document_record(session, file_id, user_id)
    doc.status = "pending"
    doc.failure_reason = None
    await session.commit()
    await session.refresh(doc)
    
    dispatch_parse_job(file_id, user_id)

    return ParsedDocumentResponse(
        id=doc.id,
        file_id=doc.file_id,
        user_id=doc.user_id,
        status=doc.status,
        failure_reason=doc.failure_reason,
        parsed_content=doc.parsed_content,
        page_count=doc.page_count,
        word_count=doc.word_count,
        ocr_used=doc.ocr_used,
        created_at=doc.created_at,
        updated_at=doc.updated_at
    )
