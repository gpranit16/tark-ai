from abc import ABC, abstractmethod

from app.schemas.retrieval import RetrievalResult


class BaseReranker(ABC):
    """Abstract base class for all reranker implementations.

    Reranking happens AFTER hybrid retrieval. Takes a query and a list of
    retrieved chunks, returns a reranked subset with updated similarity scores.
    """

    @abstractmethod
    async def rerank(
        self,
        query: str,
        chunks: list[RetrievalResult],
        top_k: int | None = None,
    ) -> list[RetrievalResult]:
        """Rerank retrieved chunks for the given query.

        Args:
            query: The search query string.
            chunks: Retrieved chunks from hybrid retrieval.
            top_k: Number of top chunks to return after reranking.

        Returns:
            Reranked list of RetrievalResult, highest score first,
            limited to top_k entries. All original metadata preserved.
        """
        ...
