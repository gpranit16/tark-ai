from abc import ABC, abstractmethod


class BaseEmbeddingProvider(ABC):
    @property
    @abstractmethod
    def model_name(self) -> str:
        """Name of the embedding model."""
        pass

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Vector dimension of the embedding output (e.g. 1024)."""
        pass

    @abstractmethod
    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Generate normalized embeddings for a list of document chunks."""
        pass

    @abstractmethod
    async def embed_query(self, text: str) -> list[float]:
        """Generate a normalized embedding for a single search query."""
        pass
