import asyncio
import logging
import threading
import time
from typing import Any

from app.core.config import get_settings
from app.schemas.retrieval import RetrievalResult
from app.services.reranking.base import BaseReranker

logger = logging.getLogger(__name__)

_RERANKER_MODEL_CACHE: dict[str, Any] = {}
_RERANKER_LOCK = threading.Lock()


def warmup_reranker(model_name: str | None = None) -> float:
    """Pre-load CrossEncoder weights into process singleton cache and run dummy inference.

    Ensures that when reranking is needed, requests do not experience cold-start model loads.
    """
    settings = get_settings()
    name = model_name or settings.reranker_model
    t0 = time.perf_counter()
    cache_hit = name in _RERANKER_MODEL_CACHE
    with _RERANKER_LOCK:
        if name not in _RERANKER_MODEL_CACHE:
            from sentence_transformers import CrossEncoder
            _RERANKER_MODEL_CACHE[name] = CrossEncoder(name)
    model = _RERANKER_MODEL_CACHE[name]
    # Quick warmup inference
    model.predict([["warmup query", "warmup passage"]], show_progress_bar=False)
    warmup_time_ms = (time.perf_counter() - t0) * 1000.0
    logger.info(
        "[Reranker Warmup] reranker_loaded=true, reranker_cache_hit=%s, warmup_time_ms=%.2f",
        cache_hit, warmup_time_ms,
    )
    return warmup_time_ms


class BGEReranker(BaseReranker):
    """Local reranker using BAAI/bge-reranker-v2-m3 (CrossEncoder).

    Uses sentence-transformers CrossEncoder for cross-attention reranking.
    Model weights are loaded once into process singleton dictionary and reused across requests.
    Inference runs in a thread pool to avoid blocking the event loop.
    """

    def __init__(self, model_name: str | None = None):
        settings = get_settings()
        self._model_name = model_name or settings.reranker_model

    def _get_model(self) -> Any:
        cache_hit = self._model_name in _RERANKER_MODEL_CACHE
        if not cache_hit:
            with _RERANKER_LOCK:
                if self._model_name not in _RERANKER_MODEL_CACHE:
                    t0 = time.perf_counter()
                    try:
                        from sentence_transformers import CrossEncoder
                        _RERANKER_MODEL_CACHE[self._model_name] = CrossEncoder(self._model_name)
                        load_ms = (time.perf_counter() - t0) * 1000.0
                        logger.info(
                            "[Reranker Init] reranker_loaded=true, reranker_cache_hit=false, model_load_ms=%.2f",
                            load_ms,
                        )
                    except Exception as e:
                        raise RuntimeError(
                            f"Failed to initialize reranker model '{self._model_name}': {e}"
                        )
        return _RERANKER_MODEL_CACHE[self._model_name]

    def _rerank_sync(
        self,
        query: str,
        contents: list[str],
    ) -> list[float]:
        """Run cross-encoder inference synchronously (called in thread pool)."""
        model = self._get_model()
        pairs = [[query, content] for content in contents]
        scores = model.predict(pairs, show_progress_bar=False)
        # sigmoid to normalize to [0, 1]
        import math
        def sigmoid(x: float) -> float:
            return 1.0 / (1.0 + math.exp(-float(x)))
        return [round(sigmoid(float(s)), 4) for s in scores]

    async def rerank(
        self,
        query: str,
        chunks: list[RetrievalResult],
        top_k: int | None = None,
    ) -> list[RetrievalResult]:
        """Rerank chunks using cross-encoder; returns top_k highest-scored chunks."""
        if not chunks or not query.strip():
            return chunks[:top_k] if top_k else chunks

        settings = get_settings()
        k = top_k or settings.rag_rerank_top_k or settings.reranker_top_k

        # Keep candidates small (5-8 max) to avoid wasteful CPU inference
        max_candidates = min(len(chunks), 8)
        candidates = chunks[:max_candidates]

        contents = [c.content for c in candidates]
        cache_hit = self._model_name in _RERANKER_MODEL_CACHE
        logger.info(
            "[Reranker Inference] reranker_loaded=true, reranker_cache_hit=%s, candidates=%d",
            cache_hit, len(candidates),
        )

        try:
            t0 = time.perf_counter()
            scores = await asyncio.wait_for(
                asyncio.to_thread(self._rerank_sync, query, contents),
                timeout=settings.rag_reranker_timeout,
            )
            inf_ms = (time.perf_counter() - t0) * 1000.0
            logger.info("[Reranker Inference] inference_time_ms=%.2f", inf_ms)

            # Pair each chunk with its rerank score and sort descending
            scored = list(zip(candidates, scores))
            scored.sort(key=lambda x: x[1], reverse=True)

            results: list[RetrievalResult] = []
            for chunk, rerank_score in scored[:k]:
                results.append(
                    RetrievalResult(
                        chunk_id=chunk.chunk_id,
                        file_id=chunk.file_id,
                        project_id=chunk.project_id,
                        content=chunk.content,
                        page_number=chunk.page_number,
                        chunk_index=chunk.chunk_index,
                        similarity_score=rerank_score,
                        metadata=chunk.metadata,
                    )
                )
            return results

        except Exception as exc:
            err_msg = str(exc) or type(exc).__name__
            logger.warning("Reranking failed or timed out (%s), falling back to retrieval scores", err_msg)
            # Fallback to retrieval scores
            sorted_chunks = sorted(chunks, key=lambda c: c.similarity_score, reverse=True)
            return sorted_chunks[:k]
