import json
from unittest.mock import AsyncMock, MagicMock, patch
import httpx
import pytest

from app.core.config import Settings
from app.core.enums import ConversationMode, MessageRole
from app.providers.base import (
    NormalizedMessage,
    ProviderError,
    ProviderErrorCode,
    ProviderName,
    ProviderStreamEvent,
)
from app.providers.nvidia import NvidiaProvider
from app.services.chat.router import ModelRouter, ProviderSelection


@pytest.fixture
def nvidia_provider() -> NvidiaProvider:
    return NvidiaProvider(
        api_key="test-nv-api-key-12345",
        base_url="https://integrate.api.nvidia.com/v1",
        default_model="nvidia/nemotron-3.5-lightning-30b-a3b",
        timeout=10.0,
    )


def test_nvidia_provider_init(nvidia_provider: NvidiaProvider) -> None:
    assert nvidia_provider.name == ProviderName.NVIDIA
    assert nvidia_provider.api_key == "test-nv-api-key-12345"
    assert nvidia_provider.base_url == "https://integrate.api.nvidia.com/v1"
    assert nvidia_provider.default_model == "nvidia/nemotron-3.5-lightning-30b-a3b"
    assert nvidia_provider.supports_model("nvidia/nemotron-3.5-lightning-30b-a3b")
    assert nvidia_provider.supports_model("custom-model")
    assert not nvidia_provider.supports_model("")


@pytest.mark.asyncio
async def test_nvidia_provider_missing_key() -> None:
    provider = NvidiaProvider(api_key=None)
    with pytest.raises(ProviderError) as exc_info:
        async for _ in provider.stream(
            messages=[NormalizedMessage(role=MessageRole.USER, content="Hello")],
            model="nvidia/nemotron-3.5-lightning-30b-a3b",
            mode=ConversationMode.NORMAL,
        ):
            pass
    assert exc_info.value.code == ProviderErrorCode.AUTH_ERROR
    assert exc_info.value.provider == ProviderName.NVIDIA


class FakeStreamContext:
    def __init__(self, response):
        self.response = response

    async def __aenter__(self):
        return self.response

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return None


class FakeClient:
    def __init__(self, response):
        self.response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return None

    def stream(self, method, url, **kwargs):
        return FakeStreamContext(self.response)


@pytest.mark.asyncio
async def test_nvidia_provider_streaming_success(nvidia_provider: NvidiaProvider) -> None:
    sse_lines = [
        b'data: {"id": "1", "choices": [{"delta": {"content": "Hello"}, "finish_reason": null}]}\n\n',
        b'data: {"id": "1", "choices": [{"delta": {"content": " world!"}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7}}\n\n',
        b'data: [DONE]\n\n',
    ]

    mock_response = AsyncMock()
    mock_response.status_code = 200

    async def mock_aiter_lines():
        for line in sse_lines:
            yield line.decode("utf-8")

    mock_response.aiter_lines = mock_aiter_lines

    with patch("httpx.AsyncClient", return_value=FakeClient(mock_response)):
        events: list[ProviderStreamEvent] = []
        async for event in nvidia_provider.stream(
            messages=[NormalizedMessage(role=MessageRole.USER, content="Hi")],
            model="nvidia/nemotron-3.5-lightning-30b-a3b",
            mode=ConversationMode.NORMAL,
        ):
            events.append(event)

        assert len(events) == 2
        assert events[0].delta == "Hello"
        assert events[1].delta == " world!"
        assert events[1].finish_reason == "stop"
        assert events[1].usage.total_tokens == 7


@pytest.mark.asyncio
async def test_nvidia_provider_think_tag_filtering(nvidia_provider: NvidiaProvider) -> None:
    sse_lines = [
        b'data: {"id": "1", "choices": [{"delta": {"content": "<think>Internal reasoning step</think>The actual answer."}}]}\n\n',
        b'data: [DONE]\n\n',
    ]

    mock_response = AsyncMock()
    mock_response.status_code = 200

    async def mock_aiter_lines():
        for line in sse_lines:
            yield line.decode("utf-8")

    mock_response.aiter_lines = mock_aiter_lines

    with patch("httpx.AsyncClient", return_value=FakeClient(mock_response)):
        collected = []
        async for event in nvidia_provider.stream(
            messages=[NormalizedMessage(role=MessageRole.USER, content="Reason")],
            model="nvidia/nemotron-3.5-lightning-30b-a3b",
            mode=ConversationMode.REASONING,
        ):
            if event.delta:
                collected.append(event.delta)

        full_text = "".join(collected)
        assert "<think>" not in full_text
        assert "Internal reasoning step" not in full_text
        assert "The actual answer." in full_text


@pytest.mark.asyncio
async def test_nvidia_provider_tool_call_delta_formatting(nvidia_provider: NvidiaProvider) -> None:
    sse_lines = [
        b'data: {"id": "1", "choices": [{"delta": {"tool_calls": [{"function": {"name": "web_search", "arguments": "{\\"query\\": \\"nvidia\\"}}"}}]}}]}\n\n',
        b'data: [DONE]\n\n',
    ]

    mock_response = AsyncMock()
    mock_response.status_code = 200

    async def mock_aiter_lines():
        for line in sse_lines:
            yield line.decode("utf-8")

    mock_response.aiter_lines = mock_aiter_lines

    with patch("httpx.AsyncClient", return_value=FakeClient(mock_response)):
        collected = []
        async for event in nvidia_provider.stream(
            messages=[NormalizedMessage(role=MessageRole.USER, content="Search")],
            model="nvidia/nemotron-3.5-lightning-30b-a3b",
            mode=ConversationMode.NORMAL,
        ):
            if event.delta:
                collected.append(event.delta)

        full_text = "".join(collected)
        assert "<tool_call>" in full_text
        assert '"name": "web_search"' in full_text


def test_nvidia_error_normalization_and_secret_redaction(nvidia_provider: NvidiaProvider) -> None:
    # 401 Auth Error
    err_401 = Exception("Invalid token test-nv-api-key-12345")
    err_401.status_code = 401
    norm_401 = nvidia_provider.normalize_error(err_401)
    assert norm_401.code == ProviderErrorCode.AUTH_ERROR
    assert "test-nv-api-key-12345" not in norm_401.message
    assert "[REDACTED]" in norm_401.message

    # 429 Rate Limit with Retry-After
    err_429 = Exception("Rate limit exceeded")
    err_429.status_code = 429
    err_429.headers = {"retry-after": "5.5"}
    norm_429 = nvidia_provider.normalize_error(err_429)
    assert norm_429.code == ProviderErrorCode.RATE_LIMIT
    assert norm_429.retryable is True
    assert norm_429.retry_after == 5.5

    # Timeout error
    timeout_err = httpx.ReadTimeout("Timeout connecting to server")
    norm_timeout = nvidia_provider.normalize_error(timeout_err)
    assert norm_timeout.code == ProviderErrorCode.TIMEOUT
    assert norm_timeout.retryable is True

    # 503 Unavailable
    err_503 = Exception("Service unavailable")
    err_503.status_code = 503
    norm_503 = nvidia_provider.normalize_error(err_503)
    assert norm_503.code == ProviderErrorCode.UNAVAILABLE
    assert norm_503.retryable is True


def test_model_router_select_nvidia() -> None:
    groq = MagicMock(spec=NvidiaProvider)
    groq.default_model = "qwen/qwen3.8-27b"
    nvidia = NvidiaProvider(api_key="nv-key", default_model="nvidia/nemotron-3.5-lightning-30b-a3b")

    settings = Settings(
        DATABASE_URL="postgresql+asyncpg://u:p@localhost:5432/db",
        NVIDIA_API_KEY="nv-key",
    )
    router = ModelRouter({ProviderName.GROQ: groq, ProviderName.NVIDIA: nvidia}, settings=settings)

    # Explicit provider
    sel1 = router.select(mode=ConversationMode.NORMAL, provider="nvidia")
    assert sel1.provider_name == ProviderName.NVIDIA
    assert sel1.model == "nvidia/nemotron-3.5-lightning-30b-a3b"

    # Auto-routed by model name
    sel2 = router.select(mode=ConversationMode.NORMAL, model="nvidia/nemotron-3.5-lightning-30b-a3b")
    assert sel2.provider_name == ProviderName.NVIDIA
    assert sel2.model == "nvidia/nemotron-3.5-lightning-30b-a3b"

    # Auto-routed by nemotron keyword
    sel3 = router.select(mode=ConversationMode.NORMAL, model="nemotron-3.5-lightning")
    assert sel3.provider_name == ProviderName.NVIDIA


def test_parse_tool_calls_bare_json() -> None:
    from app.services.chat.tool_loop import parse_tool_calls, strip_tool_call_markup

    raw_output = '{"name": "search_news", "arguments": {"query": "latest ai news"}}'
    calls = parse_tool_calls(raw_output)
    assert len(calls) == 1
    assert calls[0][0] == "search_news"
    assert calls[0][1] == {"query": "latest ai news"}

    cleaned = strip_tool_call_markup(raw_output)
    assert cleaned == ""
