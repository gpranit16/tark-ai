"""RetrievalGrader — determines whether retrieved evidence is sufficient to answer a query.

Supports:
1. Fast-path deterministic confidence scoring (top reranker score, score gap, source diversity).
2. Optional LLM grading when enabled (RAG_ENABLE_LLM_GRADER=true) for ambiguous cases.
3. Strict fallback to deterministic scoring on timeout or parsing error.
"""
import asyncio
import json
import logging
from typing import TYPE_CHECKING

from app.core.config import get_settings
from app.core.enums import ConversationMode, MessageRole
from app.providers.base import NormalizedMessage
from app.schemas.rag import GradeResult
from app.schemas.retrieval import RetrievalResult

if TYPE_CHECKING:
    from app.services.chat.router import ModelRouter

logger = logging.getLogger(__name__)

_GRADER_SYSTEM = """\
You are a document relevance grader. Your job is to decide whether the provided
document chunks contain sufficient evidence to answer the user's query.

Rules:
- Only consider evidence that is explicitly present in the chunks.
- Do NOT use your own knowledge to fill gaps.
- If chunks partially answer the query, score them honestly.

Respond ONLY with valid JSON (no markdown, no explanation):
{
  "relevant": true or false,
  "confidence": <float 0.0-1.0>,
  "reason": "<one sentence>",
  "selected_chunk_indices": [<list of int indices that are relevant>]
}
"""


def evaluate_deterministic_confidence(
    chunks: list[RetrievalResult],
    threshold: float | None = None,
) -> GradeResult:
    """Evaluate retrieval confidence using deterministic reranker and retrieval signals.

    Signals:
    - top cross-encoder score
    - score gap between top and runner-up results
    - candidate count and source diversity
    """
    settings = get_settings()
    conf_threshold = threshold if threshold is not None else settings.rag_confidence_threshold

    if not chunks:
        return GradeResult(
            relevant=False,
            confidence=0.0,
            reason="No chunks retrieved.",
            selected_chunk_indices=[],
        )

    scores = [c.similarity_score for c in chunks]
    top_score = max(scores)
    avg_score = sum(scores) / len(scores)

    # Score gap between rank 1 and rank 2
    score_gap = (scores[0] - scores[1]) if len(scores) > 1 else (scores[0] * 0.2)
    unique_files = len(set(c.file_id for c in chunks if c.file_id))

    # Calculate confidence composite: primary weight on top reranked score
    # with a slight boost if multiple distinct sources agree
    diversity_bonus = 0.03 if unique_files > 1 else 0.0
    gap_bonus = 0.02 if score_gap > 0.15 else 0.0
    computed_conf = min(1.0, round(top_score + diversity_bonus + gap_bonus, 4))

    relevant = computed_conf >= conf_threshold

    # Select chunks that meet a reasonable fraction of top score or threshold
    selection_cutoff = max(settings.min_grounding_confidence, top_score * 0.6)
    selected = [i for i, c in enumerate(chunks) if c.similarity_score >= selection_cutoff]
    if relevant and not selected:
        selected = [0]

    reason = (
        f"Deterministic confidence: top={top_score:.2f}, avg={avg_score:.2f}, "
        f"conf={computed_conf:.2f} (threshold={conf_threshold:.2f})"
    )

    return GradeResult(
        relevant=relevant,
        confidence=computed_conf,
        reason=reason,
        selected_chunk_indices=selected,
    )


class RetrievalGrader:
    """Grades retrieved chunks for relevance to the query.

    Uses deterministic confidence scoring by default for sub-millisecond fast-path.
    Only invokes LLM grading if RAG_ENABLE_LLM_GRADER is explicitly True and confidence is ambiguous.
    """

    def __init__(self, router: "ModelRouter | None" = None):
        self._router = router

    def _get_router(self) -> "ModelRouter":
        if self._router is None:
            from app.services.chat.router import ModelRouter
            self._router = ModelRouter.from_settings()
        return self._router

    async def _grade_llm(
        self,
        query: str,
        chunks: list[RetrievalResult],
    ) -> GradeResult | None:
        """Call LLM grader with timeout protection."""
        chunk_texts = []
        for i, c in enumerate(chunks):
            filename = c.metadata.get("filename", "document")
            chunk_texts.append(
                f"[Chunk {i} | {filename} | Page {c.page_number}]:\n{c.content}"
            )
        chunks_str = "\n\n".join(chunk_texts)

        user_prompt = (
            f"QUERY: {query}\n\n"
            f"DOCUMENT CHUNKS:\n{chunks_str}\n\n"
            f"Grade the relevance of the above chunks to the query."
        )

        messages = [
            NormalizedMessage(role=MessageRole.SYSTEM, content=_GRADER_SYSTEM),
            NormalizedMessage(role=MessageRole.USER, content=user_prompt),
        ]

        router = self._get_router()
        settings = get_settings()
        full_text = ""
        async for _selection, event in router.stream(
            messages=messages,
            mode=ConversationMode.FAST,
            max_tokens=settings.rag_grader_max_output_tokens,
        ):
            if event.delta:
                full_text += event.delta

        grade_data = _extract_json(full_text)
        if grade_data:
            relevant = bool(grade_data.get("relevant", False))
            confidence = float(grade_data.get("confidence", 0.0))
            reason = str(grade_data.get("reason", ""))
            selected = [
                int(i)
                for i in grade_data.get("selected_chunk_indices", [])
                if 0 <= int(i) < len(chunks)
            ]
            return GradeResult(
                relevant=relevant,
                confidence=min(1.0, max(0.0, confidence)),
                reason=reason,
                selected_chunk_indices=selected,
            )
        return None

    async def grade(
        self,
        query: str,
        chunks: list[RetrievalResult],
    ) -> GradeResult:
        """Grade whether the chunks provide sufficient evidence for the query."""
        settings = get_settings()

        if not chunks:
            return GradeResult(
                relevant=False,
                confidence=0.0,
                reason="No chunks retrieved.",
                selected_chunk_indices=[],
            )

        # 1. Deterministic Fast-Path Evaluation
        det_grade = evaluate_deterministic_confidence(
            chunks, threshold=settings.rag_confidence_threshold
        )

        # If LLM grader is disabled OR confidence is already high (>= threshold), return immediately
        if not settings.rag_enable_llm_grader or det_grade.confidence >= settings.rag_confidence_threshold:
            return det_grade

        # 2. Ambiguous case with LLM grader enabled: try LLM grading with timeout
        try:
            llm_grade = await asyncio.wait_for(
                self._grade_llm(query, chunks),
                timeout=settings.rag_grader_timeout,
            )
            if llm_grade is not None:
                return llm_grade
        except Exception as exc:
            logger.warning("Optional LLM grader failed or timed out (%s), using deterministic grade", exc)

        return det_grade


def _extract_json(text: str) -> dict | None:
    """Extract the first valid JSON object from a string."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass
    return None


def _heuristic_grade(chunks: list[RetrievalResult], threshold: float) -> GradeResult:
    """Score-based fallback grade: backward compatibility wrapper."""
    return evaluate_deterministic_confidence(chunks, threshold=threshold)
