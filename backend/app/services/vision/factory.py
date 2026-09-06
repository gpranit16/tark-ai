import os
from app.services.vision.base import BaseVisionProvider
from app.services.vision.gemini import GeminiVisionProvider
from app.services.vision.mock import MockVisionProvider


def get_vision_provider() -> BaseVisionProvider:
    provider = os.environ.get("VISION_PROVIDER", "mock").lower()
    if provider == "gemini":
        return GeminiVisionProvider()
    return MockVisionProvider()
