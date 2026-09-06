from abc import ABC, abstractmethod


class BaseVisionProvider(ABC):
    @property
    @abstractmethod
    def provider_name(self) -> str:
        pass

    @abstractmethod
    async def analyze_image(self, image_bytes: bytes, prompt: str | None = None) -> str:
        """
        Analyzes image bytes and returns textual analysis/description.
        """
        pass
