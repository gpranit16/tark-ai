from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient


def test_email_verification_flow(client: TestClient):
    captured_verify_url = []

    async def mock_send_verification(to_email, verification_url, user_name=None):
        captured_verify_url.append(verification_url)
        return {"id": "email_mock_verify"}

    # 1. Signup user with mocked email dispatch
    with patch("app.api.v1.auth.email_service.send_verification_email", side_effect=mock_send_verification):
        signup_res = client.post(
            "/api/v1/auth/signup",
            json={"email": "verifyuser@tarkai.com", "password": "SecurePassword123!", "name": "Verify Tester"},
        )
        assert signup_res.status_code == 201
        assert signup_res.json()["user"]["is_verified"] is False

    assert len(captured_verify_url) == 1
    verify_url = captured_verify_url[0]
    token = verify_url.split("token=")[-1]
    assert len(token) > 20

    # 2. Verify with invalid token
    invalid_res = client.post(
        "/api/v1/auth/verify-email",
        json={"token": "bad-verification-token"},
    )
    assert invalid_res.status_code == 400
    assert "Invalid or expired" in invalid_res.json()["detail"]

    # 3. Verify with valid token
    valid_res = client.post(
        "/api/v1/auth/verify-email",
        json={"token": token},
    )
    assert valid_res.status_code == 200
    assert "successfully verified" in valid_res.json()["message"]

    # 4. Token reuse fails
    reuse_res = client.post(
        "/api/v1/auth/verify-email",
        json={"token": token},
    )
    assert reuse_res.status_code == 400
    assert "Invalid or expired" in reuse_res.json()["detail"]

    # 5. Check /me reflects is_verified = True
    token_auth = signup_res.json()["access_token"]
    me_res = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token_auth}"})
    assert me_res.status_code == 200
    assert me_res.json()["is_verified"] is True

    # 6. Test resend verification endpoint
    with patch("app.api.v1.auth.email_service.send_verification_email", side_effect=mock_send_verification):
        resend_res = client.post(
            "/api/v1/auth/resend-verification",
            json={"email": "verifyuser@tarkai.com"},
        )
        assert resend_res.status_code == 200
        assert "verification link has been sent" in resend_res.json()["message"]
