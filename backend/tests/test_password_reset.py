from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_token
from app.models.conversation import AuthToken, User


def test_password_reset_end_to_end(client: TestClient):
    # 1. Signup user
    signup_res = client.post(
        "/api/v1/auth/signup",
        json={"email": "resetuser@tarkai.com", "password": "InitialPassword123", "name": "Reset Tester"},
    )
    assert signup_res.status_code == 201

    captured_reset_url = []

    async def mock_send_reset(to_email, reset_url, user_name=None):
        captured_reset_url.append(reset_url)
        return {"id": "email_mock_reset"}

    # 2. Request forgot password with mocked email service
    with patch("app.api.v1.auth.email_service.send_password_reset_email", side_effect=mock_send_reset):
        forgot_res = client.post(
            "/api/v1/auth/forgot-password",
            json={"email": "resetuser@tarkai.com"},
        )
        assert forgot_res.status_code == 200
        assert "recovery instructions have been sent" in forgot_res.json()["message"]

    assert len(captured_reset_url) == 1
    raw_url = captured_reset_url[0]
    token = raw_url.split("token=")[-1]
    assert len(token) > 20

    # 3. Request forgot password for nonexistent user (should safely return 200 generic message without error)
    forgot_nonexistent = client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "nonexistent@tarkai.com"},
    )
    assert forgot_nonexistent.status_code == 200
    assert "recovery instructions have been sent" in forgot_nonexistent.json()["message"]

    # 4. Attempt reset with invalid token
    bad_reset = client.post(
        "/api/v1/auth/reset-password",
        json={"token": "invalid-random-token", "new_password": "NewSecretPassword456"},
    )
    assert bad_reset.status_code == 400
    assert "Invalid or expired" in bad_reset.json()["detail"]

    # 5. Successfully reset password with valid token
    good_reset = client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "new_password": "NewSecretPassword456"},
    )
    assert good_reset.status_code == 200
    assert "successfully reset" in good_reset.json()["message"]

    # 6. Attempt token reuse (should fail)
    reuse_reset = client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "new_password": "AnotherPassword789"},
    )
    assert reuse_reset.status_code == 400
    assert "Invalid or expired" in reuse_reset.json()["detail"]

    # 7. Verify old password fails
    old_login = client.post(
        "/api/v1/auth/login",
        json={"email": "resetuser@tarkai.com", "password": "InitialPassword123"},
    )
    assert old_login.status_code == 401

    # 8. Verify new password succeeds
    new_login = client.post(
        "/api/v1/auth/login",
        json={"email": "resetuser@tarkai.com", "password": "NewSecretPassword456"},
    )
    assert new_login.status_code == 200
    assert "access_token" in new_login.json()
