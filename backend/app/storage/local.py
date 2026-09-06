import os
from pathlib import Path
from typing import BinaryIO

from fastapi import HTTPException
from app.storage.base import StorageProvider


class LocalStorageProvider(StorageProvider):
    def __init__(self, upload_dir: str = "uploads"):
        self.upload_dir = Path(upload_dir)
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    @property
    def provider_name(self) -> str:
        return "local"

    def _get_full_path(self, storage_key: str) -> Path:
        # Prevent path traversal by resolving and checking against upload_dir
        path = (self.upload_dir / storage_key).resolve()
        if not str(path).startswith(str(self.upload_dir.resolve())):
            raise HTTPException(status_code=400, detail="Invalid storage key structure.")
        return path

    async def upload(self, file: BinaryIO, storage_key: str, mime_type: str) -> None:
        file_path = self._get_full_path(storage_key)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(file_path, "wb") as buffer:
            # chunked write could be used here but assuming file is read stream
            while chunk := file.read(8192):
                buffer.write(chunk)

    async def delete(self, storage_key: str) -> None:
        file_path = self._get_full_path(storage_key)
        try:
            file_path.unlink(missing_ok=True)
        except Exception:
            pass

    async def download(self, storage_key: str) -> bytes:
        file_path = self._get_full_path(storage_key)
        if not file_path.exists():
            raise HTTPException(status_code=404, detail=f"File not found in local storage: {storage_key}")
        with open(file_path, "rb") as f:
            return f.read()

    async def exists(self, storage_key: str) -> bool:
        file_path = self._get_full_path(storage_key)
        return file_path.exists()
