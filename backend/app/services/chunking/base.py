from abc import ABC, abstractmethod
from typing import Any
from uuid import UUID

from app.schemas.document import ParsedDocumentData


class BaseChunker(ABC):
    @abstractmethod
    def chunk_document(
        self,
        doc_data: ParsedDocumentData,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Chunks parsed document data into normalized chunk items.
        Returns: list of dicts with keys:
            - chunk_index: int
            - content: str
            - page_number: int
            - metadata: dict[str, Any]
        """
        pass
