from app.core.config import get_settings
from app.services.vision.base import BaseVisionProvider


class GeminiVisionProvider(BaseVisionProvider):
    def __init__(self) -> None:
        settings = get_settings()
        self.api_key = settings.gemini_api_key

    @property
    def provider_name(self) -> str:
        return "gemini"

    async def analyze_image(self, image_bytes: bytes, prompt: str | None = None) -> str:
        if not self.api_key:
            return "[Gemini Vision] API key not configured."
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=self.api_key)
            prompt_text = prompt or "Describe the contents of this image in detail."
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[
                    types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                    prompt_text,
                ]
            )
            return response.text or ""
        except Exception as e:
            return f"[Gemini Vision Error] {str(e)}"
