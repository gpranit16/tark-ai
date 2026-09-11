from abc import ABC, abstractmethod
import io
import logging
from typing import Optional
import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class BaseSTTProvider(ABC):
    @abstractmethod
    async def transcribe(self, audio_bytes: bytes, filename: str = "audio.wav", language: Optional[str] = None) -> str:
        """Transcribe audio bytes to text."""
        pass


class GroqWhisperSTTProvider(BaseSTTProvider):
    """Server-side STT using Groq's whisper-large-v3 model."""

    def __init__(self, api_key: Optional[str] = None) -> None:
        settings = get_settings()
        self.api_key = api_key if api_key is not None else settings.groq_api_key
        self.base_url = "https://api.groq.com/openai/v1/audio/transcriptions"

    async def transcribe(self, audio_bytes: bytes, filename: str = "audio.wav", language: Optional[str] = None) -> str:
        if not self.api_key:
            raise ValueError("Groq API key not configured for server-side STT.")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
        }
        files = {
            "file": (filename, audio_bytes, "audio/wav"),
        }
        data = {
            "model": "whisper-large-v3",
            "response_format": "json",
        }
        if language:
            data["language"] = language

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(self.base_url, headers=headers, files=files, data=data)
            if resp.status_code != 200:
                err_msg = resp.text
                logger.error("Groq Whisper STT failed: %s (status %d)", err_msg, resp.status_code)
                raise RuntimeError(f"Transcription failed: {resp.status_code}")

            result = resp.json()
            return result.get("text", "").strip()
