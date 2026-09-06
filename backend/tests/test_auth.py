import pytest
from fastapi.testclient import TestClient

from app.core.security import verify_password, hash_password, create_access_token, decode_token


def test_password_hashing():
    pwd = "superSecretPassword123"
    hashed = hash_password(pwd)
    assert hashed != pwd
    assert verify_password(pwd, hashed) is True
    assert verify_password("wrongPassword", hashed) is False


def test_signup_and_login_flow(client: TestClient):
    signup_data = {
        "email": "testuser@tarkai.com",
        "password": "strongPassword!456",
        "name": "Alex Mercer",
    }
    # 1. Signup
    res = client.post("/api/v1/auth/signup", json=signup_data)
    assert res.status_code == 201
    signup_json = res.json()
    assert "access_token" in signup_json
    assert "refresh_token" in signup_json
    assert signup_json["token_type"] == "bearer"
    assert signup_json["user"]["email"] == "testuser@tarkai.com"
    assert signup_json["user"]["name"] == "Alex Mercer"

    # 2. Duplicate signup should fail with 409
    dup_res = client.post("/api/v1/auth/signup", json=signup_data)
    assert dup_res.status_code == 409
    assert "already exists" in dup_res.json()["detail"]

    # 3. Login with correct credentials
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": "testuser@tarkai.com", "password": "strongPassword!456"},
    )
    assert login_res.status_code == 200
    login_json = login_res.json()
    assert "access_token" in login_json
    access_token = login_json["access_token"]
    refresh_token = login_json["refresh_token"]

    # 4. Access /me with valid Bearer token
    me_res = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert me_res.status_code == 200
    me_json = me_res.json()
    assert me_json["email"] == "testuser@tarkai.com"
    assert me_json["name"] == "Alex Mercer"

    # 5. Access /me without token should return 401
    unauth_res = client.get("/api/v1/auth/me")
    assert unauth_res.status_code == 401

    # 6. Refresh token
    refresh_res = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert refresh_res.status_code == 200
    new_token_json = refresh_res.json()
    assert "access_token" in new_token_json

    # 7. Logout
    logout_res = client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert logout_res.status_code == 200
    assert logout_res.json()["message"] == "Successfully logged out."


def test_login_invalid_credentials(client: TestClient):
    # Nonexistent user
    res = client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@tarkai.com", "password": "somePassword123"},
    )
    assert res.status_code == 401
    assert "Incorrect email or password" in res.json()["detail"]

    # Existing user with wrong password
    client.post(
        "/api/v1/auth/signup",
        json={"email": "alice@tarkai.com", "password": "correctPassword1"},
    )
    wrong_pwd_res = client.post(
        "/api/v1/auth/login",
        json={"email": "alice@tarkai.com", "password": "wrongPassword2"},
    )
    assert wrong_pwd_res.status_code == 401


def test_invalid_tokens(client: TestClient):
    # Bad access token
    res = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer invalid.jwt.token"},
    )
    assert res.status_code == 401

    # Bad refresh token
    refresh_res = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": "not-a-real-token"},
    )
    assert refresh_res.status_code == 401
