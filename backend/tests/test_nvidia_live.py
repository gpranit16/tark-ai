import asyncio
import os
import time
import pytest

from app.core.config import get_settings
from app.core.enums import ConversationMode, MessageRole
from app.providers.base import NormalizedMessage, ProviderName
from app.providers.nvidia import NvidiaProvider
from app.services.chat.router import ModelRouter


@pytest.fixture
def live_provider() -> NvidiaProvider:
    settings = get_settings()
    if not settings.nvidia_api_key:
        pytest.skip("NVIDIA_API_KEY is not configured in .env; skipping live API test.")

    return NvidiaProvider(
        api_key=settings.nvidia_api_key,
        base_url=settings.nvidia_base_url,
        default_model=settings.nvidia_model or "nvidia/nemotron-3.5-lightning-30b-a3b",
        timeout=60.0,
    )


@pytest.mark.asyncio
async def test_live_nvidia_chat_completion_and_ttft(live_provider: NvidiaProvider) -> None:
    start_time = time.perf_counter()
    first_token_time = None
    deltas = []

    messages = [
        NormalizedMessage(role=MessageRole.SYSTEM, content="You are TARK AI, an intelligent luxury assistant."),
        NormalizedMessage(role=MessageRole.USER, content="Hello, who are you? Please give a concise 1-sentence answer."),
    ]

    async for event in live_provider.stream(
        messages=messages,
        model=live_provider.default_model,
        mode=ConversationMode.NORMAL,
        max_tokens=500,
    ):
        if event.delta:
            if first_token_time is None:
                first_token_time = time.perf_counter()
            deltas.append(event.delta)

    total_time = time.perf_counter() - start_time
    ttft = (first_token_time - start_time) if first_token_time else total_time
    response_text = "".join(deltas).strip()

    print(f"\n[LIVE NVIDIA] Chat Response: {response_text}")
    print(f"[LIVE NVIDIA] TTFT: {ttft:.3f}s | Total Latency: {total_time:.3f}s")

    assert len(response_text) > 0
    assert "<think>" not in response_text


@pytest.mark.asyncio
async def test_live_nvidia_multiturn_conversation(live_provider: NvidiaProvider) -> None:
    messages = [
        NormalizedMessage(role=MessageRole.SYSTEM, content="You are TARK AI."),
        NormalizedMessage(role=MessageRole.USER, content="The secret code is 8849."),
        NormalizedMessage(role=MessageRole.ASSISTANT, content="Understood. The secret code 8849 is saved."),
        NormalizedMessage(role=MessageRole.USER, content="What was the secret code?"),
    ]

    deltas = []
    async for event in live_provider.stream(
        messages=messages,
        model=live_provider.default_model,
        mode=ConversationMode.NORMAL,
        max_tokens=500,
    ):
        if event.delta:
            deltas.append(event.delta)

    response = "".join(deltas).strip()
    print(f"\n[LIVE NVIDIA] Multi-turn Response: {response}")
    assert "8849" in response


@pytest.mark.asyncio
async def test_live_nvidia_rag_grounded_answer(live_provider: NvidiaProvider) -> None:
    rag_context = "DOCUMENT CONTEXT:\nEmployee #4829 John Doe was born on July 14, 1988.\n\nQUESTION: What is John Doe's date of birth?"
    rag_messages = [
        NormalizedMessage(role=MessageRole.SYSTEM, content="Answer strictly using provided document context. If not found, say 'Information not found'."),
        NormalizedMessage(role=MessageRole.USER, content=rag_context),
    ]

    deltas = []
    async for event in live_provider.stream(
        messages=rag_messages,
        model=live_provider.default_model,
        mode=ConversationMode.RAG,
        max_tokens=500,
    ):
        if event.delta:
            deltas.append(event.delta)

    rag_response = "".join(deltas).strip()
    print(f"\n[LIVE NVIDIA] RAG Grounded Response: {rag_response}")
    assert "1988" in rag_response or "July 14" in rag_response


@pytest.mark.asyncio
async def test_live_nvidia_rag_missing_fact_abstention(live_provider: NvidiaProvider) -> None:
    missing_context = "DOCUMENT CONTEXT:\nEmployee #4829 John Doe was born on July 14, 1988.\n\nQUESTION: What is John Doe's favorite color?"
    missing_messages = [
        NormalizedMessage(role=MessageRole.SYSTEM, content="Answer strictly using provided document context. If not found in document, state clearly that it is not present in the document."),
        NormalizedMessage(role=MessageRole.USER, content=missing_context),
    ]

    deltas = []
    async for event in live_provider.stream(
        messages=missing_messages,
        model=live_provider.default_model,
        mode=ConversationMode.RAG,
        max_tokens=500,
    ):
        if event.delta:
            deltas.append(event.delta)

    missing_response = "".join(deltas).strip().lower()
    print(f"\n[LIVE NVIDIA] RAG Missing Fact Response: {missing_response}")
    assert any(k in missing_response for k in ["not", "unspecified", "not present", "not mentioned", "not provided"])


@pytest.mark.asyncio
async def test_live_nvidia_coding_completion(live_provider: NvidiaProvider) -> None:
    code_messages = [
        NormalizedMessage(role=MessageRole.SYSTEM, content="You are an expert Python engineer. Output only executable Python code."),
        NormalizedMessage(role=MessageRole.USER, content="Write a python function `fibonacci(n: int) -> int`."),
    ]
    deltas = []
    async for event in live_provider.stream(
        messages=code_messages,
        model=live_provider.default_model,
        mode=ConversationMode.CODING,
        max_tokens=500,
    ):
        if event.delta:
            deltas.append(event.delta)

    code_response = "".join(deltas).strip()
    print(f"\n[LIVE NVIDIA] Coding Response: {code_response[:100]}...")
    assert "def fibonacci" in code_response


def test_live_nvidia_model_router_dispatch() -> None:
    settings = get_settings()
    router = ModelRouter.from_settings(settings)
    selection = router.select(mode=ConversationMode.NORMAL, model="nvidia/nemotron-3.5-lightning-30b-a3b")
    assert selection.provider_name == ProviderName.NVIDIA
    assert selection.model == "nvidia/nemotron-3.5-lightning-30b-a3b"
