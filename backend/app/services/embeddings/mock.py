import hashlib
import math
from app.core.config import get_settings
from app.services.embeddings.base import BaseEmbeddingProvider


class MockEmbeddingProvider(BaseEmbeddingProvider):
    def __init__(self, dimension: int | None = None):
        settings = get_settings()
        self._dimension = dimension or settings.embedding_dimension

    @property
    def model_name(self) -> str:
        return "mock-bge-m3"

    @property
    def dimension(self) -> int:
        return self._dimension

    def _generate_vector(self, text: str) -> list[float]:
        # Generate a deterministic pseudo-random normalized vector from text hash
        hash_bytes = hashlib.sha256(text.encode("utf-8")).digest()
        vec = []
        for i in range(self._dimension):
            byte_val = hash_bytes[i % len(hash_bytes)]
            val = (byte_val / 255.0) * 2.0 - 1.0
            vec.append(val)

        # L2 normalize
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._generate_vector(t) for t in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._generate_vector(text)
