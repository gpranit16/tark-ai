"""CRAGOrchestrator — the main CRAG pipeline orchestrator.

Full pipeline:
  query
  → HybridRetrieval (top_k * 2 candidates)
  → BGEReranker (top_k results)
  → RetrievalGrader (sufficient?)
  → IF sufficient: ContextBuilder → RAGAnswerGenerator → CRAGResult
  → IF weak + retries remain: QueryRewriter → re-retrieve → re-rank → re-grade
  → IF max retries exceeded: return insufficient_evidence result

Design principles:
  - Reuses all existing Phase 6 retrievers and ContextBuilder.
  - Uses ModelRouter via grader/rewriter/generator — no direct provider calls.
  - Never hallucinates: if grader says insufficient, returns explicit denial.
  - All thresholds and retry limits are configurable via Settings.
"""
import asyncio
import logging
import re
import time
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.chunk import DocumentChunk
from app.models.document import ParsedDocument
from app.models.file import File
from app.schemas.rag import CRAGResult, GradeResult, RAGCitation, RAGLatencyBreakdown
from app.schemas.retrieval import RetrievalResult
from app.services.rag.answer_generator import RAGAnswerGenerator
from app.services.rag.grader import RetrievalGrader, evaluate_deterministic_confidence
from app.services.rag.query_rewriter import QueryRewriter
from app.services.rag.scope_resolver import FileScopeResolver
from app.services.reranking.factory import get_reranker
from app.services.retrieval.context_builder import ContextBuilder
from app.services.retrieval.hybrid import HybridRetriever

if TYPE_CHECKING:
    from app.services.chat.router import ModelRouter

logger = logging.getLogger(__name__)

_INSUFFICIENT_ANSWER = (
    "Based on the provided documents, I cannot find sufficient evidence to answer "
    "this question. The retrieved document chunks do not contain relevant information "
    "for your query. Please ensure the relevant documents have been uploaded and "
    "their embeddings have been generated, or try rephrasing your question."
)

_SYNOPSIS_PATTERNS = [
    r"\bwhat\s+is\s+this\b",
    r"\bwho\s+is\s+this\b",
    r"\bwhat(?:'s|\s+is)\s+in\s+(?:this|here)\b",
    r"\bsummariz\w*\b",
    r"\boverview\b",
    r"\bexplain\s+this\b",
    r"\bwhat\s+does\s+this\s+(?:doc|pdf|file|document|paper|report)\b",
    r"\btell\s+me\s+about\s+(?:this|the\s+doc|the\s+pdf|the\s+file|the\s+document)\b",
    r"\breview\s+(?:this|the\s+doc|the\s+pdf|the\s+file|the\s+document)\b",
    r"\bwhat\s+is\s+(?:this|the)\s+(?:doc|pdf|file|document|paper|report)\b",
    r"\bwhat\s+is\s+it\s+about\b",
    r"\bwhat\s+are\s+(?:the\s+contents|the\s+key\s+points|the\s+highlights)\b",
]

_COMPILED_SYNOPSIS = [re.compile(p, re.IGNORECASE) for p in _SYNOPSIS_PATTERNS]


def _is_synopsis_query(query: str) -> bool:
    cleaned = query.strip().lower()
    return any(p.search(cleaned) for p in _COMPILED_SYNOPSIS)


class CRAGOrchestrator:
    """Orchestrates the full CRAG retrieval-augmented generation pipeline."""

    def __init__(
        self,
        hybrid_retriever: HybridRetriever | None = None,
        grader: RetrievalGrader | None = None,
        query_rewriter: QueryRewriter | None = None,
        context_builder: ContextBuilder | None = None,
        answer_generator: RAGAnswerGenerator | None = None,
        router: "ModelRouter | None" = None,
        scope_resolver: FileScopeResolver | None = None,
    ):
        self.hybrid_retriever = hybrid_retriever or HybridRetriever()
        self.grader = grader or RetrievalGrader(router=router)
        self.query_rewriter = query_rewriter or QueryRewriter(router=router)
        self.context_builder = context_builder or ContextBuilder()
        self.answer_generator = answer_generator or RAGAnswerGenerator(router=router)
        self.reranker = get_reranker()
        self.scope_resolver = scope_resolver or FileScopeResolver()

    async def prepare_rag_context(
        self,
        query: str,
        user_id: UUID,
        session: AsyncSession,
        project_id: UUID | None = None,
        file_ids: list[UUID] | None = None,
        top_k: int | None = None,
        thread_id: UUID | None = None,
    ) -> tuple[CRAGResult, str, list[RAGCitation], list[str]]:
        """Run retrieval, reranking, grading, and context building without generating final LLM answer.

        Returns (crag_result_draft, context_text, citations, scoped_filenames).
        """
        settings = get_settings()
        retrieve_k = top_k or settings.retrieval_top_k
        rerank_k = settings.reranker_top_k
        max_retries = settings.crag_max_retries

        # Resolve document / attachment scope with strict priority hierarchy
        resolved_scope = await self.scope_resolver.resolve_scope(
            session=session,
            user_id=user_id,
            query=query,
            explicit_file_ids=file_ids,
            project_id=project_id,
            thread_id=thread_id,
        )
        effective_file_ids = resolved_scope.file_ids
        scoped_filenames = resolved_scope.filenames

        # If user explicitly specified files that do not belong to them, deny access immediately
        if resolved_scope.is_document_scoped and effective_file_ids == []:
            logger.warning(
                "Ownership isolation: None of file_ids %s belong to user_id %s",
                file_ids, user_id,
            )
            empty_res = CRAGResult(
                decision="insufficient_evidence",
                answer="Access denied or file not found. The specified document does not exist or does not belong to your account.",
                citations=[],
                context_text="",
                retrieved_count=0,
                reranked_count=0,
                grading_confidence=0.0,
                crag_attempts=1,
                query_rewritten=False,
                original_query=query,
                final_query=query,
            )
            return empty_res, "", [], []

        # Validate indexing lifecycle if document scope is active
        if effective_file_ids:
            chunk_stmt = select(DocumentChunk.id).where(
                DocumentChunk.file_id.in_(effective_file_ids),
                DocumentChunk.user_id == user_id,
            ).limit(1)
            chunk_res = await session.execute(chunk_stmt)
            has_chunks = chunk_res.scalar_one_or_none() is not None

            if not has_chunks:
                # Check parsed document status
                doc_stmt = select(ParsedDocument).where(
                    ParsedDocument.file_id.in_(effective_file_ids),
                    ParsedDocument.user_id == user_id,
                )
                doc_res = await session.execute(doc_stmt)
                parsed_docs = list(doc_res.scalars().all())

                # If any document is still processing/pending, wait briefly (up to 3 seconds)
                if any(d.status in ("pending", "processing") for d in parsed_docs) or len(parsed_docs) < len(effective_file_ids):
                    for _ in range(6):
                        await asyncio.sleep(0.5)
                        recheck_chunks = await session.execute(chunk_stmt)
                        if recheck_chunks.scalar_one_or_none() is not None:
                            has_chunks = True
                            break
                        doc_res = await session.execute(doc_stmt)
                        parsed_docs = list(doc_res.scalars().all())
                        if not any(d.status in ("pending", "processing") for d in parsed_docs) and len(parsed_docs) == len(effective_file_ids):
                            break

                # If parsed documents are completed, ensure embeddings are ingested on the fly
                if not has_chunks:
                    completed_file_ids = [d.file_id for d in parsed_docs if d.status == "completed"]
                    for fid in completed_file_ids:
                        try:
                            from app.services.embeddings.ingestion import EmbeddingIngestionService
                            ingestion_svc = EmbeddingIngestionService()
                            await ingestion_svc.ingest_file(session, fid, user_id)
                            has_chunks = True
                        except Exception as e:
                            logger.error("On-the-fly ingestion failed for file %s: %s", fid, e)

                # Recheck if still no chunks
                final_check = await session.execute(chunk_stmt)
                if final_check.scalar_one_or_none() is None:
                    doc_res = await session.execute(doc_stmt)
                    fresh_docs = list(doc_res.scalars().all())
                    if any(d.status in ("pending", "processing") for d in fresh_docs) or len(fresh_docs) < len(effective_file_ids):
                        empty_res = CRAGResult(
                            decision="insufficient_evidence",
                            answer="The attached document is currently being processed and indexed. Please try again in a few moments.",
                            citations=[],
                            context_text="",
                            retrieved_count=0,
                            reranked_count=0,
                            grading_confidence=0.0,
                            crag_attempts=1,
                            query_rewritten=False,
                            original_query=query,
                            final_query=query,
                        )
                        return empty_res, "", [], scoped_filenames

        t_total_start = time.perf_counter()
        t_retrieval_ms = 0.0
        t_rerank_ms = 0.0
        t_grader_ms = 0.0
        t_rewrite_ms = 0.0
        t_retry_retrieval_ms = 0.0
        t_gen_ms = 0.0

        current_query = query
        attempt = 0
        grade: GradeResult | None = None
        reranked_chunks: list[RetrievalResult] = []
        retrieved_count = 0
        query_rewritten = False
        reranker_used = False

        debug_mode = settings.rag_debug_logging
        is_synopsis = _is_synopsis_query(query) and bool(effective_file_ids)

        while attempt <= max_retries:
            # 1. Retrieval (Document Synopsis Fast Path or Hybrid Retrieval)
            if debug_mode:
                logger.info("[CRAG Stage: Retrieval] attempt=%d query=%r scope=%s synopsis=%s", attempt, current_query, scoped_filenames or "global", is_synopsis)
            t0 = time.perf_counter()

            if is_synopsis and effective_file_ids:
                # Synopsis Fast-Path: Fetch ordered leading & representative chunks from target document
                lead_stmt = select(DocumentChunk).where(
                    DocumentChunk.file_id.in_(effective_file_ids),
                    DocumentChunk.user_id == user_id,
                ).order_by(DocumentChunk.chunk_index.asc()).limit(retrieve_k * 2)
                lead_res = await session.execute(lead_stmt)
                lead_db_chunks = lead_res.scalars().all()
                raw_chunks = [
                    RetrievalResult(
                        chunk_id=lc.id,
                        file_id=lc.file_id,
                        project_id=lc.project_id,
                        content=lc.content,
                        page_number=lc.page_number,
                        chunk_index=lc.chunk_index,
                        similarity_score=0.90,
                        metadata=dict(lc.metadata_) if lc.metadata_ else {},
                    )
                    for lc in lead_db_chunks
                ]
            else:
                raw_chunks = await self.hybrid_retriever.search(
                    session=session,
                    query=current_query,
                    user_id=user_id,
                    project_id=project_id,
                    file_ids=effective_file_ids,
                    top_k=retrieve_k * 2,
                )

            elapsed_ret = (time.perf_counter() - t0) * 1000.0
            if attempt == 0:
                t_retrieval_ms += elapsed_ret
            else:
                t_retry_retrieval_ms += elapsed_ret

            # If document scope is active and query is synopsis and search yielded no chunks, fetch leading chunks
            if is_synopsis and effective_file_ids and not raw_chunks:
                lead_stmt = select(DocumentChunk).where(
                    DocumentChunk.file_id.in_(effective_file_ids),
                    DocumentChunk.user_id == user_id,
                ).order_by(DocumentChunk.chunk_index.asc()).limit(retrieve_k)
                lead_res = await session.execute(lead_stmt)
                lead_db_chunks = lead_res.scalars().all()
                if lead_db_chunks:
                    for lc in lead_db_chunks:
                        raw_chunks.append(
                            RetrievalResult(
                                chunk_id=lc.id,
                                file_id=lc.file_id,
                                project_id=lc.project_id,
                                content=lc.content,
                                page_number=lc.page_number,
                                chunk_index=lc.chunk_index,
                                similarity_score=0.30,
                                metadata=dict(lc.metadata_) if lc.metadata_ else {},
                            )
                        )

            retrieved_count = max(retrieved_count, len(raw_chunks))
            if debug_mode:
                logger.info("[CRAG Stage: Retrieval Complete] attempt=%d count=%d elapsed_ms=%.2f", attempt, len(raw_chunks), elapsed_ret)

            if not raw_chunks:
                if debug_mode:
                    logger.info("[CRAG Stage: Retrieval] 0 chunks retrieved.")
                grade = GradeResult(
                    relevant=False,
                    confidence=0.0,
                    reason="No document chunks found for the specified scope.",
                    selected_chunk_indices=[],
                )
                if attempt < max_retries and not is_synopsis:
                    t_rw0 = time.perf_counter()
                    new_q = await self.query_rewriter.rewrite(
                        query, context_hint=grade.reason
                    )
                    t_rw = (time.perf_counter() - t_rw0) * 1000.0
                    t_rewrite_ms += t_rw
                    if debug_mode:
                        logger.info("[CRAG Stage: Query Rewrite] original=%r rewritten=%r elapsed_ms=%.2f", current_query, new_q, t_rw)
                    current_query = new_q
                    query_rewritten = True
                    attempt += 1
                    continue
                break

            # 2. Synopsis / Pre-Rerank Fast Path or CrossEncoder Rerank
            if is_synopsis:
                reranked_chunks = raw_chunks[:retrieve_k]
                grade = GradeResult(
                    relevant=True,
                    confidence=0.90,
                    reason="Document synopsis query grounded on document leading contents.",
                    selected_chunk_indices=list(range(len(reranked_chunks))),
                )
                reranker_used = False
                break

            det_grade = evaluate_deterministic_confidence(raw_chunks, threshold=settings.rag_confidence_threshold)
            if det_grade.relevant and det_grade.confidence >= settings.rag_confidence_threshold:
                # Fast path: High confidence deterministic match skips LLM grading & reranker
                if debug_mode:
                    logger.info("[CRAG Stage: Grader Fast-Path] High confidence=%.2f. Skipping reranker and LLM grading.", det_grade.confidence)
                reranked_chunks = raw_chunks[:retrieve_k]
                grade = det_grade
                reranker_used = False
                break

            # 3. Reranking
            if debug_mode:
                logger.info("[CRAG Stage: Reranking] Reranking %d candidate chunks...", len(raw_chunks))
            t_rr0 = time.perf_counter()
            reranked_chunks = await self.reranker.rerank(
                query=current_query,
                chunks=raw_chunks,
                top_k=rerank_k,
            )
            t_rerank_ms += (time.perf_counter() - t_rr0) * 1000.0
            reranker_used = True

            # 4. Grading
            t_gr0 = time.perf_counter()
            grade = await self.grader.grade(
                query=current_query,
                chunks=reranked_chunks,
            )
            t_grader_ms += (time.perf_counter() - t_gr0) * 1000.0

            if debug_mode:
                logger.info(
                    "[CRAG Stage: Grader Complete] attempt=%d relevant=%s confidence=%.2f reason=%r",
                    attempt, grade.relevant, grade.confidence, grade.reason
                )

            # If relevant and confident enough, we're done
            if grade.relevant and grade.confidence >= settings.min_grounding_confidence:
                break

            # If confidence is low and retries remain, rewrite query and re-retrieve
            if attempt < max_retries:
                t_rw0 = time.perf_counter()
                new_q = await self.query_rewriter.rewrite(
                    query, context_hint=grade.reason
                )
                t_rw = (time.perf_counter() - t_rw0) * 1000.0
                t_rewrite_ms += t_rw
                if debug_mode:
                    logger.info("[CRAG Stage: Query Rewrite] original=%r rewritten=%r elapsed_ms=%.2f", current_query, new_q, t_rw)
                current_query = new_q
                query_rewritten = True
                attempt += 1
            else:
                break
        # Select which chunks to use for context
        # Must have relevant grade and confidence >= min_grounding_confidence
        min_conf = settings.min_grounding_confidence
        if grade and grade.confidence >= min_conf and reranked_chunks:
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

        # Safe timing breakdown
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

        # If no useful context, return insufficient evidence refusal
        if not context_chunks:
            logger.info(
                "[CRAG] decision=insufficient_evidence retrieval=%.1fms confidence=%.2f reranker_used=%s rewrite=%s retry=%d total_ms=%.1fms",
                t_retrieval_ms, grade.confidence if grade else 0.0, reranker_used, query_rewritten, attempt, total_elapsed_ms
            )
            if scoped_filenames:
                refusal_text = f"Based on the provided documents, I cannot find sufficient evidence to answer this question. The requested information is not present in {', '.join(scoped_filenames)}."
            else:
                refusal_text = _INSUFFICIENT_ANSWER

            res = CRAGResult(
                decision="insufficient_evidence",
                answer=refusal_text,
                citations=[],
                context_text="",
                retrieved_count=retrieved_count,
                reranked_count=len(reranked_chunks),
                grading_confidence=grade.confidence if grade else 0.0,
                reranker_used=reranker_used,
                crag_attempts=attempt + 1,
                query_rewritten=query_rewritten,
                original_query=query,
                final_query=current_query,
                latency=RAGLatencyBreakdown(**timing_metrics),
            )
            return res, "", [], scoped_filenames

        # 4. Build context — enforce allowed_file_ids invariant
        context_response = self.context_builder.build_context(
            query=current_query,
            chunks=context_chunks,
            max_tokens=settings.rag_context_max_tokens,
            allowed_file_ids=effective_file_ids,
        )

        # 5. Build structured citations
        citations = _build_citations(context_response.sources)

        res = CRAGResult(
            decision="grounded",
            answer="",
            citations=citations,
            context_text=context_response.context_text,
            retrieved_count=retrieved_count,
            reranked_count=len(reranked_chunks),
            grading_confidence=grade.confidence if grade else 0.0,
            reranker_used=reranker_used,
            crag_attempts=attempt + 1,
            query_rewritten=query_rewritten,
            original_query=query,
            final_query=current_query,
            latency=RAGLatencyBreakdown(**timing_metrics),
        )
        return res, context_response.context_text, citations, scoped_filenames

    async def run(
        self,
        query: str,
        user_id: UUID,
        session: AsyncSession,
        project_id: UUID | None = None,
        file_ids: list[UUID] | None = None,
        top_k: int | None = None,
        thread_id: UUID | None = None,
    ) -> CRAGResult:
        """Run the full CRAG pipeline end-to-end (including answer generation)."""
        result, context_text, citations, scoped_filenames = await self.prepare_rag_context(
            query=query,
            user_id=user_id,
            session=session,
            project_id=project_id,
            file_ids=file_ids,
            top_k=top_k,
            thread_id=thread_id,
        )

        if result.decision != "grounded" or not context_text:
            return result

        t_g0 = time.perf_counter()
        answer = await self.answer_generator.generate_answer(
            query=query,
            context_text=context_text,
            citations=citations,
            scoped_filenames=scoped_filenames,
        )
        t_gen_ms = (time.perf_counter() - t_g0) * 1000.0

        if result.latency:
            result.latency.generation_time_ms = round(t_gen_ms, 2)
            result.latency.total_time_ms = round(result.latency.total_time_ms + t_gen_ms, 2)

        result.answer = answer
        return result


def _build_citations(sources: list) -> list[RAGCitation]:
    """Convert ContextBuilder CitationSources to RAGCitation objects."""
    seen_chunk_ids: set = set()
    citations: list[RAGCitation] = []
    for src in sources:
        if src.chunk_id in seen_chunk_ids:
            continue  # Deduplicate by chunk_id
        seen_chunk_ids.add(src.chunk_id)
        reference = f"{src.filename} p.{src.page_number}"
        citations.append(
            RAGCitation(
                chunk_id=src.chunk_id,
                file_id=src.file_id,
                filename=src.filename,
                page_number=src.page_number,
                chunk_index=src.chunk_index,
                similarity_score=src.similarity_score,
                reference=reference,
                snippet=src.snippet,
            )
        )
    return citations
