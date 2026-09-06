from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.conversation import Message, Thread
from app.services.threads import get_thread_or_404


class ThreadSummaryService:
    """Incrementally generates and updates short-term thread summaries for long conversations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.settings = get_settings()

    async def maybe_update_thread_summary(
        self,
        thread_id: UUID,
        threshold: int | None = None,
        recent_window: int = 6,
    ) -> str | None:
        """Check if message count exceeds threshold, and incrementally generate/update summary."""
        limit_threshold = threshold or self.settings.thread_summary_threshold

        thread = await get_thread_or_404(self.session, thread_id)

        # Fetch all messages in the thread ordered by created_at
        stmt = (
            select(Message)
            .where(Message.thread_id == thread_id)
            .order_by(Message.created_at.asc())
        )
        result = await self.session.scalars(stmt)
        messages = list(result.all())

        total_msgs = len(messages)
        if total_msgs < limit_threshold:
            return thread.summary

        # Identify messages to summarize (all except the last recent_window messages)
        msgs_to_summarize = messages[:-recent_window] if total_msgs > recent_window else []
        if not msgs_to_summarize:
            return thread.summary

        last_summarized_msg = msgs_to_summarize[-1]

        # If already summarized up to or past this message, no update needed
        if thread.summarized_message_id == last_summarized_msg.id:
            return thread.summary

        # Build concise structured summary of the conversation
        summary_bullets: list[str] = []
        if thread.summary:
            summary_bullets.append(f"Prior Context: {thread.summary}")

        for msg in msgs_to_summarize:
            content_preview = msg.content.strip().replace("\n", " ")
            if len(content_preview) > 150:
                content_preview = content_preview[:147] + "..."
            role_label = "User" if msg.role.value == "user" else "Assistant"
            summary_bullets.append(f"- {role_label}: {content_preview}")

        # Condense into clean bullet summary
        condensed_summary = "\n".join(summary_bullets)
        if len(condensed_summary) > 2000:
            condensed_summary = condensed_summary[-2000:]

        thread.summary = condensed_summary
        thread.summarized_message_id = last_summarized_msg.id
        thread.summary_updated_at = datetime.now(timezone.utc)

        await self.session.commit()
        await self.session.refresh(thread)
        return thread.summary
