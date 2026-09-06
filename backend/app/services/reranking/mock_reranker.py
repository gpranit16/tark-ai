from app.schemas.retrieval import RetrievalResult
from app.services.reranking.base import BaseReranker


class MockReranker(BaseReranker):
    """Mock reranker for tests.

    Returns chunks with slightly modified scores in reverse order
    so tests can detect reranking actually occurred.
    Preserves all metadata fields exactly.
    """

    async def rerank(
        self,
        query: str,
        chunks: list[RetrievalResult],
        top_k: int | None = None,
    ) -> list[RetrievalResult]:
        if not chunks:
            return []

        k = top_k or len(chunks)

        # Assign deterministic scores for testability: reverse original order
        # and assign descending scores starting at 0.95
        results: list[RetrievalResult] = []
        reversed_chunks = list(reversed(chunks))
        for i, chunk in enumerate(reversed_chunks[:k]):
            if chunk.similarity_score < 0.30:
                mock_score = round(max(0.05, chunk.similarity_score), 4)
            else:
                mock_score = round(max(0.1, 0.95 - i * 0.05), 4)
            results.append(
                RetrievalResult(
                    chunk_id=chunk.chunk_id,
                    file_id=chunk.file_id,
                    project_id=chunk.project_id,
                    content=chunk.content,
                    page_number=chunk.page_number,
                    chunk_index=chunk.chunk_index,
                    similarity_score=mock_score,
                    metadata=chunk.metadata,
                )
            )
        return results
