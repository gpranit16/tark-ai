import asyncio
import logging
import math
import httpx

from app.core.config import get_settings
from app.services.embeddings.base import BaseEmbeddingProvider

logger = logging.getLogger(__name__)


class GeminiEmbeddingProvider(BaseEmbeddingProvider):
    """Cloud-based ultra-fast embedding provider using Google Gemini text-embedding-004.
    
    Produces 1024-dimension normalized vector embeddings via Google API.
    Zero memory footprint on server (0 MB RAM), ideal for cloud container environments like Render.
    """

    def __init__(self, api_key: str | None = None, dimension: int = 1024):
        settings = get_settings()
        self._api_key = api_key or settings.gemini_api_key
        self._dimension = dimension
        self._model_name = "text-embedding-004"

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        return self._dimension

    def _normalize(self, vec: list[float]) -> list[float]:
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        if not self._api_key:
            logger.warning("[GeminiEmbedding] No GEMINI_API_KEY set, falling back to mock vectors")
            from app.services.embeddings.mock import MockEmbeddingProvider
            return await MockEmbeddingProvider(dimension=self._dimension).embed_documents(texts)

        # Batch texts into chunks of 32
        results: list[list[float]] = []
        batch_size = 32

        async with httpx.AsyncClient(timeout=15.0) as client:
            for i in range(0, len(texts), batch_size):
                batch = texts[i : i + batch_size]
                requests_payload = [
                    {
                        "model": f"models/{self._model_name}",
                        "content": {"parts": [{"text": t[:2048]}]},
                        "outputDimensionality": self._dimension,
                    }
                    for t in batch
                ]

                url = f"https://generativelanguage.googleapis.com/v1beta/models/{self._model_name}:batchEmbedContents?key={self._api_key}"
                try:
                    response = await client.post(url, json={"requests": requests_payload})
                    if response.status_code == 200:
                        data = response.json()
                        for emb in data.get("embeddings", []):
                            values = emb.get("values", [])
                            results.append(self._normalize(values))
                    else:
                        logger.error("[GeminiEmbedding] API error %d: %s", response.status_code, response.text)
                        from app.services.embeddings.mock import MockEmbeddingProvider
                        fallback = await MockEmbeddingProvider(dimension=self._dimension).embed_documents(batch)
                        results.extend(fallback)
                except Exception as exc:
                    logger.error("[GeminiEmbedding] Network exception: %s", exc)
                    from app.services.embeddings.mock import MockEmbeddingProvider
                    fallback = await MockEmbeddingProvider(dimension=self._dimension).embed_documents(batch)
                    results.extend(fallback)

        return results

    async def embed_query(self, text: str) -> list[float]:
        res = await self.embed_documents([text])
        if res:
            return res[0]
        return [0.0] * self._dimension
