import os
from app.core.config import get_settings
from app.services.embeddings.base import BaseEmbeddingProvider
from app.services.embeddings.bge import LocalBGEEmbeddingProvider
from app.services.embeddings.mock import MockEmbeddingProvider

_embedding_instance: BaseEmbeddingProvider | None = None


def get_embedding_provider() -> BaseEmbeddingProvider:
    global _embedding_instance
    provider_name = os.environ.get("EMBEDDING_PROVIDER") or get_settings().embedding_provider
    if provider_name.lower() == "mock":
        return MockEmbeddingProvider()
    
    if _embedding_instance is None or not isinstance(_embedding_instance, LocalBGEEmbeddingProvider):
        _embedding_instance = LocalBGEEmbeddingProvider()
    return _embedding_instance
