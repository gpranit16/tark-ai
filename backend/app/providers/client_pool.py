"""Provider HTTP client pool.

Caches async HTTP clients keyed by (provider, api_key) so that connection
pools and auth headers are reused across requests rather than rebuilt on
every chat turn.  Clients are lightweight objects — the real savings are
the underlying httpx connection pools they carry.

Thread-safety: asyncio is single-threaded per event-loop so a plain dict
is safe.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Keyed by (provider_name, api_key) → client instance
_client_cache: dict[tuple[str, ...], Any] = {}


def get_groq_client(api_key: str, timeout: float) -> Any:
    """Return a cached AsyncGroq client for the given key."""
    cache_key = ("groq", api_key)
    client = _client_cache.get(cache_key)
    if client is None:
        from groq import AsyncGroq  # lazy import keeps startup fast
        client = AsyncGroq(api_key=api_key, timeout=timeout, max_retries=0)
        _client_cache[cache_key] = client
        logger.debug("ProviderPool: created new AsyncGroq client (pool size=%d)", len(_client_cache))
    return client


def get_openai_compat_client(api_key: str, base_url: str, timeout: float) -> Any:
    """Return a cached AsyncOpenAI-compatible client (used by NVIDIA/Mistral)."""
    cache_key = ("openai_compat", api_key, base_url)
    client = _client_cache.get(cache_key)
    if client is None:
        from openai import AsyncOpenAI  # lazy import
        client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=timeout, max_retries=0)
        _client_cache[cache_key] = client
        logger.debug("ProviderPool: created new AsyncOpenAI client base_url=%s (pool size=%d)", base_url, len(_client_cache))
    return client


def clear_pool() -> None:
    """Flush all cached clients — useful in tests."""
    _client_cache.clear()
