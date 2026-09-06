from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import User


def test_rename_thread(client: TestClient, user: User) -> None:
    created = client.post("/api/v1/threads", json={"user_id": str(user.id), "title": "Old Name"}).json()
    thread_id = created["id"]

    response = client.patch(f"/api/v1/threads/{thread_id}?user_id={user.id}", json={"title": "New Title"})
    assert response.status_code == 200
    assert response.json()["title"] == "New Title"

    # Verify via GET
    get_res = client.get(f"/api/v1/threads/{thread_id}?user_id={user.id}")
    assert get_res.status_code == 200
    assert get_res.json()["title"] == "New Title"


def test_pin_and_unpin_thread(client: TestClient, user: User) -> None:
    created = client.post("/api/v1/threads", json={"user_id": str(user.id), "title": "Pin Me"}).json()
    thread_id = created["id"]
    assert created["is_pinned"] is False

    # Pin
    pin_res = client.patch(f"/api/v1/threads/{thread_id}?user_id={user.id}", json={"is_pinned": True})
    assert pin_res.status_code == 200
    assert pin_res.json()["is_pinned"] is True

    # Unpin
    unpin_res = client.patch(f"/api/v1/threads/{thread_id}?user_id={user.id}", json={"is_pinned": False})
    assert unpin_res.status_code == 200
    assert unpin_res.json()["is_pinned"] is False


def test_archive_and_unarchive_thread(client: TestClient, user: User) -> None:
    created = client.post("/api/v1/threads", json={"user_id": str(user.id), "title": "Archive Me"}).json()
    thread_id = created["id"]
    assert created["is_archived"] is False

    # Archive
    arch_res = client.patch(f"/api/v1/threads/{thread_id}?user_id={user.id}", json={"is_archived": True})
    assert arch_res.status_code == 200
    assert arch_res.json()["is_archived"] is True
    assert arch_res.json()["archived_at"] is not None

    # Verify active list excludes archived thread
    active_list = client.get(f"/api/v1/threads?user_id={user.id}&is_archived=false").json()
    assert all(t["id"] != thread_id for t in active_list)

    # Verify archived list includes archived thread
    archived_list = client.get(f"/api/v1/threads?user_id={user.id}&is_archived=true").json()
    assert any(t["id"] == thread_id for t in archived_list)

    # Unarchive
    unarch_res = client.patch(f"/api/v1/threads/{thread_id}?user_id={user.id}", json={"is_archived": False})
    assert unarch_res.status_code == 200
    assert unarch_res.json()["is_archived"] is False
    assert unarch_res.json()["archived_at"] is None

    # Verify active list now includes thread again
    active_list_again = client.get(f"/api/v1/threads?user_id={user.id}&is_archived=false").json()
    assert any(t["id"] == thread_id for t in active_list_again)


def test_move_thread_up_and_down(client: TestClient, user: User) -> None:
    # Create 3 threads: A, B, C
    t_a = client.post("/api/v1/threads", json={"user_id": str(user.id), "title": "Thread A"}).json()
    t_b = client.post("/api/v1/threads", json={"user_id": str(user.id), "title": "Thread B"}).json()
    t_c = client.post("/api/v1/threads", json={"user_id": str(user.id), "title": "Thread C"}).json()

    # Move C up (so C comes before B)
    move_res = client.post(
        f"/api/v1/threads/{t_c['id']}/move?user_id={user.id}",
        json={"direction": "up"},
    )
    assert move_res.status_code == 200

    list_res = client.get(f"/api/v1/threads?user_id={user.id}&is_archived=false").json()
    titles = [t["title"] for t in list_res]
    assert titles.index("Thread C") < titles.index("Thread B")

    # Move C down (so C goes back after B)
    move_down_res = client.post(
        f"/api/v1/threads/{t_c['id']}/move?user_id={user.id}",
        json={"direction": "down"},
    )
    assert move_down_res.status_code == 200

    list_res_after = client.get(f"/api/v1/threads?user_id={user.id}&is_archived=false").json()
    titles_after = [t["title"] for t in list_res_after]
    assert titles_after.index("Thread C") > titles_after.index("Thread B")


def test_delete_thread(client: TestClient, user: User) -> None:
    created = client.post("/api/v1/threads", json={"user_id": str(user.id), "title": "Delete Me"}).json()
    thread_id = created["id"]

    # Add message
    msg = client.post(f"/api/v1/threads/{thread_id}/messages", json={"role": "user", "content": "Hello world"})
    assert msg.status_code == 201

    # Delete
    del_res = client.delete(f"/api/v1/threads/{thread_id}?user_id={user.id}")
    assert del_res.status_code == 204

    # Verify 404
    get_res = client.get(f"/api/v1/threads/{thread_id}")
    assert get_res.status_code == 404


async def test_ownership_protection(client: TestClient, user: User, db_session: AsyncSession) -> None:
    other_user = User(id=uuid4())
    db_session.add(other_user)
    await db_session.commit()

    # Create other user's thread
    other_thread = client.post("/api/v1/threads", json={"user_id": str(other_user.id), "title": "Other User Thread"}).json()
    other_id = other_thread["id"]

    # User A cannot rename User B's thread
    res_rename = client.patch(f"/api/v1/threads/{other_id}?user_id={user.id}", json={"title": "Hacked"})
    assert res_rename.status_code == 403

    # User A cannot move User B's thread
    res_move = client.post(f"/api/v1/threads/{other_id}/move?user_id={user.id}", json={"direction": "up"})
    assert res_move.status_code == 403

    # User A cannot delete User B's thread
    res_delete = client.delete(f"/api/v1/threads/{other_id}?user_id={user.id}")
    assert res_delete.status_code == 403

    # User A cannot get User B's thread when user_id is provided
    res_get = client.get(f"/api/v1/threads/{other_id}?user_id={user.id}")
    assert res_get.status_code == 403


def test_pinned_threads_ordering(client: TestClient, user: User) -> None:
    t1 = client.post("/api/v1/threads", json={"user_id": str(user.id), "title": "Thread 1"}).json()
    t2 = client.post("/api/v1/threads", json={"user_id": str(user.id), "title": "Thread 2"}).json()

    # Pin Thread 1
    client.patch(f"/api/v1/threads/{t1['id']}?user_id={user.id}", json={"is_pinned": True})

    # List threads
    listed = client.get(f"/api/v1/threads?user_id={user.id}&is_archived=false").json()
    assert len(listed) == 2
    # Pinned Thread 1 must come first even if Thread 2 was created more recently
    assert listed[0]["id"] == t1["id"]
    assert listed[0]["is_pinned"] is True
    assert listed[1]["id"] == t2["id"]
    assert listed[1]["is_pinned"] is False
