from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from enum import StrEnum

from app.core.enums import ConversationMode, MessageRole


class ProviderName(StrEnum):
    GROQ = "groq"
    GEMINI = "gemini"
    MISTRAL = "mistral"


class ProviderErrorCode(StrEnum):
    AUTH_ERROR = "PROVIDER_AUTH_ERROR"
    RATE_LIMIT = "PROVIDER_RATE_LIMIT"
    TIMEOUT = "PROVIDER_TIMEOUT"
    BAD_REQUEST = "PROVIDER_BAD_REQUEST"
    UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    CONTEXT_LIMIT = "PROVIDER_CONTEXT_LIMIT"
    UNKNOWN = "PROVIDER_UNKNOWN_ERROR"


@dataclass(frozen=True)
class NormalizedMessage:
    role: MessageRole
    content: str


@dataclass(frozen=True)
class UsageMetadata:
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    latency_ms: int | None = None


@dataclass(frozen=True)
class ProviderStreamEvent:
    delta: str = ""
    finish_reason: str | None = None
    usage: UsageMetadata = field(default_factory=UsageMetadata)


class ProviderError(Exception):
    def __init__(
        self,
        code: ProviderErrorCode,
        message: str,
        *,
        provider: ProviderName | None = None,
        retryable: bool = False,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.provider = provider
        self.retryable = retryable
        self.retry_after = retry_after

    @classmethod
    def from_no_response(cls, *, provider: ProviderName | None = None) -> "ProviderError":
        return cls(
            ProviderErrorCode.UNKNOWN,
            "No response received from provider",
            provider=provider,
            retryable=False,
        )


class AIProvider:
    name: ProviderName
    default_model: str

    def supports_model(self, model: str) -> bool:
        raise NotImplementedError

    async def generate(
        self,
        *,
        messages: list[NormalizedMessage],
        model: str,
        mode: ConversationMode,
        max_tokens: int | None = None,
    ) -> str:
        text = []
        async for event in self.stream(messages=messages, model=model, mode=mode, max_tokens=max_tokens):
            if event.delta:
                text.append(event.delta)
        return "".join(text)

    def stream(
        self,
        *,
        messages: list[NormalizedMessage],
        model: str,
        mode: ConversationMode,
        max_tokens: int | None = None,
    ) -> AsyncIterator[ProviderStreamEvent]:
        raise NotImplementedError

    def normalize_error(self, error: Exception) -> ProviderError:
        if isinstance(error, ProviderError):
            return error
        message = str(error) or "Provider request failed"
        return ProviderError(
            ProviderErrorCode.UNKNOWN,
            message,
            provider=self.name,
            retryable=False,
        )
