from collections.abc import AsyncIterator

from app.core.enums import ConversationMode
from app.providers.base import (
    AIProvider,
    NormalizedMessage,
    ProviderError,
    ProviderErrorCode,
    ProviderName,
    ProviderStreamEvent,
    UsageMetadata,
)


class MistralProvider(AIProvider):
    name = ProviderName.MISTRAL

    def __init__(self, *, api_key: str | None, default_model: str, timeout: float) -> None:
        self.api_key = api_key
        self.default_model = default_model
        self.timeout = timeout

    def supports_model(self, model: str) -> bool:
        return bool(model and model.strip())

    async def stream(
        self,
        *,
        messages: list[NormalizedMessage],
        model: str,
        mode: ConversationMode,
        max_tokens: int | None = None,
    ) -> AsyncIterator[ProviderStreamEvent]:
        if not self.api_key:
            raise ProviderError(ProviderErrorCode.AUTH_ERROR, "Mistral API key is not configured", provider=self.name)
        try:
            from mistralai import Mistral

            extra_kwargs: dict[str, object] = {}
            if max_tokens is not None:
                extra_kwargs["max_tokens"] = max_tokens

            async with Mistral(api_key=self.api_key) as client:
                stream = await client.chat.stream_async(
                    model=model,
                    messages=[
                        {"role": message.role.value, "content": message.content or " "}
                        for message in messages
                        if (message.content or "").strip()  # skip blank messages
                    ],
                    **extra_kwargs,
                )
                async for chunk in stream:
                    data = getattr(chunk, "data", chunk)
                    choices = getattr(data, "choices", None) or []
                    choice = choices[0] if choices else None
                    delta = ""
                    finish_reason = None
                    if choice is not None:
                        delta_obj = getattr(choice, "delta", None)
                        delta = getattr(delta_obj, "content", "") or ""
                        finish_reason = getattr(choice, "finish_reason", None)
                    yield ProviderStreamEvent(delta=delta, finish_reason=finish_reason, usage=_usage_from_object(data))
        except Exception as exc:
            raise self.normalize_error(exc) from exc

    def normalize_error(self, error: Exception) -> ProviderError:
        if isinstance(error, ProviderError):
            return error
        status_code = getattr(error, "status_code", None)
        name = error.__class__.__name__.lower()
        if status_code in {401, 403} or "auth" in name:
            code = ProviderErrorCode.AUTH_ERROR
        elif status_code == 429 or "rate" in name:
            code = ProviderErrorCode.RATE_LIMIT
        elif "timeout" in name:
            code = ProviderErrorCode.TIMEOUT
        elif status_code in {400, 404, 422}:
            code = ProviderErrorCode.BAD_REQUEST
        elif status_code and status_code >= 500:
            code = ProviderErrorCode.UNAVAILABLE
        else:
            code = ProviderErrorCode.UNKNOWN
        return ProviderError(code, "Mistral provider request failed", provider=self.name, retryable=code in _RETRYABLE)


def _usage_from_object(value: object | None) -> UsageMetadata:
    usage = getattr(value, "usage", None)
    if usage is None:
        return UsageMetadata()
    return UsageMetadata(
        input_tokens=getattr(usage, "prompt_tokens", None),
        output_tokens=getattr(usage, "completion_tokens", None),
        total_tokens=getattr(usage, "total_tokens", None),
    )


_RETRYABLE = {ProviderErrorCode.RATE_LIMIT, ProviderErrorCode.TIMEOUT, ProviderErrorCode.UNAVAILABLE}
