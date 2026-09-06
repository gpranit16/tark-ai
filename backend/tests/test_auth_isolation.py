import pytest
from fastapi.testclient import TestClient


def test_multi_user_data_isolation(client: TestClient):
    # 1. Sign up User A
    user_a_res = client.post(
        "/api/v1/auth/signup",
        json={"email": "usera@tarkai.com", "password": "PasswordA!123", "name": "User Alpha"},
    )
    assert user_a_res.status_code == 201
    user_a_token = user_a_res.json()["access_token"]
    user_a_id = user_a_res.json()["user"]["id"]
    headers_a = {"Authorization": f"Bearer {user_a_token}"}

    # 2. Sign up User B
    user_b_res = client.post(
        "/api/v1/auth/signup",
        json={"email": "userb@tarkai.com", "password": "PasswordB!456", "name": "User Beta"},
    )
    assert user_b_res.status_code == 201
    user_b_token = user_b_res.json()["access_token"]
    user_b_id = user_b_res.json()["user"]["id"]
    headers_b = {"Authorization": f"Bearer {user_b_token}"}

    # 3. User A creates a Project
    proj_a = client.post(
        "/api/v1/projects",
        json={"name": "Alpha Secret Project", "description": "Top secret alpha"},
        headers=headers_a,
    )
    assert proj_a.status_code == 201
    proj_a_id = proj_a.json()["id"]

    # 4. User A creates a Thread
    thread_a = client.post(
        "/api/v1/threads",
        json={"title": "Alpha Confidential Chat", "project_id": proj_a_id},
        headers=headers_a,
    )
    assert thread_a.status_code == 201
    thread_a_id = thread_a.json()["id"]

    # 5. User A creates a Memory
    mem_a = client.post(
        "/api/v1/memory",
        json={"key": "favorite_food", "value": "Alpha Pizza", "category": "preference"},
        headers=headers_a,
    )
    assert mem_a.status_code == 201

    # ── ISOLATION CHECKS FOR USER B ──────────────────────────────────────────

    # Check 1: User B lists threads -> should be empty
    threads_b = client.get("/api/v1/threads", headers=headers_b)
    assert threads_b.status_code == 200
    assert len(threads_b.json()) == 0

    # Check 2: User B tries to fetch User A's thread -> should be 403 Forbidden
    thread_get_b = client.get(f"/api/v1/threads/{thread_a_id}", headers=headers_b)
    assert thread_get_b.status_code in [403, 404]

    # Check 3: User B tries to update User A's thread -> should be 403 Forbidden
    thread_patch_b = client.patch(
        f"/api/v1/threads/{thread_a_id}",
        json={"title": "Hacked Title"},
        headers=headers_b,
    )
    assert thread_patch_b.status_code in [403, 404]

    # Check 4: User B lists projects -> should not see User A's project
    projs_b = client.get("/api/v1/projects", headers=headers_b)
    assert projs_b.status_code == 200
    assert len(projs_b.json()) == 0

    # Check 5: User B tries to access User A's project -> should fail with 403 or 404
    proj_get_b = client.get(f"/api/v1/projects/{proj_a_id}", headers=headers_b)
    assert proj_get_b.status_code in [403, 404]

    # Check 6: User B lists memories -> should not see User A's memory
    mem_b = client.get("/api/v1/memory", headers=headers_b)
    assert mem_b.status_code == 200
    assert len(mem_b.json()["items"]) == 0

    # Check 7: Settings isolation
    client.patch(
        "/api/v1/settings",
        json={"theme": "light"},
        headers=headers_a,
    )
    settings_b = client.get("/api/v1/settings", headers=headers_b)
    assert settings_b.status_code == 200
    # User B should still have default dark theme
    assert settings_b.json()["settings"]["theme"] == "dark"
