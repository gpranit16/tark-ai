from abc import ABC, abstractmethod
from uuid import UUID

from app.schemas.document import ParsedDocumentData


class BaseParser(ABC):
    @abstractmethod
    async def parse(
        self, content_bytes: bytes, file_id: UUID, filename: str, extension: str
    ) -> tuple[ParsedDocumentData, bool]:
        """
        Parses document bytes into ParsedDocumentData schema.
        Returns (ParsedDocumentData, ocr_used_bool).
        """
        pass
