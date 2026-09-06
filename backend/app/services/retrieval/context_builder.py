from uuid import UUID

from app.core.config import get_settings
from app.schemas.retrieval import CitationSource, ContextBuildResponse, RetrievalResult


class ContextBuilder:
    def __init__(self, default_max_tokens: int | None = None):
        settings = get_settings()
        self.default_max_tokens = default_max_tokens or settings.max_context_tokens

    def build_context(
        self,
        query: str,
        chunks: list[RetrievalResult],
        max_tokens: int | None = None,
        allowed_file_ids: list[UUID] | None = None,
    ) -> ContextBuildResponse:
        limit_tokens = max_tokens or self.default_max_tokens
        max_chars = limit_tokens * 4  # Approximation: 1 token ~ 4 characters

        allowed_set = set(allowed_file_ids) if allowed_file_ids else None
        seen_content_hashes: set[int] = set()
        context_blocks: list[str] = []
        sources: list[CitationSource] = []
        total_chars = 0

        for chunk in chunks:
            # Strict scope guard: reject any chunk from outside allowed_file_ids
            if allowed_set is not None and chunk.file_id not in allowed_set:
                continue

            content_clean = chunk.content.strip()
            content_hash = hash(content_clean)
            if content_hash in seen_content_hashes:
                continue
            seen_content_hashes.add(content_hash)

            filename = chunk.metadata.get("filename", "document")
            header = f"[Source: {filename} | Page: {chunk.page_number} | Chunk: {chunk.chunk_index}]"
            block = f"{header}\n{content_clean}"

            if total_chars + len(block) > max_chars and context_blocks:
                break

            context_blocks.append(block)
            total_chars += len(block) + 2

            # Build citation source
            snippet = (content_clean[:150] + "...") if len(content_clean) > 150 else content_clean
            sources.append(
                CitationSource(
                    chunk_id=chunk.chunk_id,
                    file_id=chunk.file_id,
                    filename=filename,
                    page_number=chunk.page_number,
                    chunk_index=chunk.chunk_index,
                    similarity_score=chunk.similarity_score,
                    snippet=snippet,
                )
            )

        full_context_text = "\n\n---\n\n".join(context_blocks)

        return ContextBuildResponse(
            query=query,
            context_text=full_context_text,
            sources=sources,
            total_chunks_used=len(context_blocks),
        )
