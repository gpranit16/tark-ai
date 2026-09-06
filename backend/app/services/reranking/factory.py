import os

from app.core.config import get_settings
from app.services.reranking.base import BaseReranker

_reranker_instance: BaseReranker | None = None


def get_reranker() -> BaseReranker:
    """Factory function returning the configured reranker.

    Returns MockReranker when RERANKER_MODEL=mock (used in tests).
    Returns BGEReranker (BAAI/bge-reranker-v2-m3) by default.
    Singleton pattern — reranker is initialized once and reused.
    """
    global _reranker_instance

    reranker_model = os.environ.get("RERANKER_MODEL") or get_settings().reranker_model

    if reranker_model.lower() == "mock":
        from app.services.reranking.mock_reranker import MockReranker
        return MockReranker()

    if _reranker_instance is None:
        from app.services.reranking.bge_reranker import BGEReranker
        _reranker_instance = BGEReranker(model_name=reranker_model)

    return _reranker_instance
