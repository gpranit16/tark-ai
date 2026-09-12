from collections.abc import AsyncIterator
import json
import logging
import re
from typing import Any

import httpx

from app.core.config import get_settings
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

logger = logging.getLogger(__name__)

_RETRYABLE = {ProviderErrorCode.RATE_LIMIT, ProviderErrorCode.TIMEOUT, ProviderErrorCode.UNAVAILABLE}


class NvidiaProvider(AIProvider):
    name = ProviderName.NVIDIA

    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str = "https://integrate.api.nvidia.com/v1",
        default_model: str = "nvidia/nemotron-3.5-lightning-30b-a3b",
        timeout: float = 60.0,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/") if base_url else "https://integrate.api.nvidia.com/v1"
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
            raise ProviderError(
                ProviderErrorCode.AUTH_ERROR,
                "NVIDIA API key is not configured",
                provider=self.name,
            )

        endpoint = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }

        # Token budget resolution
        if max_tokens is not None:
            resolved_max_tokens = min(max_tokens, 4096)
        elif mode == ConversationMode.FAST:
            resolved_max_tokens = 1024
        else:
            resolved_max_tokens = 4096

        msg_payload = [
            {
                "role": "user" if message.role.value == "tool" else message.role.value,
                "content": message.content or " ",
            }
            for message in messages
            if (message.content or "").strip()
        ]

        payload: dict[str, Any] = {
            "model": model or self.default_model,
            "messages": msg_payload,
            "stream": True,
            "max_tokens": resolved_max_tokens,
            "temperature": 0.7,
            "top_p": 0.9,
        }

        timeout_config = httpx.Timeout(self.timeout, connect=15.0, read=self.timeout)
        try:
            async with httpx.AsyncClient(timeout=timeout_config) as client:
                async with client.stream("POST", endpoint, headers=headers, json=payload) as response:
                    if response.status_code != 200:
                        content = await response.aread()
                        err_text = content.decode("utf-8", errors="replace")
                        raise self._build_http_error(response.status_code, err_text, response.headers)

                    in_think_block = False
                    buffer = ""
                    tool_calls_acc: dict[int, dict[str, str]] = {}

                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        line = line.strip()
                        if not line.startswith("data:"):
                            continue

                        raw_data = line[5:].strip()
                        if raw_data == "[DONE]":
                            break

                        try:
                            chunk = json.loads(raw_data)
                        except json.JSONDecodeError:
                            continue

                        choices = chunk.get("choices", [])
                        choice = choices[0] if choices else None
                        delta_text = ""
                        finish_reason = None

                        if choice is not None:
                            delta_obj = choice.get("delta", {})
                            content_chunk = delta_obj.get("content") or ""
                            finish_reason = choice.get("finish_reason")

                            # Accumulate native tool_calls in stream delta if sent by model
                            tool_calls = delta_obj.get("tool_calls")
                            if tool_calls:
                                for tc in tool_calls:
                                    idx = tc.get("index", 0) or 0
                                    if idx not in tool_calls_acc:
                                        tool_calls_acc[idx] = {"name": "", "arguments": ""}
                                    fn = tc.get("function")
                                    if fn:
                                        fn_name = fn.get("name")
                                        fn_args = fn.get("arguments")
                                        if fn_name:
                                            tool_calls_acc[idx]["name"] += fn_name
                                        if fn_args:
                                            tool_calls_acc[idx]["arguments"] += fn_args

                            if content_chunk:
                                buffer += content_chunk
                                while True:
                                    if not in_think_block:
                                        if "<think>" in buffer:
                                            before, _, after = buffer.partition("<think>")
                                            delta_text += before
                                            buffer = after
                                            in_think_block = True
                                        else:
                                            matched_prefix = False
                                            for prefix_len in range(len("<think>") - 1, 0, -1):
                                                if buffer.endswith("<think>"[:prefix_len]):
                                                    delta_text += buffer[:-prefix_len]
                                                    buffer = buffer[-prefix_len:]
                                                    matched_prefix = True
                                                    break
                                            if not matched_prefix:
                                                delta_text += buffer
                                                buffer = ""
                                            break
                                    else:
                                        if "</think>" in buffer:
                                            _, _, after = buffer.partition("</think>")
                                            buffer = after
                                            in_think_block = False
                                        else:
                                            matched_prefix = False
                                            for prefix_len in range(len("</think>") - 1, 0, -1):
                                                if buffer.endswith("</think>"[:prefix_len]):
                                                    buffer = buffer[-prefix_len:]
                                                    matched_prefix = True
                                                    break
                                            if not matched_prefix:
                                                buffer = ""
                                            break

                        usage = chunk.get("usage")
                        if delta_text:
                            yield ProviderStreamEvent(
                                delta=delta_text,
                                finish_reason=finish_reason,
                                usage=_usage_from_dict(usage) if usage else None,
                            )

                    # Flush accumulated tool calls if any
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

                    # Flush any remaining buffer if not in think block
                    if buffer and not in_think_block:
                        yield ProviderStreamEvent(delta=buffer)

        except Exception as exc:
            raise self.normalize_error(exc) from exc

    def _build_http_error(self, status_code: int, raw_text: str, headers: httpx.Headers | None = None) -> Exception:
        """Create a custom error holding status_code, message, and headers."""
        err = Exception(raw_text)
        err.status_code = status_code  # type: ignore[attr-defined]
        if headers:
            err.headers = headers  # type: ignore[attr-defined]
        return err

    def normalize_error(self, error: Exception) -> ProviderError:
        if isinstance(error, ProviderError):
            return error

        status_code = getattr(error, "status_code", None)
        name = error.__class__.__name__.lower()
        raw_message = str(error).strip() or "NVIDIA request failed"
        lower_msg = raw_message.lower()

        if "authentication" in name or status_code in {401, 403} or "unauthorized" in lower_msg:
            code = ProviderErrorCode.AUTH_ERROR
        elif "rate" in name or status_code == 429 or "quota" in lower_msg:
            code = ProviderErrorCode.RATE_LIMIT
        elif "timeout" in name or isinstance(error, httpx.TimeoutException):
            code = ProviderErrorCode.TIMEOUT
        elif status_code in {400, 404, 422}:
            code = ProviderErrorCode.BAD_REQUEST
        elif status_code and status_code >= 500:
            code = ProviderErrorCode.UNAVAILABLE
        else:
            code = ProviderErrorCode.UNKNOWN

        # Extract Retry-After if provided
        retry_after: float | None = None
        headers = getattr(error, "headers", None)
        if headers:
            ra = headers.get("retry-after") or headers.get("Retry-After")
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

        # Redact API key
        sanitized_message = raw_message.replace(self.api_key, "[REDACTED]") if self.api_key else raw_message
        safe_message = (
            f"NVIDIA provider request failed: {error.__class__.__name__}"
            f" (status={status_code}) {sanitized_message}"
        )
        is_retryable = (code in _RETRYABLE) or (status_code is None)
        return ProviderError(
            code,
            safe_message,
            provider=self.name,
            retryable=is_retryable,
            retry_after=retry_after,
        )


def _usage_from_dict(usage: dict[str, Any] | None) -> UsageMetadata:
    if not usage or not isinstance(usage, dict):
        return UsageMetadata()
    return UsageMetadata(
        input_tokens=usage.get("prompt_tokens"),
        output_tokens=usage.get("completion_tokens"),
        total_tokens=usage.get("total_tokens"),
    )
