import asyncio
from typing import Any

from app.core.config import get_settings
from app.services.embeddings.base import BaseEmbeddingProvider


import threading

_EMBEDDING_MODEL_CACHE: dict[str, Any] = {}
_CACHE_LOCK = threading.Lock()


class LocalBGEEmbeddingProvider(BaseEmbeddingProvider):
    def __init__(self, model_name: str | None = None, dimension: int | None = None):
        settings = get_settings()
        self._model_name = model_name or settings.embedding_model
        self._dimension = dimension or settings.embedding_dimension

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        return self._dimension

    def _get_model(self) -> Any:
        if self._model_name not in _EMBEDDING_MODEL_CACHE:
            with _CACHE_LOCK:
                if self._model_name not in _EMBEDDING_MODEL_CACHE:
                    try:
                        from sentence_transformers import SentenceTransformer
                        _EMBEDDING_MODEL_CACHE[self._model_name] = SentenceTransformer(self._model_name)
                    except Exception as e:
                        raise RuntimeError(
                            f"Failed to initialize embedding model '{self._model_name}': {e}"
                        )
        return _EMBEDDING_MODEL_CACHE[self._model_name]

    def _encode_sync(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        model = self._get_model()
        embeddings = model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
            batch_size=32,
        )
        return [vec.tolist() for vec in embeddings]

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return await asyncio.to_thread(self._encode_sync, texts)

    async def embed_query(self, text: str) -> list[float]:
        # BGE models require query instruction prefix for asymmetrical retrieval
        prefix = "Represent this sentence for searching relevant passages: "
        query_text = f"{prefix}{text.strip()}" if not text.strip().startswith(prefix) else text.strip()
        results = await self.embed_documents([query_text])
        if not results:
            return [0.0] * self._dimension
        return results[0]
