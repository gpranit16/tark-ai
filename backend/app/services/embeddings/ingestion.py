import asyncio
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.models.chunk import DocumentChunk
from app.models.document import ParsedDocument
from app.models.file import File
from app.schemas.document import ParsedDocumentData
from app.schemas.retrieval import IngestionStatusResponse
from app.services.chunking.document_chunker import DocumentChunker
from app.services.embeddings.factory import get_embedding_provider


class EmbeddingIngestionService:
    def __init__(self, chunker: DocumentChunker | None = None):
        self.chunker = chunker or DocumentChunker()

    async def ingest_file(
        self, session: AsyncSession, file_id: UUID, user_id: UUID
    ) -> IngestionStatusResponse:
        # 1. Ownership & File validation
        file_stmt = select(File).where(File.id == file_id, File.user_id == user_id)
        file_res = await session.execute(file_stmt)
        db_file = file_res.scalar_one_or_none()
        if not db_file:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found or access denied."
            )

        # 2. ParsedDocument validation
        doc_stmt = select(ParsedDocument).where(
            ParsedDocument.file_id == file_id, ParsedDocument.user_id == user_id
        )
        doc_res = await session.execute(doc_stmt)
        parsed_doc = doc_res.scalar_one_or_none()
        if not parsed_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Parsed document not found. Ensure document parsing is complete."
            )

        if parsed_doc.status != "completed" or not parsed_doc.parsed_content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot ingest document with parsing status '{parsed_doc.status}'."
            )

        try:
            # 3. Construct ParsedDocumentData schema
            doc_data = ParsedDocumentData.model_validate(parsed_doc.parsed_content)

            # 4. Chunk Document
            raw_chunks = self.chunker.chunk_document(doc_data)
            if not raw_chunks:
                # Handle empty doc gracefully
                return IngestionStatusResponse(
                    file_id=file_id,
                    status="completed",
                    chunk_count=0,
                    failure_reason=None,
                )

            # 5. Generate Embeddings using configured provider
            texts = [c["content"] for c in raw_chunks]
            provider = get_embedding_provider()
            embeddings = await provider.embed_documents(texts)

            if len(embeddings) != len(raw_chunks):
                raise RuntimeError(
                    f"Embedding count mismatch: expected {len(raw_chunks)}, got {len(embeddings)}"
                )

            # 6. Idempotently write chunks + embeddings to database
            # Clear old chunks for this file
            await session.execute(
                delete(DocumentChunk).where(DocumentChunk.file_id == file_id)
            )

            # Insert new chunks
            for raw_chunk, emb in zip(raw_chunks, embeddings):
                db_chunk = DocumentChunk(
                    file_id=file_id,
                    user_id=user_id,
                    project_id=db_file.project_id,
                    parsed_document_id=parsed_doc.id,
                    chunk_index=raw_chunk["chunk_index"],
                    content=raw_chunk["content"],
                    page_number=raw_chunk["page_number"],
                    metadata_=raw_chunk.get("metadata", {}),
                    embedding=emb,
                )
                session.add(db_chunk)

            await session.commit()

            return IngestionStatusResponse(
                file_id=file_id,
                status="completed",
                chunk_count=len(raw_chunks),
                failure_reason=None,
            )

        except Exception as e:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Embedding ingestion failed: {str(e)}"
            )

    async def get_ingestion_status(
        self, session: AsyncSession, file_id: UUID, user_id: UUID
    ) -> IngestionStatusResponse:
        # Validate file ownership
        file_stmt = select(File).where(File.id == file_id, File.user_id == user_id)
        file_res = await session.execute(file_stmt)
        db_file = file_res.scalar_one_or_none()
        if not db_file:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found or access denied."
            )

        count_stmt = select(func.count(DocumentChunk.id)).where(
            DocumentChunk.file_id == file_id, DocumentChunk.user_id == user_id
        )
        count_res = await session.execute(count_stmt)
        chunk_count = count_res.scalar() or 0

        current_status = "completed" if chunk_count > 0 else "pending"

        return IngestionStatusResponse(
            file_id=file_id,
            status=current_status,
            chunk_count=chunk_count,
            failure_reason=None,
        )

    async def retry_ingestion(
        self, session: AsyncSession, file_id: UUID, user_id: UUID
    ) -> IngestionStatusResponse:
        return await self.ingest_file(session, file_id, user_id)
