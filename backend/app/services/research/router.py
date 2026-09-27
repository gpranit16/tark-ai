"""
Task-based Model Selection for Deep Research 2.0.

Selects the most efficient and capable provider and model for each individual
research sub-task using TARK's existing ModelRouter and provider abstraction.

Rules:
- For Gemini, uses ONLY 'gemini-3.5-flash-lite'.
- Simple/fast tasks (classification, query generation, image planning) prefer
  fast/cheap models (e.g. Groq Qwen).
- Heavy workloads (research planning, complex evidence reasoning, section planning,
  difficult synthesis) utilize Gemini 3.5 Flash-Lite or strong reasoning fallbacks.
- Deterministic tasks (dedup, recency, canonical URL, URL validation) run in pure Python.
- Uses existing provider clients (no duplicate HTTP clients).
"""
from __future__ import annotations

from enum import StrEnum
import logging
from typing import NamedTuple

from app.core.config import get_settings
from app.providers.base import ProviderName
from app.services.chat.router import ModelRouter

logger = logging.getLogger(__name__)


class ResearchTaskType(StrEnum):
    CLASSIFICATION = "classification"
    QUERY_GENERATION = "query_generation"
    RESEARCH_PLANNING = "research_planning"
    SECTION_WORKER = "section_worker"
    EVIDENCE_VERIFICATION = "evidence_verification"
    SYNTHESIS = "synthesis"
    IMAGE_PLANNING = "image_planning"


class ModelDecision(NamedTuple):
    provider: str
    model: str
    reason: str
    fallback_provider: str | None = None
    fallback_model: str | None = None


def select_research_model(
    task_type: ResearchTaskType,
    router: ModelRouter | None = None,
    explicit_provider: str | None = None,
    explicit_model: str | None = None,
    settings: Any | None = None,
) -> ModelDecision:
    """
    Intelligently select the best provider and model for a specific research task.
    Honors user explicit overrides if provided.
    """
    settings = settings or get_settings()
    gemini_model = settings.deep_research_gemini_model or "gemini-3.5-flash-lite"
    # Rule: For Gemini, use ONLY gemini-3.5-flash-lite
    if explicit_provider == "gemini" and (not explicit_model or "2.5" in explicit_model):
        explicit_model = gemini_model

    # For heavy research tasks (Synthesis, Planning), general chat defaults (e.g. Groq Qwen 3.8 27B)
    # from the UI should NOT override the dedicated heavy research engine (Gemini 3.5 Flash-Lite).
    is_general_chat_default = (
        explicit_provider in ("groq", "mistral")
        and explicit_model in ("qwen/qwen3.8-27b", "qwen/qwen3.6-27b", "mistral-medium-latest", "llama-3.1-8b-instant")
    )
    is_heavy_task = task_type in (ResearchTaskType.SYNTHESIS, ResearchTaskType.RESEARCH_PLANNING)

    if explicit_provider and explicit_model and not (is_heavy_task and is_general_chat_default):
        return ModelDecision(
            provider=explicit_provider,
            model=explicit_model,
            reason=f"User/explicit override for {task_type.value}",
        )

    router_providers = getattr(router, "providers", None)
    if isinstance(router_providers, dict) and router_providers:
        available_providers = set(router_providers.keys())
    else:
        available_providers = {
            ProviderName.GROQ if settings.groq_api_key else None,
            ProviderName.GEMINI if settings.gemini_api_key else None,
            ProviderName.NVIDIA if settings.nvidia_api_key else None,
            ProviderName.MISTRAL if settings.mistral_api_key else None,
        }
    available_providers.discard(None)

    has_gemini = ProviderName.GEMINI in available_providers and bool(settings.gemini_api_key)
    has_groq = ProviderName.GROQ in available_providers and bool(settings.groq_api_key)
    has_nvidia = ProviderName.NVIDIA in available_providers and bool(settings.nvidia_api_key)
    has_mistral = ProviderName.MISTRAL in available_providers and bool(settings.mistral_api_key)

    # 1. Fast / lightweight tasks (Classification, Image Planning) -> Groq / NVIDIA
    if task_type in (ResearchTaskType.CLASSIFICATION, ResearchTaskType.IMAGE_PLANNING):
        if has_groq:
            return ModelDecision(
                provider="groq",
                model="qwen/qwen3.6-27b",
                reason="Ultra-fast structured output via Groq Qwen",
                fallback_provider="nvidia" if has_nvidia else ("gemini" if has_gemini else None),
                fallback_model=settings.nvidia_model if has_nvidia else (gemini_model if has_gemini else None),
            )
        elif has_nvidia:
            return ModelDecision(
                provider="nvidia",
                model=settings.fast_model or "meta/llama-3.2-11b-vision-instruct",
                reason="Fast structured output via NVIDIA",
                fallback_provider="gemini" if has_gemini else None,
                fallback_model=gemini_model if has_gemini else None,
            )
        elif has_gemini:
            return ModelDecision(
                provider="gemini",
                model=gemini_model,
                reason="Gemini fallback for structured classification",
            )

    # 2. Query Generation (multi-angle search planning) -> Groq Qwen 3.8
    if task_type == ResearchTaskType.QUERY_GENERATION:
        if has_groq:
            return ModelDecision(
                provider="groq",
                model="qwen/qwen3.8-27b",
                reason="Fast high-diversity query generation via Groq Qwen",
                fallback_provider="nvidia" if has_nvidia else ("gemini" if has_gemini else None),
                fallback_model=settings.nvidia_model if has_nvidia else (gemini_model if has_gemini else None),
            )
        elif has_nvidia:
            return ModelDecision(
                provider="nvidia",
                model=settings.nvidia_model or "meta/llama-3.2-11b-vision-instruct",
                reason="Query generation via NVIDIA",
                fallback_provider="gemini" if has_gemini else None,
                fallback_model=gemini_model if has_gemini else None,
            )
        elif has_gemini:
            return ModelDecision(
                provider="gemini",
                model=gemini_model,
                reason="Gemini fallback for query generation",
            )

    # 3. Section Workers (Parallel deep section drafting) -> NVIDIA Nemotron / Mistral / Groq
    # Keeps Gemini tokens reserved for final synthesis while getting detailed parallel sub-topic drafts
    if task_type == ResearchTaskType.SECTION_WORKER:
        if has_nvidia:
            return ModelDecision(
                provider="nvidia",
                model="nvidia/nemotron-3.5-lightning-30b-a3b",
                reason="NVIDIA Nemotron for detailed analytical section drafting",
                fallback_provider="groq" if has_groq else ("mistral" if has_mistral else ("gemini" if has_gemini else None)),
                fallback_model="qwen/qwen3.8-27b" if has_groq else ("mistral-medium-latest" if has_mistral else (gemini_model if has_gemini else None)),
            )
        elif has_groq:
            return ModelDecision(
                provider="groq",
                model="qwen/qwen3.8-27b",
                reason="Groq Qwen 3.8 for parallel section investigation",
                fallback_provider="mistral" if has_mistral else ("gemini" if has_gemini else None),
                fallback_model="mistral-medium-latest" if has_mistral else (gemini_model if has_gemini else None),
            )
        elif has_mistral:
            return ModelDecision(
                provider="mistral",
                model="mistral-medium-latest",
                reason="Mistral for deep section investigation",
                fallback_provider="gemini" if has_gemini else None,
                fallback_model=gemini_model if has_gemini else None,
            )
        elif has_gemini:
            return ModelDecision(
                provider="gemini",
                model=gemini_model,
                reason="Gemini section drafting",
            )

    # 4. Evidence Verification -> NVIDIA / Groq (Fast fact cross-check)
    if task_type == ResearchTaskType.EVIDENCE_VERIFICATION:
        if has_nvidia:
            return ModelDecision(
                provider="nvidia",
                model="nvidia/nemotron-3.5-lightning-30b-a3b",
                reason="NVIDIA fact-checking & verification reasoning",
                fallback_provider="groq" if has_groq else ("gemini" if has_gemini else None),
                fallback_model="qwen/qwen3.8-27b" if has_groq else (gemini_model if has_gemini else None),
            )
        elif has_groq:
            return ModelDecision(
                provider="groq",
                model="qwen/qwen3.8-27b",
                reason="Groq fast evidence verification",
                fallback_provider="gemini" if has_gemini else None,
                fallback_model=gemini_model if has_gemini else None,
            )
        elif has_gemini:
            return ModelDecision(
                provider="gemini",
                model=gemini_model,
                reason="Gemini evidence verification",
            )

    # 5. Research Planning & Master Synthesis (Major Core Brain) -> Gemini 3.5 Flash-Lite
    # Uses Gemini's large context, strict grounding, and narrative reasoning for the final report
    if task_type in (ResearchTaskType.RESEARCH_PLANNING, ResearchTaskType.SYNTHESIS):
        if has_gemini:
            return ModelDecision(
                provider="gemini",
                model=gemini_model,
                reason="Gemini 3.5 Flash-Lite for master research planning and comprehensive final synthesis",
                fallback_provider="nvidia" if has_nvidia else ("groq" if has_groq else None),
                fallback_model="nvidia/nemotron-3.5-lightning-30b-a3b" if has_nvidia else ("qwen/qwen3.8-27b" if has_groq else None),
            )
        elif has_nvidia:
            return ModelDecision(
                provider="nvidia",
                model="nvidia/nemotron-3.5-lightning-30b-a3b",
                reason="NVIDIA Nemotron master synthesis fallback",
                fallback_provider="groq" if has_groq else None,
                fallback_model="qwen/qwen3.8-27b" if has_groq else None,
            )
        elif has_groq:
            return ModelDecision(
                provider="groq",
                model="qwen/qwen3.8-27b",
                reason="Groq Qwen master synthesis fallback",
            )

    # Default fallback
    default_p = settings.default_provider or "groq"
    default_m = settings.normal_model or "qwen/qwen3.8-27b"
    return ModelDecision(
        provider=default_p,
        model=default_m,
        reason="Default system provider selection",
    )
