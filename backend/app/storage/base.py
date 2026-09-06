from abc import ABC, abstractmethod
from typing import BinaryIO

class StorageProvider(ABC):
    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the name of the storage provider (e.g. 'local', 'b2')."""
        pass

    @abstractmethod
    async def upload(self, file: BinaryIO, storage_key: str, mime_type: str) -> None:
        """Upload a file stream to the storage provider."""
        pass

    @abstractmethod
    async def delete(self, storage_key: str) -> None:
        """Delete a file from the storage provider."""
        pass

    @abstractmethod
    async def download(self, storage_key: str) -> bytes:
        """Download file bytes from the storage provider."""
        pass

    @abstractmethod
    async def exists(self, storage_key: str) -> bool:
        """Check if a file exists in the storage provider."""
        pass
