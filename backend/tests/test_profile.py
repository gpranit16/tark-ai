import io
import pytest
from httpx import ASGITransport, AsyncClient

from app.core.security import create_access_token, hash_password
from app.main import app
from app.models.conversation import User
from app.models.settings import UserSettings


@pytest.mark.asyncio
async def test_update_profile_name_and_avatar(db_session):
    # 1. Create test user
    user = User(
        email="profile_tester@example.com",
        password_hash=hash_password("OldPassword123!"),
        name="Initial Name",
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.flush()

    settings_obj = UserSettings(user_id=user.id, display_name="Initial Name")
    db_session.add(settings_obj)
    await db_session.commit()

    token = create_access_token(user.id)
    headers = {"Authorization": f"Bearer {token}"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Update name and avatar
        resp = await client.patch(
            "/api/v1/auth/profile",
            json={"name": "Pranit Kumar", "avatar_url": "https://example.com/avatar.png"},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Pranit Kumar"
        assert data["display_name"] == "Pranit Kumar"
        assert data["avatar_url"] == "https://example.com/avatar.png"

        # Verify /me endpoint returns updated profile
        me_resp = await client.get("/api/v1/auth/me", headers=headers)
        assert me_resp.status_code == 200
        me_data = me_resp.json()
        assert me_data["name"] == "Pranit Kumar"
        assert me_data["avatar_url"] == "https://example.com/avatar.png"


@pytest.mark.asyncio
async def test_change_password(db_session):
    user = User(
        email="pw_tester@example.com",
        password_hash=hash_password("CorrectOld123!"),
        name="Password Tester",
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.commit()

    token = create_access_token(user.id)
    headers = {"Authorization": f"Bearer {token}"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Test wrong old password
        wrong_resp = await client.post(
            "/api/v1/auth/change-password",
            json={"current_password": "WrongPassword123!", "new_password": "NewSecretPass456!"},
            headers=headers,
        )
        assert wrong_resp.status_code == 400
        assert "Current password is incorrect" in wrong_resp.json()["detail"]

        # Test valid password change
        success_resp = await client.post(
            "/api/v1/auth/change-password",
            json={"current_password": "CorrectOld123!", "new_password": "NewSecretPass456!"},
            headers=headers,
        )
        assert success_resp.status_code == 200

        # Verify can login with new password
        login_resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "pw_tester@example.com", "password": "NewSecretPass456!"},
        )
        assert login_resp.status_code == 200


@pytest.mark.asyncio
async def test_upload_avatar(db_session):
    user = User(
        email="avatar_tester@example.com",
        password_hash=hash_password("Password123!"),
        name="Avatar Tester",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()

    token = create_access_token(user.id)
    headers = {"Authorization": f"Bearer {token}"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Upload valid PNG
        png_content = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        files = {"file": ("avatar.png", io.BytesIO(png_content), "image/png")}
        resp = await client.post("/api/v1/auth/avatar", files=files, headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["avatar_url"].startswith("data:image/png;base64,")
