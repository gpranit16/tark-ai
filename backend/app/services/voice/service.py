import logging
from typing import Dict, Any, Optional

from app.core.config import get_settings
from app.services.voice.stt import BaseSTTProvider, GroqWhisperSTTProvider

logger = logging.getLogger(__name__)


class VoiceService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._stt_provider: Optional[BaseSTTProvider] = None

    def get_stt_provider(self) -> BaseSTTProvider:
        if self._stt_provider is None:
            self._stt_provider = GroqWhisperSTTProvider()
        return self._stt_provider

    def get_voice_config(self) -> Dict[str, Any]:
        """Return supported voice capabilities and defaults."""
        has_server_stt = bool(self.settings.groq_api_key)
        return {
            "browser_stt_supported": True,
            "browser_tts_supported": True,
            "server_stt_available": has_server_stt,
            "server_stt_provider": "groq_whisper" if has_server_stt else None,
            "default_language": "en-US",
            "features": {
                "barge_in": True,
                "sentence_chunking": True,
                "streaming_tts": True,
                "waveform_visualization": True,
            },
        }
