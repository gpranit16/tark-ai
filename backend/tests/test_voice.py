import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.voice.service import VoiceService
from app.services.voice.stt import GroqWhisperSTTProvider


def test_voice_service_config():
    service = VoiceService()
    config = service.get_voice_config()
    assert config["browser_stt_supported"] is True
    assert config["browser_tts_supported"] is True
    assert "features" in config
    assert config["features"]["barge_in"] is True
    assert config["features"]["sentence_chunking"] is True
    assert config["features"]["streaming_tts"] is True


@pytest.mark.asyncio
async def test_groq_whisper_missing_key():
    provider = GroqWhisperSTTProvider(api_key="")
    with pytest.raises(ValueError, match="Groq API key not configured"):
        await provider.transcribe(b"dummy audio", "audio.wav")


@pytest.mark.asyncio
async def test_groq_whisper_transcription_success():
    provider = GroqWhisperSTTProvider(api_key="test-groq-key")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"text": "Hello, how are you today?"}

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        text = await provider.transcribe(b"fake-audio-bytes", "test.wav", language="en")
        assert text == "Hello, how are you today?"
        mock_post.assert_called_once()
