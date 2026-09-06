import io
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import httpx
from fastapi import HTTPException

from app.storage.b2 import B2StorageProvider, validate_storage_key
from app.storage.factory import get_storage_provider
from app.storage.local import LocalStorageProvider
from scripts.migrate_local_files_to_b2 import run_migration


def test_validate_storage_key_valid():
    assert validate_storage_key("users/123/projects/default/abc_file.txt") == "users/123/projects/default/abc_file.txt"
    assert validate_storage_key("users\\123\\projects\\default\\abc_file.txt") == "users/123/projects/default/abc_file.txt"
    assert validate_storage_key("global/shared_doc.pdf") == "global/shared_doc.pdf"


def test_validate_storage_key_traversal():
    with pytest.raises(HTTPException) as exc_info:
        validate_storage_key("../../etc/passwd")
    assert exc_info.value.status_code == 400
    assert "traversal" in exc_info.value.detail.lower()

    with pytest.raises(HTTPException) as exc_info:
        validate_storage_key("/root/secret.txt")
    assert exc_info.value.status_code == 400

    with pytest.raises(HTTPException) as exc_info:
        validate_storage_key("users/123/../../../secret.txt")
    assert exc_info.value.status_code == 400

    with pytest.raises(HTTPException) as exc_info:
        validate_storage_key("users/123/\0malicious.txt")
    assert exc_info.value.status_code == 400


def test_storage_factory_resolution(monkeypatch):
    from app.core.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "b2_key_id", "dummy_key")
    monkeypatch.setattr(settings, "b2_application_key", "dummy_app_key")
    monkeypatch.setattr(settings, "b2_bucket_name", "dummy_bucket")

    # Local provider resolution
    local_p = get_storage_provider("local")
    assert isinstance(local_p, LocalStorageProvider)
    assert local_p.provider_name == "local"

    # B2 provider resolution
    b2_p = get_storage_provider("b2")
    assert isinstance(b2_p, B2StorageProvider)
    assert b2_p.provider_name == "b2"


@pytest.mark.asyncio
async def test_b2_authorization_flow():
    provider = B2StorageProvider(
        key_id="test_key_id",
        application_key="test_app_key",
        bucket_name="test-bucket",
    )

    auth_response_data = {
        "apiUrl": "https://api001.backblazeb2.com",
        "authorizationToken": "auth_token_123",
        "downloadUrl": "https://f001.backblazeb2.com",
        "accountId": "acc_123",
        "allowed": {
            "bucketId": "bucket_id_456",
            "bucketName": "test-bucket"
        }
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = auth_response_data

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        await provider._authorize()

        assert provider.api_url == "https://api001.backblazeb2.com"
        assert provider.authorization_token == "auth_token_123"
        assert provider.download_url == "https://f001.backblazeb2.com"
        assert provider.bucket_id == "bucket_id_456"


@pytest.mark.asyncio
async def test_b2_upload_flow():
    provider = B2StorageProvider(
        key_id="test_key_id",
        application_key="test_app_key",
        bucket_name="test-bucket",
    )
    provider.api_url = "https://api001.backblazeb2.com"
    provider.authorization_token = "auth_token_123"
    provider.download_url = "https://f001.backblazeb2.com"
    provider.bucket_id = "bucket_id_456"

    upload_url_resp = MagicMock()
    upload_url_resp.status_code = 200
    upload_url_resp.json.return_value = {
        "uploadUrl": "https://upload.backblazeb2.com/upload",
        "authorizationToken": "upload_token_789"
    }

    upload_post_resp = MagicMock()
    upload_post_resp.status_code = 200
    upload_post_resp.json.return_value = {"fileId": "file_id_999", "fileName": "test/doc.txt"}

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get, \
         patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_get.return_value = upload_url_resp
        mock_post.return_value = upload_post_resp

        file_stream = io.BytesIO(b"Hello Tark AI B2 Storage!")
        await provider.upload(file_stream, "users/u1/projects/p1/doc.txt", "text/plain")

        # Verify POST payload and headers
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args[1]
        headers = call_kwargs["headers"]
        assert headers["Authorization"] == "upload_token_789"
        assert headers["Content-Type"] == "text/plain"
        assert headers["X-Bz-File-Name"] == "users/u1/projects/p1/doc.txt"
        assert len(headers["X-Bz-Content-Sha1"]) == 40  # SHA1 hex length


@pytest.mark.asyncio
async def test_b2_download_flow():
    provider = B2StorageProvider(
        key_id="test_key_id",
        application_key="test_app_key",
        bucket_name="test-bucket",
    )
    provider.api_url = "https://api001.backblazeb2.com"
    provider.authorization_token = "auth_token_123"
    provider.download_url = "https://f001.backblazeb2.com"
    provider.bucket_id = "bucket_id_456"

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = b"Downloaded content from private B2"

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp

        content = await provider.download("users/u1/projects/p1/doc.txt")
        assert content == b"Downloaded content from private B2"

        # Verify authorization header is included (private bucket)
        mock_get.assert_called_once()
        headers = mock_get.call_args[1]["headers"]
        assert headers["Authorization"] == "auth_token_123"


@pytest.mark.asyncio
async def test_b2_exists_and_delete_flow():
    provider = B2StorageProvider(
        key_id="test_key_id",
        application_key="test_app_key",
        bucket_name="test-bucket",
    )
    provider.api_url = "https://api001.backblazeb2.com"
    provider.authorization_token = "auth_token_123"
    provider.download_url = "https://f001.backblazeb2.com"
    provider.bucket_id = "bucket_id_456"

    # Test exists = True
    list_resp_found = MagicMock()
    list_resp_found.status_code = 200
    list_resp_found.json.return_value = {
        "files": [{"fileId": "file_123", "fileName": "users/u1/doc.pdf"}]
    }

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = list_resp_found
        exists = await provider.exists("users/u1/doc.pdf")
        assert exists is True

    # Test exists = False
    list_resp_not_found = MagicMock()
    list_resp_not_found.status_code = 200
    list_resp_not_found.json.return_value = {"files": []}

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = list_resp_not_found
        exists = await provider.exists("users/u1/missing.pdf")
        assert exists is False

    # Test delete
    del_resp = MagicMock()
    del_resp.status_code = 200

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get, \
         patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_get.return_value = list_resp_found
        mock_post.return_value = del_resp

        await provider.delete("users/u1/doc.pdf")
        mock_post.assert_called_once()
        assert mock_post.call_args[1]["json"] == {
            "fileName": "users/u1/doc.pdf",
            "fileId": "file_123"
        }


@pytest.mark.asyncio
async def test_b2_token_refresh_on_401():
    provider = B2StorageProvider(
        key_id="test_key_id",
        application_key="test_app_key",
        bucket_name="test-bucket",
    )
    provider.api_url = "https://api001.backblazeb2.com"
    provider.authorization_token = "expired_token"
    provider.download_url = "https://f001.backblazeb2.com"
    provider.bucket_id = "bucket_id_456"

    # Mock 401 first, then authorization success, then 200 download
    auth_resp = MagicMock()
    auth_resp.status_code = 200
    auth_resp.json.return_value = {
        "apiUrl": "https://api001.backblazeb2.com",
        "authorizationToken": "fresh_token_456",
        "downloadUrl": "https://f001.backblazeb2.com",
        "allowed": {"bucketId": "bucket_id_456"}
    }

    resp_401 = MagicMock()
    resp_401.status_code = 401

    resp_200 = MagicMock()
    resp_200.status_code = 200
    resp_200.content = b"Refreshed content bytes"

    call_count = 0
    async def mock_get(url, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        if "b2_authorize_account" in str(url):
            return auth_resp
        if call_count == 1:
            return resp_401
        return resp_200

    with patch("httpx.AsyncClient.get", side_effect=mock_get):
        content = await provider.download("users/u1/doc.pdf")
        assert content == b"Refreshed content bytes"
        assert provider.authorization_token == "fresh_token_456"


@pytest.mark.asyncio
async def test_migration_script_dry_run(monkeypatch):
    from scripts.migrate_local_files_to_b2 import run_migration

    result = await run_migration(dry_run=True)
    assert result.total_discovered >= 0
    assert result.failed == 0

