"""RAG API routes — Phase 7.

Provides:
  POST /api/v1/rag/query   — synchronous RAG answer (JSON response)
  POST /api/v1/rag/stream  — SSE-streamed RAG answer with pipeline events

Routes are thin: all pipeline logic lives in CRAGOrchestrator.
Ownership isolation is enforced by user_id scoping in all retrieval calls.
"""
import logging
import time

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal, get_db_session
from app.schemas.rag import (
    RAGCRAGMeta,
    RAGQueryRequest,
    RAGQueryResponse,
    RAGRetrievalMeta,
)
from app.services.chat.sse import (
    error_event,
    rag_citation,
    rag_crag_retry,
    rag_generating,
    rag_grading,
    rag_message_complete,
    rag_query_rewrite,
    rag_reranking_complete,
    rag_reranking_started,
    rag_retrieval_complete,
    rag_retrieval_started,
    rag_stage_meta,
    text_delta,
)
from app.services.rag.answer_generator import RAGAnswerGenerator
from app.services.rag.crag import CRAGOrchestrator, _build_citations
from app.services.rag.grader import RetrievalGrader
from app.services.rag.query_rewriter import QueryRewriter
from app.services.reranking.factory import get_reranker
from app.services.retrieval.context_builder import ContextBuilder
from app.services.retrieval.hybrid import HybridRetriever
from app.core.config import get_settings
from app.providers.base import ProviderError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rag", tags=["rag"])


@router.post("/query", response_model=RAGQueryResponse)
async def rag_query(
    req: RAGQueryRequest,
    session: AsyncSession = Depends(get_db_session),
) -> RAGQueryResponse:
    """Run the CRAG pipeline synchronously and return a full JSON response.

    Latency is optimized: fast-path skips reranking on high confidence.
    """
    orchestrator = CRAGOrchestrator()
    result = await orchestrator.run(
        query=req.query,
        user_id=req.user_id,
        session=session,
        project_id=req.project_id,
        file_ids=req.file_ids,
        top_k=req.top_k,
    )

    return RAGQueryResponse(
        answer=result.answer,
        citations=result.citations,
        retrieval=RAGRetrievalMeta(
            retrieved=result.retrieved_count,
            reranked=result.reranked_count,
            confidence=result.grading_confidence,
            reranker_used=result.reranker_used,
            latency=result.latency,
        ),
        crag=RAGCRAGMeta(
            attempts=result.crag_attempts,
            rewritten=result.query_rewritten,
            final_decision=result.decision,
        ),
    )


@router.post("/stream")
async def rag_stream(
    req: RAGQueryRequest,
) -> StreamingResponse:
    """Run the CRAG pipeline with SSE streaming.

    Emits pipeline events: retrieval_started → retrieval_complete →
    [reranking_started → reranking_complete (if low confidence)] → grading →
    [query_rewrite → crag_retry] → rag_generating → message_delta* → citation* → message_complete.
    """
    settings = get_settings()
    retrieve_k = req.top_k or settings.rag_top_k
    rerank_k = settings.rag_rerank_top_k or settings.reranker_top_k
    max_retries = settings.rag_max_retries

    async def event_stream():
        async with AsyncSessionLocal() as stream_session:
            t_total_start = time.perf_counter()
            t_retrieval_ms = 0.0
            t_rerank_ms = 0.0
            t_grader_ms = 0.0
            t_rewrite_ms = 0.0
            t_retry_retrieval_ms = 0.0
            t_gen_ms = 0.0
            reranker_used = False

            try:
                from app.services.rag.scope_resolver import FileScopeResolver
                scope_resolver = FileScopeResolver()
                resolved_scope = await scope_resolver.resolve_scope(
                    session=stream_session,
                    user_id=req.user_id,
                    query=req.query,
                    explicit_file_ids=req.file_ids,
                    project_id=req.project_id,
                )
                effective_file_ids = resolved_scope.file_ids
                scoped_filenames = resolved_scope.filenames

                if resolved_scope.is_document_scoped and effective_file_ids == []:
                    # Unowned or invalid files requested
                    denial_msg = "Access denied or file not found. The specified document does not exist or does not belong to your account."
                    yield rag_generating()
                    for word in denial_msg.split():
                        yield text_delta(word + " ")
                    yield rag_message_complete(
                        answer=denial_msg,
                        citations=[],
                        retrieved=0,
                        reranked=0,
                        confidence=0.0,
                        attempts=1,
                        rewritten=False,
                        decision="insufficient_evidence",
                        latency={"total_time_ms": 0.0},
                        reranker_used=False,
                    )
                    return

                hybrid_retriever = HybridRetriever()
                reranker = get_reranker()
                grader = RetrievalGrader()
                query_rewriter = QueryRewriter()
                context_builder = ContextBuilder()
                answer_generator = RAGAnswerGenerator()

                current_query = req.query
                attempt = 0
                grade = None
                reranked_chunks = []
                retrieved_count = 0
                query_rewritten = False

                while attempt <= max_retries:
                    # Retrieval — strictly scoped
                    yield rag_retrieval_started(current_query)
                    t0 = time.perf_counter()
                    raw_chunks = await hybrid_retriever.search(
                        session=stream_session,
                        query=current_query,
                        user_id=req.user_id,
                        project_id=req.project_id,
                        file_ids=effective_file_ids,
                        top_k=retrieve_k * 2,
                    )
                    elapsed_ret = (time.perf_counter() - t0) * 1000.0
                    if attempt == 0:
                        t_retrieval_ms += elapsed_ret
                    else:
                        t_retry_retrieval_ms += elapsed_ret

                    retrieved_count = max(retrieved_count, len(raw_chunks))
                    yield rag_retrieval_complete(retrieved_count, attempt=attempt + 1)
                    yield rag_stage_meta("retrieval", "complete", elapsed_ret, details={"count": len(raw_chunks), "attempt": attempt + 1, "scope": scoped_filenames or "global"})

                    if not raw_chunks:
                        grade_conf = 0.0
                        grade_relevant = False
                        grade_reason = "No chunks retrieved."
                        yield rag_grading(grade_conf, grade_relevant, grade_reason)
                        yield rag_stage_meta("confidence", "low", 0.0, confidence=0.0)
                        if attempt < max_retries:
                            t_rw0 = time.perf_counter()
                            new_query = await query_rewriter.rewrite(current_query, grade_reason)
                            elapsed_rw = (time.perf_counter() - t_rw0) * 1000.0
                            t_rewrite_ms += elapsed_rw
                            yield rag_query_rewrite(current_query, new_query)
                            yield rag_stage_meta("rewrite", "complete", elapsed_rw, details={"rewritten": new_query})
                            current_query = new_query
                            query_rewritten = True
                            attempt += 1
                            yield rag_crag_retry(attempt, grade_reason)
                            continue
                        break

                    # Pre-Rerank Deterministic Confidence Evaluation (Fast-Path Check)
                    t_gr0 = time.perf_counter()
                    grade_result = await grader.grade(current_query, raw_chunks)
                    elapsed_gr = (time.perf_counter() - t_gr0) * 1000.0
                    t_grader_ms += elapsed_gr

                    # FAST PATH: On initial attempt, high retrieval confidence (>= threshold) -> SKIP Reranking
                    if attempt == 0 and grade_result.relevant and grade_result.confidence >= settings.rag_confidence_threshold:
                        grade = grade_result
                        reranked_chunks = raw_chunks[:rerank_k]
                        yield rag_grading(grade_result.confidence, grade_result.relevant, grade_result.reason)
                        yield rag_stage_meta("confidence", "high_fast_path", elapsed_gr, confidence=grade_result.confidence, details={"reranker_skipped": True})
                        break

                    # LOW-CONFIDENCE / AMBIGUOUS PATH: Only invoke CrossEncoder reranker when confidence is borderline
                    reranker_used = True
                    yield rag_reranking_started()
                    yield rag_stage_meta("reranker", "started", 0.0)
                    t_rr0 = time.perf_counter()
                    reranked_chunks = await reranker.rerank(
                        query=current_query,
                        chunks=raw_chunks,
                        top_k=rerank_k,
                    )
                    elapsed_rr = (time.perf_counter() - t_rr0) * 1000.0
                    t_rerank_ms += elapsed_rr
                    yield rag_reranking_complete(len(reranked_chunks))
                    yield rag_stage_meta("reranker", "complete", elapsed_rr, details={"candidates": len(reranked_chunks)})

                    t_gr0 = time.perf_counter()
                    post_grade = await grader.grade(current_query, reranked_chunks)
                    t_grader_ms += (time.perf_counter() - t_gr0) * 1000.0
                    yield rag_grading(post_grade.confidence, post_grade.relevant, post_grade.reason)
                    grade = post_grade

                    if grade.relevant and grade.confidence >= settings.rag_confidence_threshold:
                        break
                    if grade.relevant and grade.confidence >= settings.min_grounding_confidence and attempt >= max_retries:
                        break

                    if attempt < max_retries:
                        t_rw0 = time.perf_counter()
                        new_query = await query_rewriter.rewrite(current_query, grade.reason if grade else "low confidence")
                        elapsed_rw = (time.perf_counter() - t_rw0) * 1000.0
                        t_rewrite_ms += elapsed_rw
                        yield rag_query_rewrite(current_query, new_query)
                        yield rag_stage_meta("rewrite", "complete", elapsed_rw, details={"rewritten": new_query})
                        current_query = new_query
                        query_rewritten = True
                        attempt += 1
                        yield rag_crag_retry(attempt, grade.reason if grade else "low confidence")
                    else:
                        break

                # Determine context
                if grade and grade.relevant and reranked_chunks:
                    if grade.selected_chunk_indices:
                        context_chunks = [
                            reranked_chunks[i]
                            for i in grade.selected_chunk_indices
                            if i < len(reranked_chunks)
                        ] or reranked_chunks
                    else:
                        context_chunks = reranked_chunks
                else:
                    context_chunks = []

                total_elapsed_ms = (time.perf_counter() - t_total_start) * 1000.0
                timing_metrics = {
                    "retrieval_time_ms": round(t_retrieval_ms, 2),
                    "rerank_time_ms": round(t_rerank_ms, 2),
                    "grader_time_ms": round(t_grader_ms, 2),
                    "rewrite_time_ms": round(t_rewrite_ms, 2),
                    "retry_retrieval_time_ms": round(t_retry_retrieval_ms, 2),
                    "generation_time_ms": round(t_gen_ms, 2),
                    "total_time_ms": round(total_elapsed_ms, 2),
                    "reranker_used": reranker_used,
                }

                if not context_chunks:
                    # Insufficient evidence — stream the denial message
                    from app.services.rag.crag import _INSUFFICIENT_ANSWER
                    if scoped_filenames:
                        denial_answer = f"Based on the provided documents, I cannot find sufficient evidence to answer this question. The requested information is not present in {', '.join(scoped_filenames)}."
                    else:
                        denial_answer = _INSUFFICIENT_ANSWER
                    yield rag_generating()
                    for word in denial_answer.split():
                        yield text_delta(word + " ")
                    yield rag_message_complete(
                        answer=denial_answer,
                        citations=[],
                        retrieved=retrieved_count,
                        reranked=len(reranked_chunks),
                        confidence=grade.confidence if grade else 0.0,
                        attempts=attempt + 1,
                        rewritten=query_rewritten,
                        decision="insufficient_evidence",
                        latency=timing_metrics,
                        reranker_used=reranker_used,
                    )
                    return

                # Build context + citations — enforce allowed_file_ids invariant
                context_response = context_builder.build_context(
                    query=current_query,
                    chunks=context_chunks,
                    max_tokens=settings.rag_context_max_tokens,
                    allowed_file_ids=effective_file_ids,
                )
                citations = _build_citations(context_response.sources)

                # Emit citations
                for cit in citations:
                    yield rag_citation(cit.model_dump(mode="json"))

                # Stream answer
                yield rag_generating()
                yield rag_stage_meta("generation", "started", 0.0)
                t_g0 = time.perf_counter()
                answer_tokens: list[str] = []
                async for token in answer_generator.stream_answer(
                    query=req.query,
                    context_text=context_response.context_text,
                    citations=citations,
                    scoped_filenames=scoped_filenames,
                ):
                    answer_tokens.append(token)
                    yield text_delta(token)

                t_gen_ms = (time.perf_counter() - t_g0) * 1000.0
                total_elapsed_ms = (time.perf_counter() - t_total_start) * 1000.0
                timing_metrics["generation_time_ms"] = round(t_gen_ms, 2)
                timing_metrics["total_time_ms"] = round(total_elapsed_ms, 2)

                full_answer = "".join(answer_tokens)
                yield rag_message_complete(
                    answer=full_answer,
                    citations=[c.model_dump(mode="json") for c in citations],
                    retrieved=retrieved_count,
                    reranked=len(reranked_chunks),
                    confidence=grade.confidence if grade else 0.0,
                    attempts=attempt + 1,
                    rewritten=query_rewritten,
                    decision="grounded",
                    latency=timing_metrics,
                    reranker_used=reranker_used,
                )

            except ProviderError as exc:
                yield error_event(exc)
            except Exception as exc:
                logger.exception("RAG stream error: %s", exc)
                from app.providers.base import ProviderError, ProviderErrorCode
                yield error_event(
                    ProviderError(ProviderErrorCode.UNKNOWN, str(exc), retryable=False)
                )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
