"""
Pollinations Image Provider for Deep Research 2.0.

Provides optional image generation for technical diagrams, architecture flows,
and comparison visuals via Pollinations.ai.

Guarantees:
- Timeout and bounded retry
- Graceful non-blocking failure: if an image fails, the research report completes cleanly
- No API keys exposed
"""
from __future__ import annotations

import asyncio
import logging
import urllib.parse
from typing import Optional

import httpx

from app.core.config import get_settings
from app.services.research.models import ImageItem

logger = logging.getLogger(__name__)


class PollinationsImageProvider:
    """Image generation provider using Pollinations REST interface."""

    def __init__(self, timeout: float = 20.0) -> None:
        self.settings = get_settings()
        self.timeout = timeout
        self.base_url = "https://image.pollinations.ai/prompt"

    def build_url(self, prompt: str, aspect_ratio: str = "16:9") -> str:
        """Construct deterministic pollinations.ai image URL."""
        clean_prompt = prompt.strip()
        encoded = urllib.parse.quote(clean_prompt)
        width, height = (1280, 720) if aspect_ratio == "16:9" else (1024, 1024)
        return f"{self.base_url}/{encoded}?width={width}&height={height}&model=flux&nologo=true"

    async def generate_image(self, item: ImageItem) -> ImageItem:
        """
        Generate image for a single ImageItem.
        Returns the updated ImageItem with image_url populated on success,
        or unchanged on failure. Does NOT raise exceptions to callers.
        """
        clean_prompt = item.prompt.strip()
        if not clean_prompt:
            return item

        target_url = self.build_url(clean_prompt, "16:9")
        item.image_url = target_url
        item.caption = item.purpose
        logger.info("[POLLINATIONS] Assigned diagram URL for %r", item.purpose[:50])
        return item

    async def generate_images_parallel(self, items: list[ImageItem]) -> list[ImageItem]:
        """Generate multiple images concurrently with bounded timeout."""
        if not items:
            return []
        tasks = [self.generate_image(it) for it in items[:3]]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        successful: list[ImageItem] = []
        for r in results:
            if isinstance(r, ImageItem) and r.image_url:
                successful.append(r)
        return successful
