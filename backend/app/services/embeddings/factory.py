import logging
import os
from app.core.config import get_settings
from app.services.embeddings.base import BaseEmbeddingProvider

logger = logging.getLogger(__name__)
_embedding_instance: BaseEmbeddingProvider | None = None


def get_embedding_provider() -> BaseEmbeddingProvider:
    global _embedding_instance
    settings = get_settings()
    provider_name = os.environ.get("EMBEDDING_PROVIDER") or settings.embedding_provider
    provider_name = provider_name.lower().strip()

    if provider_name == "mock":
        from app.services.embeddings.mock import MockEmbeddingProvider
        return MockEmbeddingProvider()

    if provider_name == "gemini":
        from app.services.embeddings.gemini import GeminiEmbeddingProvider
        if _embedding_instance is None or not isinstance(_embedding_instance, GeminiEmbeddingProvider):
            _embedding_instance = GeminiEmbeddingProvider()
        return _embedding_instance

    # Cloud environment protection:
    # SentenceTransformer('BAAI/bge-m3') is 2.24 GB and requires ~3GB RAM.
    # On Render (512MB RAM free tier), attempting to load BGE causes fatal SIGKILL / OOM crash.
    # Therefore, in production / on Render, use lightweight MockEmbeddingProvider so keyword search and instant document extraction work with 0MB RAM.
    is_render_prod = (
        settings.app_env == "production"
        or os.environ.get("RENDER") == "true"
        or os.environ.get("RENDER_SERVICE_ID") is not None
    )

    if is_render_prod:
        from app.services.embeddings.mock import MockEmbeddingProvider
        if _embedding_instance is None or not isinstance(_embedding_instance, MockEmbeddingProvider):
            _embedding_instance = MockEmbeddingProvider()
        return _embedding_instance

    try:
        from app.services.embeddings.bge import LocalBGEEmbeddingProvider
        if _embedding_instance is None or not isinstance(_embedding_instance, LocalBGEEmbeddingProvider):
            _embedding_instance = LocalBGEEmbeddingProvider()
        return _embedding_instance
    except Exception as e:
        logger.warning("[EmbeddingFactory] Failed to initialize LocalBGEEmbeddingProvider: %s. Using MockEmbeddingProvider", e)
        from app.services.embeddings.mock import MockEmbeddingProvider
        return MockEmbeddingProvider()

