import json
import time
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.enums import ConversationMode, GenerationStatus, MessageRole
from app.models.conversation import Message, Thread
from app.models.file import File
from app.providers.base import ProviderError, ProviderErrorCode, ProviderStreamEvent, UsageMetadata
from app.schemas.chat import ChatRequest
from app.services import messages as message_service
from app.services.chat.context import normalize_messages
from app.services.chat.router import ModelRouter, ProviderSelection
from app.services.chat.sse import (
    MessageCompletePayload,
    error_event,
    memory_forgotten,
    memory_saved,
    message_complete,
    message_start,
    text_delta,
)
from app.services.threads import get_thread_or_404


class ChatService:
    def __init__(self, router: ModelRouter | None = None) -> None:
        self.router = router or ModelRouter.from_settings()
        self.settings = get_settings()

    async def _get_attachments(self, session: AsyncSession, file_ids: list[UUID] | None) -> list[dict]:
        if not file_ids:
            return []
        records = (await session.execute(
            select(File).where(File.id.in_(file_ids))
        )).scalars().all()
        return [
            {
                "file_id": str(f.id),
                "filename": f.original_filename,
                "mime_type": f.mime_type,
                "size_bytes": f.size_bytes,
                "storage_key": f.storage_key,
            }
            for f in records
        ]

    async def stream_chat(
        self,
        *,
        session: AsyncSession,
        thread_id: UUID,
        payload: ChatRequest,
        is_disconnected,
    ) -> AsyncIterator[str]:
        thread = await get_thread_or_404(session, thread_id)
        thread.updated_at = datetime.now(timezone.utc)
        attachments_data = await self._get_attachments(session, payload.file_ids)
        user_message = Message(
            thread_id=thread.id,
            role=MessageRole.USER,
            content=payload.content,
            mode=payload.mode,
            attachments=attachments_data,
            generation_status=GenerationStatus.COMPLETED,
        )
        session.add(user_message)
        await session.commit()
        await session.refresh(user_message)

        is_temp = thread.is_temporary or bool(payload.is_temporary)

        history = await message_service.list_messages(
            session,
            thread_id=thread.id,
            limit=self.settings.max_context_messages,
            offset=0,
        )

        # Check for explicit GPT-style memory commands (remember, forget, query, clear)
        if self.settings.memory_enabled and not is_temp:
            from app.services.memory.extractor import ExplicitIntent, MemoryExtractor
            from app.services.memory.service import MemoryService
            from app.services.settings import settings_service

            user_settings = await settings_service.get_or_create_user_settings(session, thread.user_id)
            if user_settings.explicit_memory_enabled:
                extractor = MemoryExtractor()
                mem_cmd = extractor.detect_explicit_command(payload.content)
                if mem_cmd.intent != ExplicitIntent.NONE:
                    mem_svc = MemoryService(session)
                    resp_text, evt_type, evt_payload = await mem_svc.handle_explicit_memory_command(
                        user_id=thread.user_id,
                        command=mem_cmd,
                        project_id=thread.project_id,
                        recent_messages=history,
                        source=f"thread:{thread.id}",
                    )
                    yield message_start(payload.provider or "groq", payload.model or "llama-3.1-8b-instant", payload.mode, False)
                    if evt_type == "memory_saved" and evt_payload:
                        yield memory_saved(
                            key=evt_payload.get("key", "note"),
                            value=evt_payload.get("value", ""),
                            category=evt_payload.get("category", "preference"),
                            explicit=evt_payload.get("explicit", True),
                        )
                    elif evt_type == "memory_forgotten" and evt_payload:
                        yield memory_forgotten(
                            key=evt_payload.get("key", "note"),
                            value=evt_payload.get("value", ""),
                        )

                    words = resp_text.split(" ")
                    for i, w in enumerate(words):
                        part = w + (" " if i < len(words) - 1 else "")
                        yield text_delta(part)

                    assistant = await self._persist_assistant(
                        session,
                        thread_id=thread.id,
                        content=resp_text,
                        selection=None,
                        status=GenerationStatus.COMPLETED,
                        usage=UsageMetadata(),
                        latency_ms=0,
                        finish_reason="stop",
                        mode=payload.mode,
                        provider=payload.provider or "groq",
                        model=payload.model or "qwen/qwen3.8-27b",
                    )
                    yield message_complete(
                        MessageCompletePayload(
                            message_id=assistant.id,
                            provider=payload.provider or "groq",
                            model=payload.model or "llama-3.1-8b-instant",
                            mode=payload.mode,
                            finish_reason="stop",
                            fallback_used=False,
                        )
                    )
                    return

        # Load Project if thread is associated with a project
        project = None
        if thread.project_id:
            from app.models.conversation import Project
            project = await session.get(Project, thread.project_id)

        # Retrieve relevant long-term memories if enabled and not temporary
        memory_context: str | None = None
        if self.settings.memory_enabled and (not is_temp or self.settings.temporary_chat_memory_enabled):
            from app.services.memory.retriever import MemoryRetriever
            retriever = MemoryRetriever(session)
            memories = await retriever.retrieve_relevant_memories(
                user_id=thread.user_id,
                query=payload.content,
                project_id=thread.project_id,
                top_k=self.settings.memory_top_k,
            )
            memory_context = retriever.format_memory_context(memories)

        from app.services.chat.project_context import ProjectContextBuilder
        context_builder = ProjectContextBuilder(
            project=project,
            memory_context=memory_context,
            thread_summary=thread.summary,
        )
        context = context_builder.assemble(history[-self.settings.max_context_messages :])
        self._validate_context(context)
        assistant_text: list[str] = []
        latest_selection: ProviderSelection | None = None
        latest_usage = UsageMetadata()
        finish_reason = "stop"
        start = time.perf_counter()

        try:
            if self.settings.tool_calling_enabled:
                from app.services.chat.tool_loop import ToolCallOrchestrator
                from app.tools.base import ToolExecutionContext

                tool_context = ToolExecutionContext(
                    user_id=thread.user_id,
                    project_id=thread.project_id,
                    thread_id=thread.id,
                    session=session,
                )
                orchestrator = ToolCallOrchestrator(self.router)

                async for sse_chunk in orchestrator.run_tool_loop(
                    messages=context,
                    mode=payload.mode,
                    provider=payload.provider,
                    model=payload.model,
                    context=tool_context,
                    is_disconnected=is_disconnected,
                ):
                    yield sse_chunk

                    # Parse deltas and provider info for database persistence
                    if sse_chunk.startswith("event: text_delta\n"):
                        try:
                            lines = sse_chunk.strip().split("\n")
                            for line in lines:
                                if line.startswith("data: "):
                                    d_json = json.loads(line[6:])
                                    if "delta" in d_json:
                                        assistant_text.append(d_json["delta"])
                        except Exception:
                            pass
                    elif sse_chunk.startswith("event: message_start\n"):
                        try:
                            lines = sse_chunk.strip().split("\n")
                            for line in lines:
                                if line.startswith("data: "):
                                    p_json = json.loads(line[6:])
                                    p_name = p_json.get("provider", "groq")
                                    p_model = p_json.get("model", "llama-3.1-8b-instant")
                                    prov_instance = None
                                    if self.router.providers:
                                        prov_instance = self.router.providers.get(p_name) or next(iter(self.router.providers.values()), None)
                                    latest_selection = ProviderSelection(
                                        provider=prov_instance,
                                        provider_name=p_name,
                                        model=p_model,
                                        fallback_used=p_json.get("fallback_used", False),
                                    )
                        except Exception:
                            pass
            else:
                async for selection, event in self.router.stream(
                    messages=context,
                    mode=payload.mode,
                    provider=payload.provider,
                    model=payload.model,
                ):
                    if latest_selection is None or latest_selection.provider_name != selection.provider_name:
                        latest_selection = selection
                        yield message_start(selection.provider_name, selection.model, payload.mode, selection.fallback_used)
                    if await is_disconnected():
                        await self._persist_assistant(
                            session,
                            thread_id=thread.id,
                            content="".join(assistant_text),
                            selection=latest_selection,
                            status=GenerationStatus.CANCELLED,
                            usage=latest_usage,
                            latency_ms=_latency_ms(start),
                            finish_reason="cancelled",
                            mode=payload.mode,
                        )
                        return
                    latest_usage = _merge_usage(latest_usage, event)
                    if event.finish_reason:
                        finish_reason = event.finish_reason
                    if event.delta:
                        assistant_text.append(event.delta)
                        yield text_delta(event.delta)

            if latest_selection is None:
                try:
                    latest_selection = self.router.select(
                        mode=payload.mode,
                        provider=payload.provider,
                        model=payload.model,
                    )
                except Exception:
                    latest_selection = ProviderSelection(
                        provider=None,
                        provider_name=getattr(payload, "provider", None) or "groq",
                        model=getattr(payload, "model", None) or "llama-3.1-8b-instant",
                    )


            assistant = await self._persist_assistant(
                session,
                thread_id=thread.id,
                content="".join(assistant_text),
                selection=latest_selection,
                status=GenerationStatus.COMPLETED,
                usage=latest_usage,
                latency_ms=_latency_ms(start),
                finish_reason=finish_reason,
                mode=payload.mode,
            )

            # Post-generation memory extraction and thread summarization
            if self.settings.memory_enabled and not is_temp:
                try:
                    from app.services.memory.extractor import MemoryExtractor
                    from app.services.memory.service import MemoryService
                    from app.services.memory.summarizer import ThreadSummaryService
                    from app.services.settings import settings_service

                    user_settings = await settings_service.get_or_create_user_settings(session, thread.user_id)

                    if user_settings.smart_memory_enabled:
                        extractor = MemoryExtractor()
                        ext_result = extractor.extract(payload.content, is_rag_query=False)
                        if ext_result.candidates:
                            mem_svc = MemoryService(session)
                            stored_memories = await mem_svc.process_and_store_candidates(
                                user_id=thread.user_id,
                                candidates=ext_result.candidates,
                                project_id=thread.project_id,
                                source=f"thread:{thread.id}",
                            )
                            for sm in stored_memories:
                                yield memory_saved(sm.key, sm.value, sm.category.value, explicit=False)

                    # Incremental thread summary check
                    summarizer = ThreadSummaryService(session)
                    await summarizer.maybe_update_thread_summary(
                        thread.id,
                        threshold=self.settings.thread_summary_threshold,
                    )
                except Exception:
                    # Non-blocking background memory extraction failure
                    pass


            yield message_complete(
                MessageCompletePayload(
                    message_id=assistant.id,
                    provider=latest_selection.provider_name,
                    model=latest_selection.model,
                    mode=payload.mode,
                    finish_reason=finish_reason,
                    fallback_used=latest_selection.fallback_used,
                )
            )
        except ProviderError as exc:
            if latest_selection is not None:
                await self._persist_assistant(
                    session,
                    thread_id=thread.id,
                    content="".join(assistant_text),
                    selection=latest_selection,
                    status=GenerationStatus.FAILED,
                    usage=latest_usage,
                    latency_ms=_latency_ms(start),
                    finish_reason="error",
                    mode=payload.mode,
                )
            yield error_event(exc)

    async def _persist_assistant(
        self,
        session: AsyncSession,
        *,
        thread_id: UUID,
        content: str,
        selection: ProviderSelection | None,
        status: GenerationStatus,
        usage: UsageMetadata,
        latency_ms: int,
        finish_reason: str,
        mode: ConversationMode,
        provider: str | None = None,
        model: str | None = None,
    ) -> Message:
        provider_name = provider
        model_name = model
        if selection is not None:
            provider_name = getattr(selection.provider_name, "value", selection.provider_name)
            model_name = selection.model

        thread = await session.get(Thread, thread_id)
        if thread is not None:
            thread.updated_at = datetime.now(timezone.utc)

        message = Message(
            thread_id=thread_id,
            role=MessageRole.ASSISTANT,
            content=content,
            provider=provider_name,
            model=model_name,
            mode=mode,
            generation_status=status,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            total_tokens=usage.total_tokens,
            latency_ms=latency_ms,
        )
        session.add(message)
        await session.commit()
        await session.refresh(message)
        return message

    def _validate_context(self, messages: list[object]) -> None:
        if len(messages) > self.settings.max_context_messages:
            raise ProviderError(
                ProviderErrorCode.CONTEXT_LIMIT,
                "Context exceeds the configured message limit",
                retryable=False,
            )


    async def stream_rag_chat(
        self,
        *,
        session: AsyncSession,
        thread_id: UUID,
        payload: ChatRequest,
        is_disconnected,
        user_id: UUID,
    ) -> AsyncIterator[str]:
        """Stream a RAG-grounded response for the given thread.

        Runs the full CRAG pipeline (retrieve → rerank → grade → CRAG →
        answer) and emits RAG SSE events interleaved with the standard
        message_start / message_complete lifecycle events.

        Falls back to normal chat if no document chunks exist for the user.
        """
        from app.services.chat.sse import (
            rag_citation,
            rag_generating,
            rag_grading,
            rag_message_complete,
            rag_query_rewrite,
            rag_crag_retry,
            rag_reranking_complete,
            rag_reranking_started,
            rag_retrieval_complete,
            rag_retrieval_started,
        )
        from app.services.rag.crag import CRAGOrchestrator
        from app.models.conversation import Message as MsgModel

        thread = await get_thread_or_404(session, thread_id)
        thread.updated_at = datetime.now(timezone.utc)
        attachments_data = await self._get_attachments(session, payload.file_ids)

        # Persist the user message
        user_message = MsgModel(
            thread_id=thread.id,
            role=MessageRole.USER,
            content=payload.content,
            mode=payload.mode,
            attachments=attachments_data,
            generation_status=GenerationStatus.COMPLETED,
        )
        session.add(user_message)
        await session.commit()
        await session.refresh(user_message)

        # Emit pipeline events
        yield rag_retrieval_started(payload.content)

        try:
            orchestrator = CRAGOrchestrator()
            result = await orchestrator.run(
                query=payload.content,
                user_id=user_id,
                session=session,
                project_id=thread.project_id,
                file_ids=payload.file_ids,
                top_k=self.settings.retrieval_top_k,
                thread_id=thread.id,
            )
        except Exception as exc:
            from app.providers.base import ProviderError, ProviderErrorCode
            err = ProviderError(ProviderErrorCode.UNKNOWN, str(exc), retryable=False)
            yield error_event(err)
            return

        yield rag_retrieval_complete(result.retrieved_count)
        yield rag_reranking_started()
        yield rag_reranking_complete(result.reranked_count)
        yield rag_grading(result.grading_confidence, result.decision == "grounded")

        if result.query_rewritten:
            yield rag_query_rewrite(result.original_query, result.final_query)

        # Emit citations
        for cit in result.citations:
            yield rag_citation(cit.model_dump(mode="json"))

        yield rag_generating()

        # Stream the answer word-by-word to simulate streaming
        answer = result.answer
        for word in answer.split(" "):
            yield text_delta(word + " ")

        # Persist assistant message
        assistant = await self._persist_assistant(
            session,
            thread_id=thread.id,
            content=answer,
            selection=None,
            status=GenerationStatus.COMPLETED,
            usage=UsageMetadata(),
            latency_ms=0,
            finish_reason="stop",
            mode=payload.mode,
        )

        yield rag_message_complete(
            answer=answer,
            citations=[c.model_dump(mode="json") for c in result.citations],
            retrieved=result.retrieved_count,
            reranked=result.reranked_count,
            confidence=result.grading_confidence,
            attempts=result.crag_attempts,
            rewritten=result.query_rewritten,
            decision=result.decision,
        )


def _merge_usage(current: UsageMetadata, event: ProviderStreamEvent) -> UsageMetadata:
    usage = event.usage
    return UsageMetadata(
        input_tokens=usage.input_tokens if usage.input_tokens is not None else current.input_tokens,
        output_tokens=usage.output_tokens if usage.output_tokens is not None else current.output_tokens,
        total_tokens=usage.total_tokens if usage.total_tokens is not None else current.total_tokens,
    )


def _latency_ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)

