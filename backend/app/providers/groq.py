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


import re
from app.core.config import get_settings


class GroqProvider(AIProvider):
    name = ProviderName.GROQ

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
            raise ProviderError(ProviderErrorCode.AUTH_ERROR, "Groq API key is not configured", provider=self.name)
        try:
            from groq import AsyncGroq

            settings = get_settings()
            kwargs: dict[str, object] = {}

            # Token budget resolution:
            # 1. Explicit max_tokens parameter takes highest precedence (clamped to Groq provider model bounds)
            # 2. If mode is RAG, use configured rag_max_output_tokens (default 500)
            # 3. If mode is FAST, use fast mode bounded limit (150)
            # 4. For normal chat / coding / reasoning, use model defaults
            if max_tokens is not None:
                if "qwen3.6" in model.lower():
                    kwargs["max_tokens"] = min(max_tokens, 450)
                elif "qwen" in model.lower():
                    kwargs["max_tokens"] = min(max_tokens, 2000)
                elif "gpt-oss" in model.lower():
                    kwargs["max_tokens"] = min(max_tokens, 3000)
                else:
                    kwargs["max_tokens"] = min(max_tokens, 3000)
            elif mode == ConversationMode.RAG:
                kwargs["max_tokens"] = settings.rag_max_output_tokens
            elif mode == ConversationMode.FAST:
                kwargs["max_tokens"] = 150
            elif "qwen3.6" in model.lower():
                kwargs["max_tokens"] = 450
            elif "qwen" in model.lower():
                kwargs["max_tokens"] = 900
            elif "gpt-oss" in model.lower():
                kwargs["max_tokens"] = 1200

            client = AsyncGroq(api_key=self.api_key, timeout=self.timeout, max_retries=0)
            msg_payload = [
                {
                    "role": "user" if message.role.value == "tool" else message.role.value,
                    "content": message.content or " ",
                }
                for message in messages
                if (message.content or "").strip()  # skip blank messages
            ]
            try:
                stream = await client.chat.completions.create(
                    model=model,
                    messages=msg_payload,
                    stream=True,
                    **kwargs,
                )
            except Exception as create_exc:
                err_msg = str(create_exc).lower()
                if "request too large" in err_msg or "otpm" in err_msg:
                    # Retry once with bounded 250 tokens
                    kwargs["max_tokens"] = 250
                    stream = await client.chat.completions.create(
                        model=model,
                        messages=msg_payload,
                        stream=True,
                        **kwargs,
                    )
                else:
                    raise
            async for chunk in stream:
                choice = chunk.choices[0] if chunk.choices else None
                delta = ""
                finish_reason = None
                if choice is not None:
                    delta = choice.delta.content or ""
                    finish_reason = choice.finish_reason
                usage = getattr(chunk, "usage", None)
                yield ProviderStreamEvent(
                    delta=delta,
                    finish_reason=finish_reason,
                    usage=_usage_from_object(usage),
                )
            await client.close()
        except Exception as exc:
            raise self.normalize_error(exc) from exc

    def normalize_error(self, error: Exception) -> ProviderError:
        if isinstance(error, ProviderError):
            return error
        status_code = getattr(error, "status_code", None)
        name = error.__class__.__name__.lower()
        if "authentication" in name or status_code in {401, 403}:
            code = ProviderErrorCode.AUTH_ERROR
        elif "rate" in name or status_code == 429:
            code = ProviderErrorCode.RATE_LIMIT
        elif "timeout" in name:
            code = ProviderErrorCode.TIMEOUT
        elif status_code in {400, 404, 422}:
            code = ProviderErrorCode.BAD_REQUEST
        elif status_code and status_code >= 500:
            code = ProviderErrorCode.UNAVAILABLE
        else:
            code = ProviderErrorCode.UNKNOWN

        # Extract Retry-After if provided in headers or error message
        retry_after: float | None = None
        response = getattr(error, "response", None)
        if response is not None and hasattr(response, "headers"):
            ra = response.headers.get("retry-after") or response.headers.get("Retry-After")
            if ra:
                try:
                    retry_after = float(ra)
                except (ValueError, TypeError):
                    pass

        raw_message = str(error).strip() or "Groq request failed"
        if retry_after is None:
            m = re.search(r"try again in ([\d\.]+)\s*(s|ms)", raw_message, re.IGNORECASE)
            if m:
                val, unit = float(m.group(1)), m.group(2).lower()
                retry_after = val if unit == "s" else (val / 1000.0)

        sanitized_message = raw_message.replace(self.api_key or "", "[REDACTED]") if self.api_key else raw_message
        safe_message = (
            f"Groq provider request failed: {error.__class__.__name__}"
            f" (status={status_code}) {sanitized_message}"
        )
        return ProviderError(code, safe_message, provider=self.name, retryable=code in _RETRYABLE, retry_after=retry_after)


def _usage_from_object(usage: object | None) -> UsageMetadata:
    if usage is None:
        return UsageMetadata()
    return UsageMetadata(
        input_tokens=getattr(usage, "prompt_tokens", None),
        output_tokens=getattr(usage, "completion_tokens", None),
        total_tokens=getattr(usage, "total_tokens", None),
    )


_RETRYABLE = {ProviderErrorCode.RATE_LIMIT, ProviderErrorCode.TIMEOUT, ProviderErrorCode.UNAVAILABLE}
