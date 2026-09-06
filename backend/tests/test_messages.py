from uuid import uuid4

from fastapi.testclient import TestClient

from app.models.conversation import User


def _create_thread(client: TestClient, user: User) -> dict:
    response = client.post("/api/v1/threads", json={"user_id": str(user.id), "title": "Chat"})
    assert response.status_code == 201
    return response.json()


def test_create_message(client: TestClient, user: User) -> None:
    thread = _create_thread(client, user)

    response = client.post(
        f"/api/v1/threads/{thread['id']}/messages",
        json={"role": "user", "content": "Hello"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["thread_id"] == thread["id"]
    assert body["role"] == "user"
    assert body["content"] == "Hello"


def test_list_messages(client: TestClient, user: User) -> None:
    thread = _create_thread(client, user)
    client.post(f"/api/v1/threads/{thread['id']}/messages", json={"role": "user", "content": "Hello"})
    client.post(f"/api/v1/threads/{thread['id']}/messages", json={"role": "assistant", "content": "Hi"})

    response = client.get(f"/api/v1/threads/{thread['id']}/messages")

    assert response.status_code == 200
    body = response.json()
    assert [message["content"] for message in body] == ["Hello", "Hi"]


def test_invalid_parent_message_id(client: TestClient, user: User) -> None:
    first_thread = _create_thread(client, user)
    second_thread = client.post("/api/v1/threads", json={"user_id": str(user.id), "title": "Other"}).json()
    parent = client.post(
        f"/api/v1/threads/{first_thread['id']}/messages",
        json={"role": "user", "content": "Parent"},
    ).json()

    response = client.post(
        f"/api/v1/threads/{second_thread['id']}/messages",
        json={"role": "assistant", "content": "Child", "parent_message_id": parent["id"]},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Parent message must belong to the same thread"


def test_missing_parent_message_id(client: TestClient, user: User) -> None:
    thread = _create_thread(client, user)

    response = client.post(
        f"/api/v1/threads/{thread['id']}/messages",
        json={"role": "assistant", "content": "Child", "parent_message_id": str(uuid4())},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Message not found"
