from abc import ABC, abstractmethod
from typing import Any


class BaseOCRProvider(ABC):
    @property
    @abstractmethod
    def provider_name(self) -> str:
        pass

    @abstractmethod
    async def extract_text(self, image_bytes: bytes) -> tuple[str, list[dict[str, Any]]]:
        """
        Extracts text from raw image bytes.
        Returns:
            (full_text_string, list_of_detected_blocks)
        """
        pass
