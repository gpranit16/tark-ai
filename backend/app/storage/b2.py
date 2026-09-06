from __future__ import annotations

import base64
import hashlib
import urllib.parse
from typing import BinaryIO

import httpx
from fastapi import HTTPException

from app.core.config import get_settings
from app.storage.base import StorageProvider


def validate_storage_key(storage_key: str) -> str:
    """Validate storage key to prevent path traversal, null bytes, or dangerous prefixes."""
    if not storage_key or not isinstance(storage_key, str):
        raise HTTPException(status_code=400, detail="Invalid storage key: key cannot be empty.")
    
    if "\0" in storage_key:
        raise HTTPException(status_code=400, detail="Invalid storage key: null bytes are not allowed.")
    
    # Normalize separators
    normalized = storage_key.replace("\\", "/").strip()
    
    # Reject leading slashes and traversal segments
    if normalized.startswith("/"):
        raise HTTPException(status_code=400, detail="Invalid storage key: leading slash not allowed.")
    
    segments = normalized.split("/")
    for segment in segments:
        if segment in ("..", "."):
            raise HTTPException(status_code=400, detail="Invalid storage key: directory traversal detected.")
    
    return normalized


class B2StorageProvider(StorageProvider):
    def __init__(
        self,
        key_id: str | None = None,
        application_key: str | None = None,
        bucket_name: str | None = None,
        endpoint: str | None = None,
    ):
        settings = get_settings()
        self.key_id = key_id or settings.b2_key_id
        self.application_key = application_key or settings.b2_application_key
        self.bucket_name = bucket_name or settings.b2_bucket_name
        self.endpoint = endpoint or settings.b2_endpoint

        if not self.key_id or not self.application_key or not self.bucket_name:
            raise ValueError("B2 credentials and bucket name must be provided to use B2StorageProvider.")

        # Internal cached state
        self.api_url: str | None = None
        self.authorization_token: str | None = None
        self.download_url: str | None = None
        self.bucket_id: str | None = None

    @property
    def provider_name(self) -> str:
        return "b2"

    async def _authorize(self, force_refresh: bool = False) -> None:
        """Authenticate against Backblaze B2 v3 API and cache tokens."""
        if self.authorization_token and not force_refresh:
            return

        id_and_key = f"{self.key_id}:{self.application_key}"
        basic_auth_string = "Basic " + base64.b64encode(id_and_key.encode()).decode()
        headers = {"Authorization": basic_auth_string}

        auth_endpoint = "https://api.backblazeb2.com/b2api/v3/b2_authorize_account"

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(auth_endpoint, headers=headers)
            except Exception as e:
                raise HTTPException(status_code=502, detail="Unable to connect to B2 authorization service.")

            if response.status_code != 200:
                raise HTTPException(
                    status_code=500,
                    detail=f"B2 authorization failed with status {response.status_code}."
                )

            data = response.json()
            storage_api = data.get("apiInfo", {}).get("storageApi", {})
            self.api_url = storage_api.get("apiUrl") or data.get("apiUrl")
            self.download_url = storage_api.get("downloadUrl") or data.get("downloadUrl")
            self.authorization_token = data.get("authorizationToken")

            # Check if bucketId is scoped directly in authorization response
            if storage_api.get("bucketId") and (storage_api.get("bucketName") == self.bucket_name or not self.bucket_name):
                self.bucket_id = storage_api.get("bucketId")
            else:
                allowed = data.get("allowed", {})
                if allowed.get("bucketId") and (allowed.get("bucketName") == self.bucket_name or not allowed.get("bucketName")):
                    self.bucket_id = allowed.get("bucketId")
                else:
                    # Resolve bucketId via b2_list_buckets
                    account_id = data.get("accountId")
                    bucket_resp = await client.get(
                        f"{self.api_url}/b2api/v3/b2_list_buckets",
                        headers={"Authorization": self.authorization_token},
                        params={"accountId": account_id, "bucketName": self.bucket_name},
                    )
                    if bucket_resp.status_code == 200:
                        bucket_data = bucket_resp.json()
                        buckets = bucket_data.get("buckets", [])
                        if buckets:
                            self.bucket_id = buckets[0].get("bucketId")

            if not self.bucket_id:
                raise HTTPException(
                    status_code=500,
                    detail=f"B2 bucket '{self.bucket_name}' not found or access denied."
                )

    async def _get_upload_url(self) -> tuple[str, str]:
        """Obtain a single-use or reusable upload URL and auth token."""
        await self._authorize()
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self.api_url}/b2api/v3/b2_get_upload_url",
                headers={"Authorization": self.authorization_token},
                params={"bucketId": self.bucket_id},
            )
            if response.status_code == 401:
                # Token expired, refresh and retry once
                await self._authorize(force_refresh=True)
                response = await client.get(
                    f"{self.api_url}/b2api/v3/b2_get_upload_url",
                    headers={"Authorization": self.authorization_token},
                    params={"bucketId": self.bucket_id},
                )

            if response.status_code != 200:
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to acquire B2 upload URL (status {response.status_code})."
                )

            data = response.json()
            return data["uploadUrl"], data["authorizationToken"]

    async def upload(self, file: BinaryIO, storage_key: str, mime_type: str) -> None:
        """Upload a file stream to private B2 bucket with SHA1 verification."""
        clean_key = validate_storage_key(storage_key)
        
        file_data = file.read() if hasattr(file, "read") else bytes(file)
        sha1_hash = hashlib.sha1(file_data).hexdigest()
        
        # B2 expects percent-encoded file names in header
        encoded_key = urllib.parse.quote(clean_key, safe="/-_.")
        
        upload_url, upload_auth_token = await self._get_upload_url()
        headers = {
            "Authorization": upload_auth_token,
            "X-Bz-File-Name": encoded_key,
            "Content-Type": mime_type or "b2/x-auto",
            "X-Bz-Content-Sha1": sha1_hash,
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(upload_url, headers=headers, content=file_data)
            if resp.status_code == 401:
                # Refresh upload URL and retry once
                upload_url, upload_auth_token = await self._get_upload_url()
                headers["Authorization"] = upload_auth_token
                resp = await client.post(upload_url, headers=headers, content=file_data)

            if resp.status_code != 200:
                raise HTTPException(
                    status_code=500,
                    detail=f"B2 file upload failed with status {resp.status_code}."
                )

    async def delete(self, storage_key: str) -> None:
        """Delete file from B2 by locating file ID and removing file version."""
        clean_key = validate_storage_key(storage_key)
        await self._authorize()

        async with httpx.AsyncClient(timeout=30.0) as client:
            list_resp = await client.get(
                f"{self.api_url}/b2api/v3/b2_list_file_names",
                headers={"Authorization": self.authorization_token},
                params={"bucketId": self.bucket_id, "startFileName": clean_key, "maxFileCount": 1},
            )
            if list_resp.status_code == 401:
                await self._authorize(force_refresh=True)
                list_resp = await client.get(
                    f"{self.api_url}/b2api/v3/b2_list_file_names",
                    headers={"Authorization": self.authorization_token},
                    params={"bucketId": self.bucket_id, "startFileName": clean_key, "maxFileCount": 1},
                )

            if list_resp.status_code != 200:
                return  # Safe fallback if listing fails

            list_data = list_resp.json()
            files = list_data.get("files", [])
            if not files or files[0].get("fileName") != clean_key:
                return  # File not found or already deleted

            file_id = files[0].get("fileId")
            await client.post(
                f"{self.api_url}/b2api/v3/b2_delete_file_version",
                headers={"Authorization": self.authorization_token},
                json={"fileName": clean_key, "fileId": file_id},
            )

    async def download(self, storage_key: str) -> bytes:
        """Download file bytes from private B2 bucket using authorized request."""
        clean_key = validate_storage_key(storage_key)
        await self._authorize()

        encoded_key = urllib.parse.quote(clean_key, safe="/-_.")
        url = f"{self.download_url}/file/{self.bucket_name}/{encoded_key}"
        headers = {"Authorization": self.authorization_token}

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 401:
                await self._authorize(force_refresh=True)
                headers["Authorization"] = self.authorization_token
                resp = await client.get(url, headers=headers)

            if resp.status_code == 404:
                raise HTTPException(status_code=404, detail=f"File not found in B2 storage: {storage_key}")
            elif resp.status_code != 200:
                raise HTTPException(
                    status_code=500,
                    detail=f"B2 file download failed with status {resp.status_code}."
                )

            return resp.content

    async def exists(self, storage_key: str) -> bool:
        """Check if file exists in B2 bucket."""
        try:
            clean_key = validate_storage_key(storage_key)
            await self._authorize()
        except Exception:
            return False

        async with httpx.AsyncClient(timeout=30.0) as client:
            list_resp = await client.get(
                f"{self.api_url}/b2api/v3/b2_list_file_names",
                headers={"Authorization": self.authorization_token},
                params={"bucketId": self.bucket_id, "startFileName": clean_key, "maxFileCount": 1},
            )
            if list_resp.status_code == 401:
                await self._authorize(force_refresh=True)
                list_resp = await client.get(
                    f"{self.api_url}/b2api/v3/b2_list_file_names",
                    headers={"Authorization": self.authorization_token},
                    params={"bucketId": self.bucket_id, "startFileName": clean_key, "maxFileCount": 1},
                )

            if list_resp.status_code != 200:
                return False

            files = list_resp.json().get("files", [])
            return len(files) > 0 and files[0].get("fileName") == clean_key
