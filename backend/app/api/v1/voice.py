import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.api.v1.auth_deps import get_current_user
from app.models.conversation import User
from app.services.voice.service import VoiceService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/voice", tags=["voice"])


@router.get("/config")
async def get_voice_config(
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Get supported voice features and configuration for authenticated user."""
    service = VoiceService()
    return service.get_voice_config()


@router.post("/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...),
    language: Optional[str] = Form(default=None),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Transcribe uploaded audio file to text using server STT provider."""
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Audio file must have a filename.")

    audio_bytes = await file.read()
    if len(audio_bytes) == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty audio payload.")
    if len(audio_bytes) > 25 * 1024 * 1024:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Audio file exceeds 25MB limit.")

    service = VoiceService()
    stt_provider = service.get_stt_provider()

    try:
        text = await stt_provider.transcribe(audio_bytes, filename=file.filename, language=language)
        return {"text": text, "language": language}
    except ValueError as val_err:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(val_err))
    except Exception as exc:
        logger.error("Voice transcription failed for user %s: %s", current_user.id, exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Transcription failed: {exc}")
