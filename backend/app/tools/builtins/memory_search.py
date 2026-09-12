"""Memory Search Tool for TARK AI using Phase 8 MemoryRetriever and Repository."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Type
from uuid import UUID
from pydantic import BaseModel, Field

from app.db.session import get_db_session
from app.services.memory.retriever import MemoryRetriever
from app.tools.base import BaseTool, ToolExecutionContext, ToolPermission, ToolResult

logger = logging.getLogger(__name__)


class MemorySearchInput(BaseModel):
    query: str = Field(
        ...,
        description="Topic or query to find remembered user facts, preferences, background, skills, or instructions.",
        min_length=1,
        max_length=200,
    )
    top_k: int = Field(default=5, description="Maximum number of memory facts to return (1-10).", ge=1, le=10)


class MemorySearchTool(BaseTool):
    name: str = "search_user_memory"
    description: str = (
        "Search stored long-term memory facts, persistent preferences, and user background from PREVIOUS past sessions. "
        "DO NOT use this tool if the fact or topic was already stated in the CURRENT ongoing conversation thread. "
        "Use this only when the fact is absent from the current thread and refers to persistent historical profile info."
    )
    permission: ToolPermission = ToolPermission.USER_DATA
    input_schema: Type[BaseModel] = MemorySearchInput

    async def execute(self, arguments: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        query = arguments.get("query", "").strip()
        top_k = min(int(arguments.get("top_k", 5)), 10)

        if not query:
            return ToolResult(tool_name=self.name, success=False, error="Query is required.")

        user_id = context.user_id
        if not user_id:
            return ToolResult(tool_name=self.name, success=False, error="User authentication context is required.")

        try:
            if context.session:
                memories = await self._run_search(context.session, query, user_id, context.project_id, top_k)
            else:
                async with get_db_session() as session:
                    memories = await self._run_search(session, query, user_id, context.project_id, top_k)

            formatted = [
                {
                    "category": m.category.value if hasattr(m.category, "value") else str(m.category),
                    "key": m.key,
                    "value": m.value,
                    "importance": m.importance,
                    "confidence": m.confidence,
                }
                for m in memories
            ]

            return ToolResult(
                tool_name=self.name,
                success=True,
                data={
                    "query": query,
                    "count": len(formatted),
                    "memories": formatted,
                },
                source=f"TARK AI User Long-Term Memory ({len(formatted)} facts)",
            )

        except Exception as exc:
            logger.exception("Error in MemorySearchTool: %s", exc)
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=f"Memory retrieval error: {str(exc)}",
                source="TARK AI Memory System",
            )

    async def _run_search(self, session, query: str, user_id: UUID, project_id: Optional[UUID], top_k: int):
        retriever = MemoryRetriever(session)
        return await retriever.retrieve_relevant_memories(
            user_id=user_id,
            query=query,
            project_id=project_id,
            top_k=top_k,
        )
