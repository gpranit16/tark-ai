"""Unit and integration tests for ModelRouter, provider dispatch, fallback isolation, and persistence."""
from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID
import pytest

from app.core.config import Settings
from app.core.enums import ConversationMode, MessageRole
from app.models.conversation import Message, Thread, User
from app.providers.base import (
    AIProvider,
    NormalizedMessage,
    ProviderError,
    ProviderErrorCode,
    ProviderName,
    ProviderStreamEvent,
    UsageMetadata,
)
from app.schemas.chat import ChatRequest
from app.services.chat.router import ModelRouter, ProviderSelection
from app.services.chat.service import ChatService


class MockAIProvider(AIProvider):
    def __init__(self, name: ProviderName, default_model: str, should_fail: bool = False, fail_code: ProviderErrorCode = ProviderErrorCode.RATE_LIMIT):
        self.name = name
        self.default_model = default_model
        self.should_fail = should_fail
        self.fail_code = fail_code
        self.calls = []

    def supports_model(self, model: str) -> bool:
        return True

    async def stream(
        self,
        *,
        messages: list[NormalizedMessage],
        model: str,
        mode: ConversationMode,
        max_tokens: int | None = None,
    ) -> AsyncIterator[ProviderStreamEvent]:
        self.calls.append({"model": model, "mode": mode, "messages": messages, "max_tokens": max_tokens})
        if self.should_fail:
            raise ProviderError(self.fail_code, f"{self.name.value} simulated failure", provider=self.name, retryable=True)
        yield ProviderStreamEvent(delta=f"Hello from {self.name.value} ({model})", finish_reason="stop", usage=UsageMetadata(10, 20, 30))


def create_test_settings() -> Settings:
    return Settings(
        DATABASE_URL="postgresql+asyncpg://tarkai:change-me@localhost:5433/tarkai_test",
        FAST_PROVIDER="groq",
        FAST_MODEL="qwen/qwen3.6-27b",
        NORMAL_PROVIDER="groq",
        NORMAL_MODEL="qwen/qwen3.8-27b",
        REASONING_PROVIDER="groq",
        REASONING_MODEL="openai/gpt-oss-120b",
        CODING_PROVIDER="groq",
        CODING_MODEL="qwen/qwen3.8-27b",
        DEFAULT_PROVIDER="groq",
        AUTO_FALLBACK=True,
    )


def test_routing_fast_mode():
    """A. Fast -> Groq Qwen 3.6"""
    settings = create_test_settings()
    groq = MockAIProvider(ProviderName.GROQ, "qwen/qwen3.8-27b")
    router = ModelRouter({ProviderName.GROQ: groq}, settings=settings)

    selection = router.select(mode=ConversationMode.FAST)
    assert selection.provider_name == ProviderName.GROQ
    assert selection.model == "qwen/qwen3.6-27b"
    assert not selection.fallback_used


def test_routing_normal_mode():
    """B. Normal -> Groq Qwen 3.8"""
    settings = create_test_settings()
    groq = MockAIProvider(ProviderName.GROQ, "qwen/qwen3.8-27b")
    router = ModelRouter({ProviderName.GROQ: groq}, settings=settings)

    selection = router.select(mode=ConversationMode.NORMAL)
    assert selection.provider_name == ProviderName.GROQ
    assert selection.model == "qwen/qwen3.8-27b"
    assert not selection.fallback_used


def test_routing_reasoning_mode():
    """C. Reasoning -> Groq GPT-OSS 120B"""
    settings = create_test_settings()
    groq = MockAIProvider(ProviderName.GROQ, "qwen/qwen3.8-27b")
    router = ModelRouter({ProviderName.GROQ: groq}, settings=settings)

    selection = router.select(mode=ConversationMode.REASONING)
    assert selection.provider_name == ProviderName.GROQ
    assert selection.model == "openai/gpt-oss-120b"
    assert not selection.fallback_used


def test_routing_coding_mode():
    """D. Coding -> configured coding provider / model"""
    settings = create_test_settings()
    groq = MockAIProvider(ProviderName.GROQ, "qwen/qwen3.8-27b")
    router = ModelRouter({ProviderName.GROQ: groq}, settings=settings)

    selection = router.select(mode=ConversationMode.CODING)
    assert selection.provider_name == ProviderName.GROQ
    assert selection.model == "qwen/qwen3.8-27b"


def test_no_accidental_mistral_routing():
    """E. No accidental Mistral routing when normal mode is selected"""
    settings = create_test_settings()
    groq = MockAIProvider(ProviderName.GROQ, "qwen/qwen3.8-27b")
    mistral = MockAIProvider(ProviderName.MISTRAL, "mistral-medium-latest")
    router = ModelRouter({ProviderName.GROQ: groq, ProviderName.MISTRAL: mistral}, settings=settings)

    selection = router.select(mode=ConversationMode.NORMAL)
    assert selection.provider_name == ProviderName.GROQ
    assert selection.provider_name != ProviderName.MISTRAL


@pytest.mark.asyncio
async def test_fallback_behavior_and_primary_error_attribution():
    """F. Fallback behavior: if groq fails, attempts next provider. If all fail, attributes primary error."""
    settings = create_test_settings()
    groq_failing = MockAIProvider(ProviderName.GROQ, "qwen/qwen3.8-27b", should_fail=True)
    mistral_failing = MockAIProvider(ProviderName.MISTRAL, "mistral-medium-latest", should_fail=True)
    router = ModelRouter(
        {ProviderName.GROQ: groq_failing, ProviderName.MISTRAL: mistral_failing},
        settings=settings,
    )

    messages = [NormalizedMessage(role=MessageRole.USER, content="Hello")]
    with pytest.raises(ProviderError) as exc_info:
        async for sel, ev in router.stream(messages=messages, mode=ConversationMode.NORMAL):
            pass

    # Error message must cite the primary provider failure, NOT solely mistral failure
    assert "Primary provider 'groq' request failed" in exc_info.value.message
    assert exc_info.value.provider == ProviderName.GROQ


@pytest.mark.asyncio
async def test_persisted_provider_model_and_followup_preservation(db_session, user):
    """G & H. Verify persisted message metadata stores actual provider/model and follow-up messages preserve mode."""
    user_db = await db_session.merge(user)
    thread = Thread(user_id=user_db.id, title="Router Test", default_mode=ConversationMode.NORMAL)
    db_session.add(thread)
    await db_session.commit()
    await db_session.refresh(thread)

    settings = create_test_settings()
    groq = MockAIProvider(ProviderName.GROQ, "qwen/qwen3.8-27b")
    router = ModelRouter({ProviderName.GROQ: groq}, settings=settings)
    service = ChatService(router=router)

    async def is_disc():
        return False

    # Turn 1
    events_turn1 = [
        ev async for ev in service.stream_chat(
            session=db_session,
            thread_id=thread.id,
            payload=ChatRequest(content="How are you?", mode=ConversationMode.NORMAL, provider="groq", model="qwen/qwen3.8-27b"),
            is_disconnected=is_disc,
        )
    ]
    assert any("event: message_start" in ev for ev in events_turn1)

    # Turn 2 (Follow up in same thread)
    events_turn2 = [
        ev async for ev in service.stream_chat(
            session=db_session,
            thread_id=thread.id,
            payload=ChatRequest(content="What is my name?", mode=ConversationMode.NORMAL, provider="groq", model="qwen/qwen3.8-27b"),
            is_disconnected=is_disc,
        )
    ]
    assert any("event: message_start" in ev for ev in events_turn2)

    # Inspect persisted messages in database
    from sqlalchemy import select
    msgs = (await db_session.scalars(select(Message).where(Message.thread_id == thread.id).order_by(Message.created_at.asc()))).all()
    assert len(msgs) == 4
    # User 1
    assert msgs[0].role == MessageRole.USER
    assert msgs[0].content == "How are you?"
    # Asst 1
    assert msgs[1].role == MessageRole.ASSISTANT
    assert msgs[1].provider == "groq"
    assert msgs[1].model == "qwen/qwen3.8-27b"
    assert msgs[1].mode == ConversationMode.NORMAL
    # User 2
    assert msgs[2].role == MessageRole.USER
    assert msgs[2].content == "What is my name?"
    # Asst 2
    assert msgs[3].role == MessageRole.ASSISTANT
    assert msgs[3].provider == "groq"
    assert msgs[3].model == "qwen/qwen3.8-27b"
    assert msgs[3].mode == ConversationMode.NORMAL
