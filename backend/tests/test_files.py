import io
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.file import File


@pytest.fixture
def mock_storage_provider(monkeypatch):
    class MockStorage:
        @property
        def provider_name(self): return "local"
        
        async def upload(self, file, key, mime): pass
        async def delete(self, key): pass
        async def exists(self, key): return True
        async def download(self, key): return b"fake file content"

    monkeypatch.setattr("app.services.files.get_storage_provider", lambda *args, **kwargs: MockStorage())
    monkeypatch.setattr("app.api.v1.files.get_storage_provider", lambda *args, **kwargs: MockStorage())
    monkeypatch.setattr("app.services.document_processing.get_storage_provider", lambda *args, **kwargs: MockStorage())


@pytest.mark.asyncio
async def test_upload_valid_file(client: TestClient, user, mock_storage_provider, db_session: AsyncSession):
    file_content = b"fake file content"
    files = {"file": ("test.txt", io.BytesIO(file_content), "text/plain")}
    data = {"user_id": str(user.id)}
    
    response = client.post("/api/v1/files/upload", files=files, data=data)
    assert response.status_code == 201
    
    response_data = response.json()
    assert response_data["original_filename"] == "test.txt"
    assert response_data["extension"] == ".txt"
    assert response_data["status"] == "active"
    
    # check db
    db_file = await db_session.get(File, response_data["id"])
    assert db_file is not None


@pytest.mark.asyncio
async def test_upload_unsupported_extension(client: TestClient, user):
    file_content = b"fake file content"
    files = {"file": ("test.exe", io.BytesIO(file_content), "application/x-msdownload")}
    data = {"user_id": str(user.id)}
    
    response = client.post("/api/v1/files/upload", files=files, data=data)
    assert response.status_code == 415


@pytest.mark.asyncio
async def test_upload_invalid_mime(client: TestClient, user):
    file_content = b"fake file content"
    # Valid extension but invalid mime according to our rules
    files = {"file": ("test.txt", io.BytesIO(file_content), "audio/mpeg")}
    data = {"user_id": str(user.id)}
    
    response = client.post("/api/v1/files/upload", files=files, data=data)
    assert response.status_code == 415


@pytest.mark.asyncio
async def test_list_files(client: TestClient, user, mock_storage_provider):
    # Upload first
    file_content = b"fake file content"
    files = {"file": ("test1.txt", io.BytesIO(file_content), "text/plain")}
    data = {"user_id": str(user.id)}
    client.post("/api/v1/files/upload", files=files, data=data)
    
    # List
    response = client.get(f"/api/v1/files?user_id={user.id}")
    assert response.status_code == 200
    assert len(response.json()) >= 1


@pytest.mark.asyncio
async def test_get_file_and_isolation(client: TestClient, user, mock_storage_provider):
    file_content = b"fake file content"
    files = {"file": ("test_iso.txt", io.BytesIO(file_content), "text/plain")}
    data = {"user_id": str(user.id)}
    resp = client.post("/api/v1/files/upload", files=files, data=data)
    file_id = resp.json()["id"]
    
    # Get file with correct user
    response = client.get(f"/api/v1/files/{file_id}?user_id={user.id}")
    assert response.status_code == 200
    
    # Get file with WRONG user
    wrong_user = str(uuid4())
    response_wrong = client.get(f"/api/v1/files/{file_id}?user_id={wrong_user}")
    assert response_wrong.status_code == 404


@pytest.mark.asyncio
async def test_delete_file(client: TestClient, user, mock_storage_provider, db_session: AsyncSession):
    file_content = b"fake file content"
    files = {"file": ("test_del.txt", io.BytesIO(file_content), "text/plain")}
    data = {"user_id": str(user.id)}
    resp = client.post("/api/v1/files/upload", files=files, data=data)
    file_id = resp.json()["id"]
    
    # Delete file
    del_resp = client.delete(f"/api/v1/files/{file_id}?user_id={user.id}")
    assert del_resp.status_code == 204
    
    # Check it's gone
    get_resp = client.get(f"/api/v1/files/{file_id}?user_id={user.id}")
    assert get_resp.status_code == 404
    
    db_file = await db_session.get(File, file_id)
    assert db_file is None
