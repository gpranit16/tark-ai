from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.chunk import DocumentChunk
from app.schemas.retrieval import RetrievalResult


class KeywordRetriever:
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

        cleaned_query = query.strip()
        if not cleaned_query:
            return []

        # 1. Primary PostgreSQL full-text search with tsvector and plainto_tsquery
        ts_query = func.plainto_tsquery("english", cleaned_query)
        ts_vector = func.to_tsvector("english", DocumentChunk.content)
        rank_expr = func.ts_rank(ts_vector, ts_query)

        stmt = select(
            DocumentChunk,
            rank_expr.label("rank")
        ).where(
            DocumentChunk.user_id == user_id,
            ts_vector.op("@@")(ts_query)
        )

        if project_id is not None:
            stmt = stmt.where(DocumentChunk.project_id == project_id)

        if file_ids:
            stmt = stmt.where(DocumentChunk.file_id.in_(file_ids))

        stmt = stmt.order_by(rank_expr.desc()).limit(limit)

        result = await session.execute(stmt)
        rows = result.all()

        # 2. Fallback: If full-text returns 0 results, try ILIKE substring matching
        if not rows:
            words = [w for w in cleaned_query.split() if len(w) > 1]
            if words:
                ilike_filters = [DocumentChunk.content.ilike(f"%{w}%") for w in words]
                fallback_stmt = select(DocumentChunk).where(
                    DocumentChunk.user_id == user_id,
                    or_(*ilike_filters)
                )
                if project_id is not None:
                    fallback_stmt = fallback_stmt.where(DocumentChunk.project_id == project_id)
                if file_ids:
                    fallback_stmt = fallback_stmt.where(DocumentChunk.file_id.in_(file_ids))

                fallback_stmt = fallback_stmt.limit(limit)
                fb_result = await session.execute(fallback_stmt)
                fb_rows = fb_result.scalars().all()
                rows = [(chunk, 0.5) for chunk in fb_rows]

        results: list[RetrievalResult] = []
        for chunk, rank in rows:
            # Calibrate ts_rank (typically 0.02 - 0.30) without dividing by single-item max
            raw_rank = float(rank)
            if raw_rank <= 0.30 and len(rows) > 0 and isinstance(rank, float) and rank == 0.2: # fallback marker
                normalized_score = 0.20
            else:
                normalized_score = min(0.85, max(0.10, raw_rank * 2.5))
            results.append(
                RetrievalResult(
                    chunk_id=chunk.id,
                    file_id=chunk.file_id,
                    project_id=chunk.project_id,
                    content=chunk.content,
                    page_number=chunk.page_number,
                    chunk_index=chunk.chunk_index,
                    similarity_score=round(normalized_score, 4),
                    metadata=chunk.metadata_ or {},
                )
            )

        return results
