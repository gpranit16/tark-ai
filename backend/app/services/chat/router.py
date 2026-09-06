import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
import logging

from app.core.config import Settings, get_settings
from app.core.enums import ConversationMode
from app.providers.base import (
    AIProvider,
    NormalizedMessage,
    ProviderError,
    ProviderErrorCode,
    ProviderName,
    ProviderStreamEvent,
)
from app.providers.gemini import GeminiProvider
from app.providers.groq import GroqProvider
from app.providers.mistral import MistralProvider

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProviderSelection:
    provider: AIProvider
    provider_name: ProviderName
    model: str
    fallback_used: bool = False


class ModelRouter:
    def __init__(self, providers: dict[ProviderName, AIProvider], settings: Settings | None = None) -> None:
        self.providers = providers
        self.settings = settings or get_settings()
        self.fallback_order = [ProviderName.GROQ, ProviderName.GEMINI, ProviderName.MISTRAL]

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "ModelRouter":
        settings = settings or get_settings()
        default_groq_model = settings.normal_model or "qwen/qwen3.8-27b"
        providers: dict[ProviderName, AIProvider] = {}

        if settings.groq_api_key or True:
            providers[ProviderName.GROQ] = GroqProvider(
                api_key=settings.groq_api_key,
                default_model=default_groq_model,
                timeout=settings.provider_timeout_seconds,
            )
        if settings.gemini_api_key:
            providers[ProviderName.GEMINI] = GeminiProvider(
                api_key=settings.gemini_api_key,
                default_model="gemini-2.5-flash",
                timeout=settings.provider_timeout_seconds,
            )
        if settings.mistral_api_key:
            providers[ProviderName.MISTRAL] = MistralProvider(
                api_key=settings.mistral_api_key,
                default_model="mistral-medium-latest",
                timeout=settings.provider_timeout_seconds,
            )

        return cls(providers, settings=settings)

    def select(
        self,
        *,
        mode: ConversationMode,
        provider: str | None = None,
        model: str | None = None,
        fallback_used: bool = False,
    ) -> ProviderSelection:
        provider_name = self._provider_name(provider) if provider else self._provider_for_mode(mode)
        selected_provider = self.providers.get(provider_name)
        if selected_provider is None:
            raise ProviderError(ProviderErrorCode.BAD_REQUEST, f"Unsupported or unconfigured provider: {provider_name}", provider=provider_name)

        if fallback_used:
            selected_model = selected_provider.default_model
        else:
            configured_model = model or self._model_for_mode(mode) or selected_provider.default_model
            selected_model = (configured_model or selected_provider.default_model).strip()
            if provider_name == ProviderName.GEMINI and not selected_model.startswith("gemini"):
                selected_model = selected_provider.default_model
            elif provider_name == ProviderName.MISTRAL and not selected_model.startswith("mistral"):
                selected_model = selected_provider.default_model
            elif provider_name == ProviderName.GROQ and selected_model in {"llama-3.3-70b-versatile", "llama-3.3-70b-specdec"}:
                selected_model = self._model_for_mode(mode) or "qwen/qwen3.8-27b"

        if not selected_model:
            selected_model = selected_provider.default_model
        return ProviderSelection(selected_provider, provider_name, selected_model, fallback_used=fallback_used)

    async def stream(
        self,
        *,
        messages: list[NormalizedMessage],
        mode: ConversationMode,
        provider: str | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[tuple[ProviderSelection, ProviderStreamEvent]]:
        attempted: set[ProviderName] = set()
        explicit_provider = provider is not None
        primary_selection: ProviderSelection | None = None
        primary_error: ProviderError | None = None

        while True:
            selection = self.select(
                mode=mode,
                provider=provider,
                model=model,
                fallback_used=bool(attempted),
            )
            if primary_selection is None:
                primary_selection = selection

            attempted.add(selection.provider_name)

            mode_str = mode.value if hasattr(mode, "value") else str(mode)
            prov_str = selection.provider_name.value if hasattr(selection.provider_name, "value") else str(selection.provider_name)
            logger.info(
                "[ROUTING] mode=%s provider=%s model=%s fallback=%s",
                mode_str,
                prov_str,
                selection.model,
                selection.fallback_used,
            )

            try:
                async for event in selection.provider.stream(
                    messages=messages, model=selection.model, mode=mode, max_tokens=max_tokens
                ):
                    yield selection, event
                return
            except ProviderError as exc:
                if primary_error is None:
                    primary_error = exc

                # If rate limited and retry_after is available and reasonable (<= 2.5s) on the primary attempt,
                # sleep briefly and retry once with same provider before initiating fallback cascade
                if (
                    exc.code == ProviderErrorCode.RATE_LIMIT
                    and exc.retry_after is not None
                    and exc.retry_after <= 20.0
                    and len(attempted) == 1
                ):
                    logger.warning(
                        "[RATE_LIMIT] Provider %s rate limited. Honoring Retry-After (%.2fs) before retry",
                        selection.provider_name.value,
                        exc.retry_after,
                    )
                    await asyncio.sleep(exc.retry_after + 0.5)
                    try:
                        async for event in selection.provider.stream(
                            messages=messages, model=selection.model, mode=mode, max_tokens=max_tokens
                        ):
                            yield selection, event
                        return
                    except ProviderError as retry_exc:
                        exc = retry_exc

                next_provider = self._next_fallback(exc, attempted, explicit_provider=explicit_provider)
                if next_provider is None:
                    # If fallback failed or wasn't available, report the primary provider error with clear context
                    if selection.fallback_used and primary_selection and primary_error:
                        logger.error(
                            "[ROUTING_FAILED] Primary provider '%s' failed (%s) and fallback '%s' also failed (%s)",
                            primary_selection.provider_name.value,
                            primary_error.message,
                            selection.provider_name.value,
                            exc.message,
                        )
                        raise ProviderError(
                            primary_error.code,
                            f"Primary provider '{primary_selection.provider_name.value}' request failed: {primary_error.message}",
                            provider=primary_selection.provider_name,
                            retryable=False,
                        )
                    raise exc

                logger.warning(
                    "[FALLBACK] primary=%s failed (%s). Attempting fallback to %s",
                    selection.provider_name.value,
                    exc.message,
                    next_provider.value,
                )
                provider = next_provider.value
                model = None  # Reset model so fallback provider uses its supported default model
                await asyncio.sleep(0.2 * len(attempted))

    def _provider_for_mode(self, mode: ConversationMode) -> ProviderName:
        value = {
            ConversationMode.FAST: self.settings.fast_provider,
            ConversationMode.NORMAL: self.settings.normal_provider,
            ConversationMode.REASONING: self.settings.reasoning_provider,
            ConversationMode.RAG: self.settings.rag_provider,
            ConversationMode.DEEP_RESEARCH: self.settings.deep_research_provider,
            ConversationMode.CODING: self.settings.coding_provider,
        }.get(mode) or self.settings.default_provider
        return self._provider_name(value)

    def _model_for_mode(self, mode: ConversationMode) -> str | None:
        return {
            ConversationMode.FAST: self.settings.fast_model,
            ConversationMode.NORMAL: self.settings.normal_model,
            ConversationMode.REASONING: self.settings.reasoning_model,
            ConversationMode.RAG: self.settings.rag_model or self.settings.normal_model,
            ConversationMode.DEEP_RESEARCH: self.settings.deep_research_model or self.settings.normal_model,
            ConversationMode.CODING: self.settings.coding_model,
        }.get(mode)

    def _provider_name(self, value: str) -> ProviderName:
        try:
            return ProviderName(value.lower())
        except ValueError as exc:
            raise ProviderError(ProviderErrorCode.BAD_REQUEST, f"Unsupported provider: {value}") from exc

    def _next_fallback(
        self,
        error: ProviderError,
        attempted: set[ProviderName],
        *,
        explicit_provider: bool,
    ) -> ProviderName | None:
        if not self.settings.auto_fallback or (explicit_provider and not self.settings.auto_fallback):
            return None
        if not error.retryable and error.code != ProviderErrorCode.AUTH_ERROR:
            return None
        for provider_name in self.fallback_order:
            if provider_name not in attempted and provider_name in self.providers:
                return provider_name
        return None

