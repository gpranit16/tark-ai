import asyncio
import time
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.schemas.retrieval import RetrievalResult
from app.services.retrieval.keyword import KeywordRetriever
from app.services.retrieval.vector import VectorRetriever

# In-memory scoped cache: (user_id, project_id, file_ids_key, query_key, limit) -> (timestamp, list[RetrievalResult])
_RETRIEVAL_CACHE: dict[tuple, tuple[float, list[RetrievalResult]]] = {}
_CACHE_TTL_SECONDS = 60.0
_MAX_CACHE_SIZE = 500


def clear_retrieval_cache() -> None:
    """Clear the retrieval cache (used in tests/maintenance)."""
    _RETRIEVAL_CACHE.clear()


class HybridRetriever:
    def __init__(
        self,
        vector_retriever: VectorRetriever | None = None,
        keyword_retriever: KeywordRetriever | None = None,
    ):
        self.vector_retriever = vector_retriever or VectorRetriever()
        self.keyword_retriever = keyword_retriever or KeywordRetriever()

    async def search(
        self,
        session: AsyncSession,
        query: str,
        user_id: UUID,
        project_id: UUID | None = None,
        file_ids: list[UUID] | None = None,
        top_k: int | None = None,
        vector_weight: float | None = None,
        keyword_weight: float | None = None,
        use_cache: bool = True,
    ) -> list[RetrievalResult]:
        settings = get_settings()
        limit = top_k or settings.rag_top_k or settings.default_top_k
        v_weight = vector_weight if vector_weight is not None else settings.vector_search_weight
        k_weight = keyword_weight if keyword_weight is not None else settings.keyword_search_weight

        norm_query = query.strip().lower()
        if not norm_query:
            return []

        # Scoped cache check: strictly scoped by user_id and project_id for security isolation
        file_ids_key = tuple(sorted(str(f) for f in file_ids)) if file_ids else ()
        cache_key = (str(user_id), str(project_id) if project_id else None, file_ids_key, norm_query, limit)

        now = time.time()
        if use_cache and cache_key in _RETRIEVAL_CACHE:
            ts, cached_results = _RETRIEVAL_CACHE[cache_key]
            if now - ts < _CACHE_TTL_SECONDS:
                # Return deep copy of results to prevent mutation
                return [
                    RetrievalResult(
                        chunk_id=r.chunk_id,
                        file_id=r.file_id,
                        project_id=r.project_id,
                        content=r.content,
                        page_number=r.page_number,
                        chunk_index=r.chunk_index,
                        similarity_score=r.similarity_score,
                        metadata=dict(r.metadata),
                    )
                    for r in cached_results
                ]

        # Execute vector and keyword retrieval concurrently with bounded timeouts
        timeout = settings.rag_retrieval_timeout

        async def _run_vector():
            try:
                return await asyncio.wait_for(
                    self.vector_retriever.search(
                        session, query, user_id, project_id, file_ids, top_k=limit * 2
                    ),
                    timeout=timeout,
                )
            except Exception:
                return []

        async def _run_keyword():
            try:
                return await asyncio.wait_for(
                    self.keyword_retriever.search(
                        session, query, user_id, project_id, file_ids, top_k=limit * 2
                    ),
                    timeout=timeout,
                )
            except Exception:
                return []

        vector_results, keyword_results = await asyncio.gather(_run_vector(), _run_keyword())

        merged_dict: dict[UUID, RetrievalResult] = {}
        scores_dict: dict[UUID, float] = {}

        for item in vector_results:
            merged_dict[item.chunk_id] = item
            scores_dict[item.chunk_id] = item.similarity_score

        for item in keyword_results:
            k_score = item.similarity_score
            if item.chunk_id in scores_dict:
                # Strong Agreement: chunk matched BOTH semantic vector and lexical keyword search!
                base_score = max(scores_dict[item.chunk_id], k_score)
                scores_dict[item.chunk_id] = min(1.0, base_score + 0.10)
            else:
                merged_dict[item.chunk_id] = item
                scores_dict[item.chunk_id] = min(0.70, k_score)

        # Update combined score in retrieval results
        ranked_items: list[RetrievalResult] = []
        for chunk_id, combined_score in sorted(
            scores_dict.items(), key=lambda kv: kv[1], reverse=True
        ):
            res = merged_dict[chunk_id]
            res.similarity_score = round(min(1.0, combined_score), 4)
            ranked_items.append(res)
            if len(ranked_items) >= limit:
                break

        # Save to scoped cache if we have results
        if use_cache and ranked_items:
            if len(_RETRIEVAL_CACHE) >= _MAX_CACHE_SIZE:
                # Evict oldest 20%
                sorted_keys = sorted(_RETRIEVAL_CACHE.keys(), key=lambda k: _RETRIEVAL_CACHE[k][0])
                for k in sorted_keys[: len(sorted_keys) // 5]:
                    _RETRIEVAL_CACHE.pop(k, None)
            _RETRIEVAL_CACHE[cache_key] = (now, ranked_items)

        return ranked_items
