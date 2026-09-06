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
        def provider_name(self):
            return "local"

        async def upload(self, file, key, mime):
            pass

        async def delete(self, key):
            pass

        async def exists(self, key):
            return True

        async def download(self, key):
            return b"Secure file payload content"

    monkeypatch.setattr("app.services.files.get_storage_provider", lambda provider_name=None: MockStorage())
    monkeypatch.setattr("app.api.v1.files.get_storage_provider", lambda provider_name=None: MockStorage())


@pytest.mark.asyncio
async def test_file_extension_whitelist_security(client: TestClient, user):
    """Ensure executable, script, and dangerous extensions are rejected."""
    dangerous_extensions = [
        ("malicious.exe", "application/x-msdownload"),
        ("exploit.bat", "application/x-bat"),
        ("payload.cmd", "application/cmd"),
        ("script.vbs", "text/vbs"),
        ("virus.dll", "application/x-msdownload"),
    ]

    for filename, mime in dangerous_extensions:
        files = {"file": (filename, io.BytesIO(b"malicious"), mime)}
        data = {"user_id": str(user.id)}
        response = client.post("/api/v1/files/upload", files=files, data=data)
        assert response.status_code == 415, f"Expected 415 for {filename}, got {response.status_code}"


@pytest.mark.asyncio
async def test_file_user_isolation_security(client: TestClient, user, mock_storage_provider):
    """Ensure User A cannot view, preview, or delete User B's files."""
    user_a_file = {"file": ("secret_report.pdf", io.BytesIO(b"Classified"), "application/pdf")}
    data = {"user_id": str(user.id)}
    
    upload_resp = client.post("/api/v1/files/upload", files=user_a_file, data=data)
    assert upload_resp.status_code == 201
    file_id = upload_resp.json()["id"]

    # Attacker / other user
    attacker_id = str(uuid4())

    # 1. Attacker tries to get metadata
    meta_resp = client.get(f"/api/v1/files/{file_id}?user_id={attacker_id}")
    assert meta_resp.status_code == 404

    # 2. Attacker tries to download/preview content
    content_resp = client.get(f"/api/v1/files/{file_id}/content?user_id={attacker_id}")
    assert content_resp.status_code == 404

    # 3. Attacker tries to delete file
    del_resp = client.delete(f"/api/v1/files/{file_id}?user_id={attacker_id}")
    assert del_resp.status_code == 404

    # Owner can still access file
    owner_resp = client.get(f"/api/v1/files/{file_id}?user_id={user.id}")
    assert owner_resp.status_code == 200


@pytest.mark.asyncio
async def test_file_content_disposition_security(client: TestClient, user, mock_storage_provider):
    """Ensure file download endpoint returns safe headers and correct media type."""
    files = {"file": ("report.pdf", io.BytesIO(b"%PDF-1.4 test"), "application/pdf")}
    data = {"user_id": str(user.id)}
    
    upload_resp = client.post("/api/v1/files/upload", files=files, data=data)
    assert upload_resp.status_code == 201
    file_id = upload_resp.json()["id"]

    resp = client.get(f"/api/v1/files/{file_id}/content?user_id={user.id}")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert 'inline; filename="report.pdf"' in resp.headers.get("content-disposition", "")
