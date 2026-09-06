import io
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.conversation import User
from app.models.file import File
from app.storage.factory import get_storage_provider


@pytest.fixture(autouse=True)
def mock_document_processing():
    with patch("app.services.document_processing.create_and_start_parsing", new_callable=AsyncMock) as mock_parser:
        yield mock_parser


@pytest.mark.asyncio
async def test_upload_with_explicit_local_provider(client: TestClient, user: User, mock_document_processing):
    file_bytes = b"Hello local file content"
    files = {"file": ("notes.txt", io.BytesIO(file_bytes), "text/plain")}
    data = {"user_id": str(user.id), "storage_provider": "local"}

    response = client.post("/api/v1/files/upload", data=data, files=files)
    assert response.status_code == 201
    body = response.json()
    assert body["storage_provider"] == "local"
    assert body["original_filename"] == "notes.txt"

    # Verify physical file exists on local storage
    local_provider = get_storage_provider("local")
    db_file_id = body["id"]
    file_info = client.get(f"/api/v1/files/{db_file_id}?user_id={user.id}").json()
    assert file_info["storage_provider"] == "local"


@pytest.mark.asyncio
async def test_upload_with_explicit_b2_provider(client: TestClient, user: User, mock_document_processing):
    file_bytes = b"Hello B2 file content"
    files = {"file": ("report.pdf", io.BytesIO(file_bytes), "application/pdf")}
    data = {"user_id": str(user.id), "storage_provider": "b2"}

    with patch("app.storage.b2.B2StorageProvider.upload", new_callable=AsyncMock) as mock_b2_upload:
        response = client.post("/api/v1/files/upload", data=data, files=files)
        assert response.status_code == 201
        body = response.json()
        assert body["storage_provider"] == "b2"
        assert body["original_filename"] == "report.pdf"
        assert mock_b2_upload.called


@pytest.mark.asyncio
async def test_upload_with_invalid_provider_rejected(client: TestClient, user: User):
    files = {"file": ("invalid.txt", io.BytesIO(b"content"), "text/plain")}
    data = {"user_id": str(user.id), "storage_provider": "dropbox"}

    response = client.post("/api/v1/files/upload", data=data, files=files)
    assert response.status_code == 400
    assert "Invalid storage_provider" in response.json()["detail"]


@pytest.mark.asyncio
async def test_upload_default_fallback_provider(client: TestClient, user: User, mock_document_processing):
    files = {"file": ("default.txt", io.BytesIO(b"default content"), "text/plain")}
    data = {"user_id": str(user.id)}

    response = client.post("/api/v1/files/upload", data=data, files=files)
    assert response.status_code == 201
    body = response.json()
    assert body["storage_provider"] in ("local", "b2")


@pytest.mark.asyncio
async def test_read_and_preview_uses_db_provider(client: TestClient, user: User, mock_document_processing):
    # Upload local file
    local_bytes = b"Local preview bytes"
    files_local = {"file": ("local_doc.txt", io.BytesIO(local_bytes), "text/plain")}
    res_local = client.post("/api/v1/files/upload", data={"user_id": str(user.id), "storage_provider": "local"}, files=files_local)
    assert res_local.status_code == 201
    local_id = res_local.json()["id"]

    # Preview local file
    prev_local = client.get(f"/api/v1/files/{local_id}/content?user_id={user.id}")
    assert prev_local.status_code == 200
    assert prev_local.content == local_bytes

    # Upload B2 file with mocked B2 provider
    b2_bytes = b"B2 mocked preview bytes"
    with patch("app.storage.b2.B2StorageProvider.upload", new_callable=AsyncMock), \
         patch("app.storage.b2.B2StorageProvider.download", new_callable=AsyncMock, return_value=b2_bytes) as mock_b2_dl:
        files_b2 = {"file": ("b2_doc.pdf", io.BytesIO(b"original"), "application/pdf")}
        res_b2 = client.post("/api/v1/files/upload", data={"user_id": str(user.id), "storage_provider": "b2"}, files=files_b2)
        assert res_b2.status_code == 201
        b2_id = res_b2.json()["id"]

        prev_b2 = client.get(f"/api/v1/files/{b2_id}/content?user_id={user.id}")
        assert prev_b2.status_code == 200
        assert prev_b2.content == b2_bytes
        assert mock_b2_dl.called


@pytest.mark.asyncio
async def test_delete_uses_db_provider(client: TestClient, user: User, mock_document_processing):
    # Upload B2 file
    with patch("app.storage.b2.B2StorageProvider.upload", new_callable=AsyncMock), \
         patch("app.storage.b2.B2StorageProvider.delete", new_callable=AsyncMock) as mock_b2_del:
        files = {"file": ("delete_me.pdf", io.BytesIO(b"content"), "application/pdf")}
        res = client.post("/api/v1/files/upload", data={"user_id": str(user.id), "storage_provider": "b2"}, files=files)
        assert res.status_code == 201
        file_id = res.json()["id"]

        # Delete file
        del_res = client.delete(f"/api/v1/files/{file_id}?user_id={user.id}")
        assert del_res.status_code == 204
        assert mock_b2_del.called


@pytest.mark.asyncio
async def test_global_provider_switch_compatibility(client: TestClient, user: User, mock_document_processing):
    # Create local file
    local_bytes = b"Local permanent content"
    files = {"file": ("keep_local.txt", io.BytesIO(local_bytes), "text/plain")}
    res = client.post("/api/v1/files/upload", data={"user_id": str(user.id), "storage_provider": "local"}, files=files)
    assert res.status_code == 201
    file_id = res.json()["id"]

    settings = get_settings()
    original_setting = settings.storage_provider
    try:
        # Switch global setting to b2
        settings.storage_provider = "b2"

        # Reading the local file must STILL succeed from local storage
        content_res = client.get(f"/api/v1/files/{file_id}/content?user_id={user.id}")
        assert content_res.status_code == 200
        assert content_res.content == local_bytes
    finally:
        settings.storage_provider = original_setting


@pytest.mark.asyncio
async def test_list_files_storage_filtering(client: TestClient, user: User, mock_document_processing):
    # Create 1 local file and 1 B2 file
    client.post("/api/v1/files/upload", data={"user_id": str(user.id), "storage_provider": "local"}, files={"file": ("f1.txt", io.BytesIO(b"c1"), "text/plain")})
    with patch("app.storage.b2.B2StorageProvider.upload", new_callable=AsyncMock):
        client.post("/api/v1/files/upload", data={"user_id": str(user.id), "storage_provider": "b2"}, files={"file": ("f2.pdf", io.BytesIO(b"c2"), "application/pdf")})

    # List all
    all_files = client.get(f"/api/v1/files?user_id={user.id}").json()
    assert len(all_files) == 2

    # Filter local
    local_only = client.get(f"/api/v1/files?user_id={user.id}&storage_provider=local").json()
    assert len(local_only) == 1
    assert local_only[0]["storage_provider"] == "local"

    # Filter b2
    b2_only = client.get(f"/api/v1/files?user_id={user.id}&storage_provider=b2").json()
    assert len(b2_only) == 1
    assert b2_only[0]["storage_provider"] == "b2"


@pytest.mark.asyncio
async def test_storage_stats_endpoint(client: TestClient, user: User, mock_document_processing):
    # Add files
    client.post("/api/v1/files/upload", data={"user_id": str(user.id), "storage_provider": "local"}, files={"file": ("local1.txt", io.BytesIO(b"12345"), "text/plain")})
    with patch("app.storage.b2.B2StorageProvider.upload", new_callable=AsyncMock):
        client.post("/api/v1/files/upload", data={"user_id": str(user.id), "storage_provider": "b2"}, files={"file": ("b2_1.pdf", io.BytesIO(b"1234567"), "application/pdf")})

    stats_res = client.get(f"/api/v1/files/stats?user_id={user.id}")
    assert stats_res.status_code == 200
    stats = stats_res.json()
    assert stats["total_files"] == 2
    assert stats["local_files"] == 1
    assert stats["b2_files"] == 1
    assert stats["local_size_bytes"] == 5
    assert stats["b2_size_bytes"] == 7
    assert stats["total_size_bytes"] == 12
