"""Knowledge Search Tool for TARK AI using Hybrid (Vector + Keyword) retrieval."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Type
from uuid import UUID
from pydantic import BaseModel, Field

from app.db.session import get_db_session
from app.services.retrieval.hybrid import HybridRetriever
from app.tools.base import BaseTool, ToolExecutionContext, ToolPermission, ToolResult

logger = logging.getLogger(__name__)


class KnowledgeSearchInput(BaseModel):
    query: str = Field(
        ...,
        description="Search query to find relevant documents, notes, manuals, and ingested workspace knowledge.",
        min_length=1,
        max_length=300,
    )
    top_k: int = Field(default=5, description="Number of knowledge chunks to retrieve (1-10).", ge=1, le=10)


class KnowledgeSearchTool(BaseTool):
    name: str = "search_knowledge_base"
    description: str = (
        "Search through indexed enterprise/project documents, knowledge base files, and uploaded resources. "
        "Use this whenever the user asks about documentation, uploaded PDFs/files, project specifications, or workspace facts."
    )
    permission: ToolPermission = ToolPermission.USER_DATA
    input_schema: Type[BaseModel] = KnowledgeSearchInput

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
                results = await self._run_search(context.session, query, user_id, context.project_id, top_k)
            else:
                async with get_db_session() as session:
                    results = await self._run_search(session, query, user_id, context.project_id, top_k)

            formatted_results = [
                {
                    "file_name": getattr(r, "file_name", None) or (r.metadata.get("filename") if r.metadata else None) or (r.metadata.get("file_name") if r.metadata else None) or "document",
                    "content": r.content,
                    "chunk_index": r.chunk_index,
                    "similarity_score": round(r.similarity_score, 4),
                }
                for r in results
            ]

            return ToolResult(
                tool_name=self.name,
                success=True,
                data={
                    "query": query,
                    "count": len(formatted_results),
                    "results": formatted_results,
                },
                source=f"TARK AI Hybrid Knowledge Base ({len(formatted_results)} chunks retrieved)",
            )

        except Exception as exc:
            logger.exception("Error in KnowledgeSearchTool: %s", exc)
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=f"Knowledge retrieval error: {str(exc)}",
                source="TARK AI Knowledge Base",
            )

    async def _run_search(self, session, query: str, user_id: UUID, project_id: Optional[UUID], top_k: int):
        try:
            retriever = HybridRetriever()
            return await retriever.search(
                session=session,
                query=query,
                user_id=user_id,
                project_id=project_id,
                top_k=top_k,
            )
        except Exception as err:
            logger.warning("HybridRetriever search failed, falling back to keyword search: %s", err)
            from app.services.retrieval.keyword import KeywordRetriever
            return await KeywordRetriever().search(
                session=session,
                query=query,
                user_id=user_id,
                project_id=project_id,
                top_k=top_k,
            )

