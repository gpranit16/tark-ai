import asyncio
import logging
from typing import TYPE_CHECKING

from app.core.config import get_settings
from app.core.enums import ConversationMode, MessageRole
from app.providers.base import NormalizedMessage

if TYPE_CHECKING:
    from app.services.chat.router import ModelRouter

logger = logging.getLogger(__name__)

_REWRITER_SYSTEM = """\
You are a query expansion specialist for document retrieval systems.
Your task is to rewrite a search query to improve retrieval from a document database.

Rules:
1. Preserve the original intent — do not change what is being asked.
2. Expand abbreviations and acronyms where applicable.
3. Remove ambiguity by being more specific.
4. Use synonyms and related terms that may appear in technical documents.
5. Do NOT add new requirements not present in the original query.
6. Output ONLY the rewritten query — no explanation, no preamble.
"""


class QueryRewriter:
    """Rewrites a query to improve document retrieval coverage.

    Only called when initial retrieval grades as insufficient.
    Uses ModelRouter with FAST mode for low-latency rewriting.
    """

    def __init__(self, router: "ModelRouter | None" = None):
        self._router = router

    def _get_router(self) -> "ModelRouter":
        if self._router is None:
            from app.services.chat.router import ModelRouter
            self._router = ModelRouter.from_settings()
        return self._router

    async def _do_rewrite(self, query: str, context_hint: str = "") -> str:
        hint_part = ""
        if context_hint:
            hint_part = f"\nContext: The previous search found insufficient evidence because: {context_hint}"

        user_prompt = f"Original query: {query}{hint_part}\n\nRewritten query:"

        messages = [
            NormalizedMessage(role=MessageRole.SYSTEM, content=_REWRITER_SYSTEM),
            NormalizedMessage(role=MessageRole.USER, content=user_prompt),
        ]

        router = self._get_router()
        settings = get_settings()
        tokens: list[str] = []
        async for _selection, event in router.stream(
            messages=messages,
            mode=ConversationMode.FAST,
            max_tokens=settings.rag_rewrite_max_output_tokens,
        ):
            if event.delta:
                tokens.append(event.delta)

        rewritten = "".join(tokens).strip()
        if not rewritten or len(rewritten) > 500:
            logger.warning("Query rewriter returned invalid output, using original")
            return query

        logger.info("Query rewritten: %r → %r", query, rewritten)
        return rewritten

    async def rewrite(self, query: str, context_hint: str = "") -> str:
        """Rewrite the query for better document retrieval with timeout protection."""
        settings = get_settings()
        try:
            return await asyncio.wait_for(
                self._do_rewrite(query, context_hint),
                timeout=settings.rag_rewrite_timeout,
            )
        except Exception as exc:
            logger.warning("Query rewriting failed or timed out (%s), using original query", exc)
            return query
