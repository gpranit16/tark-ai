from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.chunk import DocumentChunk
from app.schemas.retrieval import RetrievalResult
from app.services.embeddings.factory import get_embedding_provider


class VectorRetriever:
    async def search(
        self,
        session: AsyncSession,
        query: str,
        user_id: UUID,
        project_id: UUID | None = None,
        file_ids: list[UUID] | None = None,
        top_k: int | None = None,
    ) -> list[RetrievalResult]:
        settings = get_settings()
        limit = top_k or settings.default_top_k

        if not query.strip():
            return []

        provider = get_embedding_provider()
        query_vector = await provider.embed_query(query.strip())

        # Cosine distance expression using pgvector
        distance_expr = DocumentChunk.embedding.cosine_distance(query_vector)

        stmt = select(
            DocumentChunk,
            distance_expr.label("distance")
        ).where(
            DocumentChunk.user_id == user_id
        )

        if project_id is not None:
            stmt = stmt.where(DocumentChunk.project_id == project_id)

        if file_ids:
            stmt = stmt.where(DocumentChunk.file_id.in_(file_ids))

        stmt = stmt.order_by(distance_expr.asc()).limit(limit)

        result = await session.execute(stmt)
        rows = result.all()

        results: list[RetrievalResult] = []
        for chunk, distance in rows:
            # Cosine similarity is 1.0 - cosine distance
            score = max(0.0, min(1.0, 1.0 - float(distance)))
            results.append(
                RetrievalResult(
                    chunk_id=chunk.id,
                    file_id=chunk.file_id,
                    project_id=chunk.project_id,
                    content=chunk.content,
                    page_number=chunk.page_number,
                    chunk_index=chunk.chunk_index,
                    similarity_score=round(score, 4),
                    metadata=chunk.metadata_ or {},
                )
            )

        return results
