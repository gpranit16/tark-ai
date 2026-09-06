import os
import logging
from app.core.config import get_settings
from app.services.reranking.base import BaseReranker

logger = logging.getLogger(__name__)
_reranker_instance: BaseReranker | None = None


def get_reranker() -> BaseReranker:
    """Factory function returning the configured reranker.

    Returns MockReranker when RERANKER_MODEL=mock or in memory-constrained environments.
    Returns BGEReranker by default.
    """
    global _reranker_instance
    settings = get_settings()

    reranker_model = os.environ.get("RERANKER_MODEL") or settings.reranker_model
    reranker_model_clean = reranker_model.lower().strip()

    if reranker_model_clean == "mock" or settings.app_env == "production":
        from app.services.reranking.mock_reranker import MockReranker
        return MockReranker()

    if _reranker_instance is None:
        try:
            from app.services.reranking.bge_reranker import BGEReranker
            _reranker_instance = BGEReranker(model_name=reranker_model)
        except Exception as e:
            logger.warning("[Reranker] Failed to initialize BGEReranker (%s), using MockReranker", e)
            from app.services.reranking.mock_reranker import MockReranker
            return MockReranker()

    return _reranker_instance

