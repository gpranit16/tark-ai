from collections.abc import AsyncIterator

from app.core.enums import ConversationMode, MessageRole
from app.providers.base import (
    AIProvider,
    NormalizedMessage,
    ProviderError,
    ProviderErrorCode,
    ProviderName,
    ProviderStreamEvent,
    UsageMetadata,
)


class GeminiProvider(AIProvider):
    name = ProviderName.GEMINI

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
            raise ProviderError(ProviderErrorCode.AUTH_ERROR, "Gemini API key is not configured", provider=self.name)
        try:
            from google import genai
            from google.genai import types

            contents = _to_gemini_contents(messages)
            config_kwargs: dict[str, object] = {
                "system_instruction": _system_instruction(messages) or None,
            }
            if max_tokens is not None:
                config_kwargs["max_output_tokens"] = max_tokens

            config = types.GenerateContentConfig(**config_kwargs)
            async with genai.Client(api_key=self.api_key).aio as client:
                stream = await client.models.generate_content_stream(
                    model=model,
                    contents=contents,
                    config=config,
                )
                async for chunk in stream:
                    yield ProviderStreamEvent(delta=getattr(chunk, "text", "") or "", usage=_usage_from_chunk(chunk))
        except Exception as exc:
            raise self.normalize_error(exc) from exc

    def normalize_error(self, error: Exception) -> ProviderError:
        if isinstance(error, ProviderError):
            return error
        status_code = getattr(error, "code", None) or getattr(error, "status_code", None)
        name = error.__class__.__name__.lower()
        if status_code in {401, 403} or "permission" in name or "unauth" in name:
            code = ProviderErrorCode.AUTH_ERROR
        elif status_code == 429 or "quota" in name or "rate" in name:
            code = ProviderErrorCode.RATE_LIMIT
        elif "timeout" in name:
            code = ProviderErrorCode.TIMEOUT
        elif status_code in {400, 404}:
            code = ProviderErrorCode.BAD_REQUEST
        elif status_code and status_code >= 500:
            code = ProviderErrorCode.UNAVAILABLE
        else:
            code = ProviderErrorCode.UNKNOWN
        return ProviderError(code, "Gemini provider request failed", provider=self.name, retryable=code in _RETRYABLE)


def _system_instruction(messages: list[NormalizedMessage | dict]) -> str:
    system_parts = []
    for msg in messages:
        role = msg.get("role") if isinstance(msg, dict) else getattr(msg, "role", None)
        content = msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", "")
        if role == MessageRole.SYSTEM or role == "system":
            if content:
                system_parts.append(str(content))
    return "\n".join(system_parts)


def _to_gemini_contents(messages: list[NormalizedMessage | dict]) -> list[dict[str, object]]:
    role_map = {
        MessageRole.USER: "user",
        MessageRole.ASSISTANT: "model",
        MessageRole.TOOL: "user",
        "user": "user",
        "assistant": "model",
        "system": "user",
        "tool": "user",
    }
    contents: list[dict[str, object]] = []
    for message in messages:
        role = message.get("role") if isinstance(message, dict) else getattr(message, "role", "user")
        if role == MessageRole.SYSTEM or role == "system":
            continue
        # Gemini requires non-empty content; skip blank messages to avoid:
        # "model output must contain either output text or tool calls, cannot both be empty"
        content = message.get("content") if isinstance(message, dict) else getattr(message, "content", "")
        text = (content or "").strip()
        if not text:
            continue
        g_role = role_map.get(role, "user")
        if contents and contents[-1]["role"] == g_role:
            contents[-1]["parts"].append({"text": text})
        else:
            contents.append({"role": g_role, "parts": [{"text": text}]})

    # Gemini requires conversations to start with a "user" turn
    if contents and contents[0]["role"] != "user":
        contents.insert(0, {"role": "user", "parts": [{"text": " "}]})

    # Ensure turns strictly alternate user/model; merge consecutive same-role turns
    merged: list[dict[str, object]] = []
    for entry in contents:
        if merged and merged[-1]["role"] == entry["role"]:
            merged[-1]["parts"].extend(entry["parts"])  # type: ignore[attr-defined]
        else:
            merged.append(entry)
    return merged


def _usage_from_chunk(chunk: object) -> UsageMetadata:
    usage = getattr(chunk, "usage_metadata", None)
    if usage is None:
        return UsageMetadata()
    return UsageMetadata(
        input_tokens=getattr(usage, "prompt_token_count", None),
        output_tokens=getattr(usage, "candidates_token_count", None),
        total_tokens=getattr(usage, "total_token_count", None),
    )


_RETRYABLE = {ProviderErrorCode.RATE_LIMIT, ProviderErrorCode.TIMEOUT, ProviderErrorCode.UNAVAILABLE}
