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
            # 1. Explicit max_tokens parameter takes highest precedence
            # 2. If mode is FAST, allow 2048 tokens so thinking models can think & complete response
            # 3. For normal chat / coding / reasoning / web search, allow full 4096 tokens
            if max_tokens is not None:
                kwargs["max_tokens"] = min(max_tokens, 4096)
            elif mode == ConversationMode.FAST:
                kwargs["max_tokens"] = 2048
            else:
                kwargs["max_tokens"] = 4096

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
            tool_calls_acc: dict[int, dict[str, str]] = {}
            try:
                async for chunk in stream:
                    choice = chunk.choices[0] if chunk.choices else None
                    delta = ""
                    finish_reason = None
                    if choice is not None:
                        delta = choice.delta.content or ""
                        # Accumulate native Groq tool_calls in stream delta if sent by model
                        if hasattr(choice.delta, "tool_calls") and choice.delta.tool_calls:
                            for tc in choice.delta.tool_calls:
                                idx = getattr(tc, "index", 0) or 0
                                if idx not in tool_calls_acc:
                                    tool_calls_acc[idx] = {"name": "", "arguments": ""}
                                fn = getattr(tc, "function", None)
                                if fn:
                                    fn_name = getattr(fn, "name", None)
                                    fn_args = getattr(fn, "arguments", None)
                                    if fn_name:
                                        tool_calls_acc[idx]["name"] += fn_name
                                    if fn_args:
                                        tool_calls_acc[idx]["arguments"] += fn_args
                        finish_reason = choice.finish_reason
                    usage = getattr(chunk, "usage", None)
                    if delta:
                        yield ProviderStreamEvent(
                            delta=delta,
                            finish_reason=finish_reason,
                            usage=_usage_from_object(usage),
                        )

                # Flush complete accumulated tool calls if any
                if tool_calls_acc:
                    for idx, tc_data in sorted(tool_calls_acc.items()):
                        t_name = tc_data["name"].strip()
                        t_args = tc_data["arguments"].strip() or "{}"
                        if t_name:
                            yield ProviderStreamEvent(
                                delta=f'<tool_call>{{"name": "{t_name}", "arguments": {t_args}}}</tool_call>',
                                finish_reason="tool_calls",
                                usage=None,
                            )
            finally:
                try:
                    await client.close()
                except Exception:
                    pass
        except Exception as exc:
            raise self.normalize_error(exc) from exc

    def normalize_error(self, error: Exception) -> ProviderError:
        if isinstance(error, ProviderError):
            return error
        status_code = getattr(error, "status_code", None)
        name = error.__class__.__name__.lower()
        raw_message = str(error).strip() or "Groq request failed"
        lower_msg = raw_message.lower()

        # Check for tool mismatch or model-specific tool errors
        is_tool_error = "tool choice" in lower_msg or "called a tool" in lower_msg

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
        is_retryable = (code in _RETRYABLE) or is_tool_error or (status_code is None)
        return ProviderError(code, safe_message, provider=self.name, retryable=is_retryable, retry_after=retry_after)


def _usage_from_object(usage: object | None) -> UsageMetadata:
    if usage is None:
        return UsageMetadata()
    return UsageMetadata(
        input_tokens=getattr(usage, "prompt_tokens", None),
        output_tokens=getattr(usage, "completion_tokens", None),
        total_tokens=getattr(usage, "total_tokens", None),
    )


_RETRYABLE = {ProviderErrorCode.RATE_LIMIT, ProviderErrorCode.TIMEOUT, ProviderErrorCode.UNAVAILABLE}

