"""CodingService for Phase 12 Coding Mode.

Coordinates code-aware context assembly, ModelRouter invocation,
SSE event streaming, structured change extraction, and database persistence.
"""
from __future__ import annotations

import json
import re
import time
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any, List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.enums import ConversationMode, GenerationStatus, MessageRole
from app.models.conversation import Message, Project, Thread
from app.models.file import File
from app.providers.base import ProviderError, ProviderErrorCode, ProviderStreamEvent, UsageMetadata
from app.schemas.chat import ChatRequest
from app.services import messages as message_service
from app.services.chat.router import ModelRouter, ProviderSelection
from app.services.chat.sse import (
    MessageCompletePayload,
    coding_complete,
    coding_context_ready,
    coding_error,
    coding_file,
    coding_generation,
    coding_started,
    error_event,
    message_complete,
    message_start,
    text_delta,
)
from app.services.coding.context import CodeContextBuilder
from app.services.coding.models import (
    CodeChange,
    CodingQueryRequest,
    CodingQueryResponse,
    StructuredCodeResponse,
)
from app.services.threads import get_thread_or_404


def _latency_ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


def _merge_usage(current: UsageMetadata, event: ProviderStreamEvent) -> UsageMetadata:
    usage = event.usage
    return UsageMetadata(
        input_tokens=usage.input_tokens if usage.input_tokens is not None else current.input_tokens,
        output_tokens=usage.output_tokens if usage.output_tokens is not None else current.output_tokens,
        total_tokens=usage.total_tokens if usage.total_tokens is not None else current.total_tokens,
    )


def extract_diffs_from_text(text: str) -> list[CodeChange]:
    """Parse unified diff blocks and code change fences from assistant response."""
    diffs: list[CodeChange] = []

    # Match diff fences
    diff_pattern = re.compile(r"```diff\n(.*?)\n```", re.DOTALL)
    for match in diff_pattern.finditer(text):
        diff_content = match.group(1).strip()
        filename = "unknown"
        # Try to find filename from --- a/path or +++ b/path
        file_match = re.search(r"\+\+\+\s+(?:b/)?([^\s\n]+)", diff_content)
        if file_match:
            filename = file_match.group(1)
        diffs.append(
            CodeChange(
                file=filename,
                operation="modify",
                summary=f"Suggested diff for {filename}",
                diff=diff_content,
            )
        )

    # Match code blocks with file annotations: ```python:path/to/file.py
    file_block_pattern = re.compile(r"```([a-zA-Z0-9_-]+):([^\n]+)\n(.*?)\n```", re.DOTALL)
    for match in file_block_pattern.finditer(text):
        lang = match.group(1).strip()
        filename = match.group(2).strip()
        code_content = match.group(3)
        diffs.append(
            CodeChange(
                file=filename,
                operation="modify",
                summary=f"Updated implementation for {filename}",
                language=lang,
                code=code_content,
            )
        )

    return diffs


class CodingService:
    """Manages Coding Mode interactions with code-aware context and real-time streaming."""

    def __init__(self, router: ModelRouter | None = None) -> None:
        self.router = router or ModelRouter.from_settings()
        self.settings = get_settings()

    async def stream_coding_chat(
        self,
        *,
        session: AsyncSession,
        thread_id: UUID,
        payload: ChatRequest,
        is_disconnected,
        user_id: UUID,
    ) -> AsyncIterator[str]:
        """Stream a coding-specific response inside an existing thread."""
        thread = await get_thread_or_404(session, thread_id)
        is_temp = thread.is_temporary or bool(payload.is_temporary)

        # 1. Persist the user message
        thread.updated_at = datetime.now(timezone.utc)
        attachments_data = []
        if payload.file_ids:
            records = (await session.execute(
                select(File).where(File.id.in_(payload.file_ids))
            )).scalars().all()
            attachments_data = [
                {
                    "file_id": str(f.id),
                    "filename": f.original_filename,
                    "mime_type": f.mime_type,
                    "size_bytes": f.size_bytes,
                    "storage_key": f.storage_key,
                }
                for f in records
            ]

        user_message = Message(
            thread_id=thread.id,
            role=MessageRole.USER,
            content=payload.content,
            mode=ConversationMode.CODING,
            attachments=attachments_data,
            generation_status=GenerationStatus.COMPLETED,
        )
        session.add(user_message)
        await session.commit()
        await session.refresh(user_message)

        # 2. Load Project Workspace if thread belongs to project
        project: Optional[Project] = None
        if thread.project_id:
            project = await session.get(Project, thread.project_id)

        # 3. Retrieve relevant long-term memory
        memory_context: Optional[str] = None
        if self.settings.memory_enabled and (not is_temp or self.settings.temporary_chat_memory_enabled):
            try:
                from app.services.memory.retriever import MemoryRetriever
                retriever = MemoryRetriever(session)
                memories = await retriever.retrieve_relevant_memories(
                    user_id=user_id,
                    query=payload.content,
                    project_id=thread.project_id,
                    top_k=self.settings.memory_top_k,
                )
                memory_context = retriever.format_memory_context(memories)
            except Exception:
                pass

        # 4. Retrieve RAG documentation if relevant
        rag_context: Optional[str] = None
        if payload.file_ids or thread.project_id:
            try:
                from app.services.rag.crag import CRAGOrchestrator
                orchestrator = CRAGOrchestrator()
                crag_res = await orchestrator.run(
                    query=payload.content,
                    user_id=user_id,
                    session=session,
                    project_id=thread.project_id,
                    file_ids=payload.file_ids,
                    top_k=3,
                )
                if crag_res.retrieved_count > 0:
                    rag_context = f"[Grounding Documentation]\n{crag_res.answer}"
            except Exception:
                pass

        # 5. Build Code Context
        context_builder = CodeContextBuilder(
            project=project,
            memory_context=memory_context,
            rag_context=rag_context,
            thread_summary=thread.summary,
            max_context_tokens=self.settings.coding_max_context_tokens,
            max_files=self.settings.coding_max_files,
            max_file_size=self.settings.coding_max_file_size,
        )

        # Emit coding_started
        project_name = project.name if project else None
        num_attached_files = len(payload.file_ids) if payload.file_ids else 0
        yield coding_started(
            query=payload.content,
            file_count=num_attached_files,
            project_name=project_name,
        )

        # Load code files
        loaded_files = await context_builder.load_code_files(
            session=session,
            user_id=user_id,
            file_ids=payload.file_ids,
            project_id=thread.project_id,
        )

        # Emit coding_file for each loaded file
        total_chars = 0
        file_names: list[str] = []
        for file_info in loaded_files:
            fname = file_info.get("filename", "")
            flang = file_info.get("language", "text")
            fsize = file_info.get("size_bytes", 0)
            file_names.append(fname)
            total_chars += len(file_info.get("content", ""))
            yield coding_file(filename=fname, language=flang, size_bytes=fsize)

        # Emit coding_context_ready
        yield coding_context_ready(
            file_names=file_names,
            total_files=len(loaded_files),
            total_chars=total_chars,
        )

        # 6. Fetch conversation history and assemble messages
        history = await message_service.list_messages(
            session,
            thread_id=thread.id,
            limit=self.settings.max_context_messages,
            offset=0,
        )
        context_messages = context_builder.assemble(
            messages=history[-self.settings.max_context_messages :],
            user_query=payload.content,
        )

        # Resolve provider and model selection
        selection = self.router.select(
            mode=ConversationMode.CODING,
            provider=payload.provider or self.settings.coding_provider,
            model=payload.model or self.settings.coding_model,
        )
        yield coding_generation(
            provider=getattr(selection.provider_name, "value", str(selection.provider_name)),
            model=selection.model,
        )

        assistant_text: list[str] = []
        latest_selection: ProviderSelection | None = selection
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
                    messages=context_messages,
                    mode=ConversationMode.CODING,
                    provider=payload.provider or self.settings.coding_provider,
                    model=payload.model or self.settings.coding_model,
                    context=tool_context,
                    is_disconnected=is_disconnected,
                ):
                    yield sse_chunk

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
            else:
                yield message_start(
                    selection.provider_name,
                    selection.model,
                    ConversationMode.CODING,
                    selection.fallback_used,
                )
                async for sel, event in self.router.stream(
                    messages=context_messages,
                    mode=ConversationMode.CODING,
                    provider=payload.provider or self.settings.coding_provider,
                    model=payload.model or self.settings.coding_model,
                ):
                    latest_selection = sel
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
                        )
                        return
                    latest_usage = _merge_usage(latest_usage, event)
                    if event.finish_reason:
                        finish_reason = event.finish_reason
                    if event.delta:
                        assistant_text.append(event.delta)
                        yield text_delta(event.delta)

            full_content = "".join(assistant_text)
            diffs = extract_diffs_from_text(full_content)

            # Persist assistant message
            assistant = await self._persist_assistant(
                session,
                thread_id=thread.id,
                content=full_content,
                selection=latest_selection,
                status=GenerationStatus.COMPLETED,
                usage=latest_usage,
                latency_ms=_latency_ms(start),
                finish_reason=finish_reason,
            )

            # Post-generation memory extraction and summarization
            if self.settings.memory_enabled and not is_temp:
                try:
                    from app.services.memory.extractor import MemoryExtractor
                    from app.services.memory.service import MemoryService
                    from app.services.memory.summarizer import ThreadSummaryService

                    extractor = MemoryExtractor()
                    ext_result = extractor.extract(payload.content, is_rag_query=False)
                    if ext_result.candidates:
                        mem_svc = MemoryService(session)
                        await mem_svc.process_and_store_candidates(
                            user_id=thread.user_id,
                            candidates=ext_result.candidates,
                            project_id=thread.project_id,
                            source=f"thread:{thread.id}",
                        )

                    summarizer = ThreadSummaryService(session)
                    await summarizer.maybe_update_thread_summary(
                        thread.id,
                        threshold=self.settings.thread_summary_threshold,
                    )
                except Exception:
                    pass

            # Emit coding_complete and message_complete
            yield coding_complete(
                files_analyzed=len(loaded_files),
                changes_count=len(diffs),
                tests_count=1 if "def test_" in full_content or "it(" in full_content else 0,
            )

            p_name = latest_selection.provider_name if latest_selection else ProviderSelection(None, "groq", "qwen/qwen3.8-27b").provider_name
            p_model = latest_selection.model if latest_selection else "qwen/qwen3.8-27b"
            yield message_complete(
                MessageCompletePayload(
                    message_id=assistant.id,
                    provider=p_name,
                    model=p_model,
                    mode=ConversationMode.CODING,
                    finish_reason=finish_reason,
                    fallback_used=latest_selection.fallback_used if latest_selection else False,
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
                )
            yield coding_error(exc.message)
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
    ) -> Message:
        provider_name = None
        if selection is not None:
            provider_name = getattr(selection.provider_name, "value", str(selection.provider_name))

        message = Message(
            thread_id=thread_id,
            role=MessageRole.ASSISTANT,
            content=content,
            provider=provider_name,
            model=selection.model if selection else None,
            mode=ConversationMode.CODING,
            generation_status=status,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            total_tokens=usage.total_tokens,
            latency_ms=latency_ms,
        )
        session.add(message)
        thread = await session.get(Thread, thread_id)
        if thread:
            thread.updated_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(message)
        return message

    async def query_coding(
        self,
        session: AsyncSession,
        req: CodingQueryRequest,
        user_id: UUID,
    ) -> CodingQueryResponse:
        """Standalone non-streaming coding endpoint execution."""
        project: Optional[Project] = None
        if req.project_id:
            project = await session.get(Project, req.project_id)

        context_builder = CodeContextBuilder(
            project=project,
            max_context_tokens=self.settings.coding_max_context_tokens,
            max_files=self.settings.coding_max_files,
            max_file_size=self.settings.coding_max_file_size,
        )

        loaded_files = await context_builder.load_code_files(
            session=session,
            user_id=user_id,
            file_ids=req.file_ids,
            project_id=req.project_id,
        )

        user_turn = Message(
            id=None,
            role=MessageRole.USER,
            content=req.query,
        )
        messages = context_builder.assemble([user_turn])

        selection = self.router.select(
            mode=ConversationMode.CODING,
            provider=req.provider or self.settings.coding_provider,
            model=req.model or self.settings.coding_model,
        )

        collected_text: list[str] = []
        async for sel, event in self.router.stream(
            messages=messages,
            mode=ConversationMode.CODING,
            provider=req.provider or self.settings.coding_provider,
            model=req.model or self.settings.coding_model,
        ):
            if event.delta:
                collected_text.append(event.delta)

        full_text = "".join(collected_text)
        diffs = extract_diffs_from_text(full_text)

        # Detect primary language
        primary_lang = None
        if loaded_files:
            primary_lang = loaded_files[0].get("language")

        return CodingQueryResponse(
            answer=full_text,
            language=primary_lang,
            files_changed=[d.file for d in diffs if d.file != "unknown"],
            diffs=diffs,
            tests=[],
        )
