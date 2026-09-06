import re
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.enums import MemoryCategory
from app.models.memory import Memory
from app.services.memory.repository import MemoryRepository


class MemoryRetriever:
    """Retrieves relevant user and project long-term memories for personalized chat responses."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = MemoryRepository(session)
        self.settings = get_settings()

    async def retrieve_relevant_memories(
        self,
        user_id: UUID,
        query: str,
        project_id: UUID | None = None,
        top_k: int | None = None,
    ) -> list[Memory]:
        """Fetch active memories for user_id within project scope that are relevant to query."""
        if not self.settings.memory_enabled:
            return []

        limit = top_k or self.settings.memory_top_k

        # Fetch all active candidate memories for user (global + current project)
        all_candidates = await self.repository.list_for_user(
            user_id=user_id,
            project_id=project_id,
            include_global=True,
            is_active=True,
            limit=50,
            offset=0,
        )

        if not all_candidates:
            return []

        # Score candidates for relevance
        query_words = set(re.findall(r"\w+", query.lower()))
        scored: list[tuple[float, Memory]] = []

        for mem in all_candidates:
            # Calculate word overlap
            mem_text = f"{mem.key} {mem.value} {mem.category.value}".lower()
            mem_words = set(re.findall(r"\w+", mem_text))
            overlap = len(query_words.intersection(mem_words))

            # Base relevance score
            # Universal preferences (e.g. response_style, explanation_style) get baseline priority
            base_score = mem.importance * mem.confidence

            if mem.category == MemoryCategory.PREFERENCE and mem.key in ("response_style", "formatting_preference", "explanation_style"):
                # Only apply response style if prompt is not a single-word ping or simple utility
                score = base_score + 1.0
            elif overlap > 0:
                score = base_score + (overlap * 0.8)
            else:
                # If zero overlap and not a universal style preference, don't inject
                score = 0.0

            if score > 0.4:
                scored.append((score, mem))

        # Sort by score descending
        scored.sort(key=lambda x: x[0], reverse=True)
        selected = [mem for _, mem in scored[:limit]]

        # Touch last accessed
        if selected:
            await self.repository.touch_last_accessed([m.id for m in selected])

        return selected

    def format_memory_context(self, memories: list[Memory]) -> str:
        """Format a list of memories into a prompt injection block."""
        if not memories:
            return ""

        lines = ["[User Personalization & Long-Term Memory]"]
        for mem in memories:
            scope = "Project" if mem.project_id else "Global"
            lines.append(f"- [{mem.category.value.upper()}] ({mem.key}): {mem.value} ({scope})")

        return "\n".join(lines)
