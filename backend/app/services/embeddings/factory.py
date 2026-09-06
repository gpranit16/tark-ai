import os
from app.core.config import get_settings
from app.services.embeddings.base import BaseEmbeddingProvider

_embedding_instance: BaseEmbeddingProvider | None = None


def get_embedding_provider() -> BaseEmbeddingProvider:
    global _embedding_instance
    settings = get_settings()
    provider_name = os.environ.get("EMBEDDING_PROVIDER") or settings.embedding_provider
    provider_name = provider_name.lower().strip()

    if provider_name == "mock":
        from app.services.embeddings.mock import MockEmbeddingProvider
        return MockEmbeddingProvider()

    if provider_name == "gemini" or (settings.app_env == "production" and settings.gemini_api_key):
        from app.services.embeddings.gemini import GeminiEmbeddingProvider
        if _embedding_instance is None or not isinstance(_embedding_instance, GeminiEmbeddingProvider):
            _embedding_instance = GeminiEmbeddingProvider()
        return _embedding_instance

    from app.services.embeddings.bge import LocalBGEEmbeddingProvider
    if _embedding_instance is None or not isinstance(_embedding_instance, LocalBGEEmbeddingProvider):
        _embedding_instance = LocalBGEEmbeddingProvider()
    return _embedding_instance

