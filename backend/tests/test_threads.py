from uuid import uuid4

from fastapi.testclient import TestClient

from app.models.conversation import Project, User


def test_create_thread(client: TestClient, user: User) -> None:
    response = client.post("/api/v1/threads", json={"user_id": str(user.id), "title": "First thread"})

    assert response.status_code == 201
    body = response.json()
    assert body["user_id"] == str(user.id)
    assert body["title"] == "First thread"
    assert body["default_mode"] == "normal"


def test_list_threads(client: TestClient, user: User) -> None:
    client.post("/api/v1/threads", json={"user_id": str(user.id), "title": "Older"})
    client.post("/api/v1/threads", json={"user_id": str(user.id), "title": "Newer"})

    response = client.get(f"/api/v1/threads?user_id={user.id}&limit=10&offset=0")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert {item["title"] for item in body} == {"Older", "Newer"}


def test_get_thread(client: TestClient, user: User) -> None:
    created = client.post("/api/v1/threads", json={"user_id": str(user.id), "title": "Open me"}).json()

    response = client.get(f"/api/v1/threads/{created['id']}")

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_update_thread(client: TestClient, user: User) -> None:
    created = client.post("/api/v1/threads", json={"user_id": str(user.id), "title": "Draft"}).json()

    response = client.patch(
        f"/api/v1/threads/{created['id']}",
        json={"title": "Renamed", "default_mode": "reasoning"},
    )

    assert response.status_code == 200
    assert response.json()["title"] == "Renamed"
    assert response.json()["default_mode"] == "reasoning"


def test_invalid_thread(client: TestClient) -> None:
    response = client.get(f"/api/v1/threads/{uuid4()}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Thread not found"


def test_project_thread_relationship(client: TestClient, user: User, project: Project) -> None:
    response = client.post(
        "/api/v1/threads",
        json={"user_id": str(user.id), "project_id": str(project.id), "title": "Project thread"},
    )

    assert response.status_code == 201
    assert response.json()["project_id"] == str(project.id)

    listed = client.get(f"/api/v1/threads?project_id={project.id}")
    assert listed.status_code == 200
    assert len(listed.json()) == 1


def test_thread_create_rejects_missing_project(client: TestClient, user: User) -> None:
    response = client.post(
        "/api/v1/threads",
        json={"user_id": str(user.id), "project_id": str(uuid4()), "title": "No project"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Project not found"
