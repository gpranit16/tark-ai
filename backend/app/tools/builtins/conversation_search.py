"""Conversation History Search Tool for TARK AI. Search past threads and messages."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Type
from uuid import UUID
from pydantic import BaseModel, Field
from sqlalchemy import desc, or_, select

from app.db.session import get_db_session
from app.models.conversation import Message, Thread
from app.tools.base import BaseTool, ToolExecutionContext, ToolPermission, ToolResult

logger = logging.getLogger(__name__)


class ConversationSearchInput(BaseModel):
    query: str = Field(
        ...,
        description="Keyword or topic to search across past conversation threads and messages.",
        min_length=1,
        max_length=200,
    )
    max_results: int = Field(default=5, description="Maximum number of message snippets to return (1-10).", ge=1, le=10)


class ConversationSearchTool(BaseTool):
    name: str = "search_conversation_history"
    description: str = (
        "Search past conversation history, prior discussion threads, and historical messages for this user. "
        "Use this whenever the user asks 'what did we discuss earlier?', 'find that link from last week', or references past chat threads."
    )
    permission: ToolPermission = ToolPermission.USER_DATA
    input_schema: Type[BaseModel] = ConversationSearchInput

    async def execute(self, arguments: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        query = arguments.get("query", "").strip()
        max_results = min(int(arguments.get("max_results", 5)), 10)

        if not query:
            return ToolResult(tool_name=self.name, success=False, error="Query is required.")

        user_id = context.user_id
        if not user_id:
            return ToolResult(tool_name=self.name, success=False, error="User authentication context is required.")

        try:
            if context.session:
                results = await self._run_search(context.session, query, user_id, context.thread_id, max_results)
            else:
                async with get_db_session() as session:
                    results = await self._run_search(session, query, user_id, context.thread_id, max_results)

            return ToolResult(
                tool_name=self.name,
                success=True,
                data={
                    "query": query,
                    "count": len(results),
                    "conversations": results,
                },
                source=f"TARK AI Conversation History ({len(results)} matches)",
            )

        except Exception as exc:
            logger.exception("Error in ConversationSearchTool: %s", exc)
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=f"Conversation history search error: {str(exc)}",
                source="TARK AI Conversation History",
            )

    async def _run_search(
        self,
        session,
        query: str,
        user_id: UUID,
        current_thread_id: Optional[UUID],
        limit: int,
    ) -> List[Dict[str, Any]]:
        # Find messages matching query belonging to threads owned by user_id
        stmt = (
            select(Message, Thread.title)
            .join(Thread, Message.thread_id == Thread.id)
            .where(
                Thread.user_id == user_id,
                Message.content.ilike(f"%{query}%"),
            )
            .order_by(desc(Message.created_at))
            .limit(limit)
        )

        result = await session.execute(stmt)
        rows = result.all()

        formatted = []
        for msg, thread_title in rows:
            content_preview = msg.content[:300] + "..." if len(msg.content) > 300 else msg.content
            formatted.append({
                "thread_id": str(msg.thread_id),
                "thread_title": thread_title or "Untitled Thread",
                "role": msg.role,
                "snippet": content_preview,
                "created_at": msg.created_at.isoformat() if msg.created_at else None,
                "is_current_thread": (msg.thread_id == current_thread_id) if current_thread_id else False,
            })

        return formatted
