from app.services.vision.base import BaseVisionProvider


class MockVisionProvider(BaseVisionProvider):
    @property
    def provider_name(self) -> str:
        return "mock"

    async def analyze_image(self, image_bytes: bytes, prompt: str | None = None) -> str:
        return "[Mock Vision] Image processed successfully."
