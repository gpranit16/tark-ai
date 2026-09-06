from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from sqlalchemy import select

from app.core.enums import ConversationMode, GenerationStatus, MessageRole
from app.models.conversation import Message, Thread, User
from app.providers.base import ProviderStreamEvent, UsageMetadata
from app.schemas.chat import ChatRequest
from app.services.chat.router import ModelRouter, ProviderSelection
from app.services.chat.service import ChatService


class FakeProvider:
    name = "groq"
    default_model = "llama-3.1-8b-instant"

    def supports_model(self, model: str) -> bool:
        return bool(model)

    async def stream(self, *, messages, model: str, mode: ConversationMode) -> AsyncIterator[ProviderStreamEvent]:
        yield ProviderStreamEvent(delta="hello ", finish_reason="stop", usage=UsageMetadata(input_tokens=2, output_tokens=3, total_tokens=5))
        yield ProviderStreamEvent(delta="world", finish_reason="stop", usage=UsageMetadata(input_tokens=2, output_tokens=3, total_tokens=5))


class FakeRouter(ModelRouter):
    def __init__(self) -> None:
        super().__init__({})

    async def stream(self, *, messages, mode, provider=None, model=None):
        yield (
            ProviderSelection(provider=FakeProvider(), provider_name="groq", model="llama-3.1-8b-instant", fallback_used=False),
            ProviderStreamEvent(delta="hello ", finish_reason="stop", usage=UsageMetadata(input_tokens=2, output_tokens=3, total_tokens=5)),
        )
        yield (
            ProviderSelection(provider=FakeProvider(), provider_name="groq", model="llama-3.1-8b-instant", fallback_used=False),
            ProviderStreamEvent(delta="world", finish_reason="stop", usage=UsageMetadata(input_tokens=2, output_tokens=3, total_tokens=5)),
        )


@pytest.mark.asyncio
async def test_stream_chat_persists_user_and_assistant_messages(db_session, user):
    user_db = await db_session.merge(user)
    thread = Thread(user_id=user_db.id, title="Test", default_mode=ConversationMode.NORMAL)
    db_session.add(thread)
    await db_session.commit()
    await db_session.refresh(thread)

    service = ChatService(router=FakeRouter())

    async def is_disconnected() -> bool:
        return False

    events = [
        event
        async for event in service.stream_chat(
            session=db_session,
            thread_id=thread.id,
            payload=ChatRequest(content="hello there"),
            is_disconnected=is_disconnected,
        )
    ]

    assert any("event: message_start" in item for item in events)
    assert any("event: text_delta" in item for item in events)
    assert any("event: message_complete" in item for item in events)

    db_messages = (await db_session.execute(select(Message).where(Message.thread_id == thread.id))).scalars().all()
    assert [message.role for message in db_messages] == [MessageRole.USER, MessageRole.ASSISTANT]
    assert db_messages[-1].content == "hello world"
    assert db_messages[-1].provider == "groq"
    assert db_messages[-1].model == "llama-3.1-8b-instant"
    assert db_messages[-1].mode == ConversationMode.NORMAL
    assert db_messages[-1].generation_status == GenerationStatus.COMPLETED


@pytest.mark.asyncio
async def test_chat_endpoint_streams_sse(client, user, db_session, monkeypatch):
    user_db = await db_session.merge(user)
    thread = Thread(user_id=user_db.id, title="Chat", default_mode=ConversationMode.NORMAL)
    db_session.add(thread)
    await db_session.commit()
    await db_session.refresh(thread)

    class FakeRouteChatService:
        async def stream_chat(self, **kwargs):
            yield "event: message_start\ndata: {\"provider\": \"groq\", \"model\": \"llama-3.1-8b-instant\", \"mode\": \"normal\", \"fallback_used\": false}\n\n"
            yield "event: text_delta\ndata: {\"delta\": \"hello\"}\n\n"
            yield "event: message_complete\ndata: {\"message_id\": \"00000000-0000-0000-0000-000000000000\", \"provider\": \"groq\", \"model\": \"llama-3.1-8b-instant\", \"mode\": \"normal\", \"finish_reason\": \"stop\", \"fallback_used\": false}\n\n"

    import app.api.v1.threads as threads_module
    monkeypatch.setattr(threads_module, "ChatService", FakeRouteChatService)

    response = client.post(f"/api/v1/threads/{thread.id}/chat", json={"content": "hello"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    payload = response.text
    assert "event: message_start" in payload
    assert "event: text_delta" in payload
    assert "event: message_complete" in payload
