"""RAGAnswerGenerator — generates grounded answers from document context.

Uses the existing ModelRouter and provider abstraction.
Applies a strict grounding system prompt that prohibits hallucination.
Supports both streaming (async generator) and non-streaming modes.
"""
import logging
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from app.core.enums import ConversationMode, MessageRole
from app.providers.base import NormalizedMessage
from app.schemas.rag import RAGCitation

if TYPE_CHECKING:
    from app.services.chat.router import ModelRouter

logger = logging.getLogger(__name__)

_GROUNDING_SYSTEM = """\
You are a document-grounded AI assistant. You answer questions strictly based on
the provided document evidence. You must follow these rules at all times:

1. Answer ONLY using the supplied document evidence in the context sections below.
2. Do NOT invent, fabricate, or hallucinate document facts.
3. Do NOT treat your own training knowledge as document evidence.
4. Cite document-specific claims using the format [Source: filename | Page: N].
5. When evidence from different sources conflicts, explicitly explain the conflict
   and cite both sources. Do not arbitrarily resolve the conflict.
6. When the evidence is insufficient or absent, state clearly:
   "Based on the provided documents, I cannot find sufficient evidence to answer this."
7. Never create fake citations. Only reference sources that appear in the context.

The document context is provided below, formatted as labeled sections.
"""


class RAGAnswerGenerator:
    """Generates grounded answers using document context and citations.

    Streams tokens via the ModelRouter using ConversationMode.RAG,
    falling back to NORMAL mode if RAG provider is not configured.
    """

    def __init__(self, router: "ModelRouter | None" = None):
        self._router = router

    def _get_router(self) -> "ModelRouter":
        if self._router is None:
            from app.services.chat.router import ModelRouter
            self._router = ModelRouter.from_settings()
        return self._router

    async def stream_answer(
        self,
        query: str,
        context_text: str,
        citations: list[RAGCitation],
        scoped_filenames: list[str] | None = None,
    ) -> AsyncIterator[str]:
        """Stream the grounded answer token by token.

        Yields individual text tokens (deltas) from the LLM.
        The caller is responsible for accumulating and persisting the full answer.
        """
        doc_header = f"TARGET DOCUMENT(S): {', '.join(scoped_filenames)}\n\n" if scoped_filenames else ""
        doc_instruction = (
            f"Answer the question using only the document evidence above for {', '.join(scoped_filenames)}. "
            f"If the requested information is not present in {', '.join(scoped_filenames)}, state clearly that it is not present in {', '.join(scoped_filenames)}. "
            "Do NOT reference or invent information from any other documents."
            if scoped_filenames
            else "Answer the question using only the document evidence above."
        )

        user_prompt = (
            f"{doc_header}DOCUMENT CONTEXT:\n\n{context_text}\n\n"
            f"---\n\n"
            f"QUESTION: {query}\n\n"
            f"{doc_instruction}"
        )

        messages = [
            NormalizedMessage(role=MessageRole.SYSTEM, content=_GROUNDING_SYSTEM),
            NormalizedMessage(role=MessageRole.USER, content=user_prompt),
        ]

        router = self._get_router()
        from app.core.config import get_settings
        settings = get_settings()
        out_tokens = settings.rag_max_output_tokens

        try:
            try:
                async for _selection, event in router.stream(
                    messages=messages,
                    mode=ConversationMode.RAG,
                    max_tokens=out_tokens,
                ):
                    if event.delta:
                        yield event.delta
            except Exception:
                # Fallback to NORMAL mode
                async for _selection, event in router.stream(
                    messages=messages,
                    mode=ConversationMode.NORMAL,
                    max_tokens=out_tokens,
                ):
                    if event.delta:
                        yield event.delta
        except Exception as exc:
            logger.warning("Answer generation LLM stream failed: %s", exc)
            yield f"Based on the available context, here is the relevant information retrieved for your query:\n\n{context_text[:300]}..."

    async def generate_answer(
        self,
        query: str,
        context_text: str,
        citations: list[RAGCitation],
        scoped_filenames: list[str] | None = None,
    ) -> str:
        """Non-streaming version — collects full answer and returns it."""
        tokens: list[str] = []
        async for token in self.stream_answer(query, context_text, citations, scoped_filenames=scoped_filenames):
            tokens.append(token)
        return "".join(tokens)
