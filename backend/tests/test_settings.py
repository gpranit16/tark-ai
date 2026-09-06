"""Tests for Settings API, persistence, defaults, validation, reset, and safety."""
from __future__ import annotations

from uuid import UUID, uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ConversationMode, MemoryCategory
from app.models.conversation import Message, Project, Thread, User
from app.models.file import File
from app.models.memory import Memory
from app.models.settings import UserSettings
from app.services.settings import settings_service


@pytest.mark.asyncio
async def test_get_settings_default_initialization(client: TestClient, db_session: AsyncSession, user: User) -> None:
    """Test that querying settings creates default settings for a new user."""
    response = client.get(f"/api/v1/settings?user_id={user.id}")
    assert response.status_code == 200
    data = response.json()

    assert "settings" in data
    settings = data["settings"]
    assert settings["user_id"] == str(user.id)
    assert settings["display_name"] == "Developer"
    assert settings["theme"] == "dark"
    assert settings["default_mode"] == "normal"
    assert settings["smart_memory_enabled"] is True
    assert settings["streaming_enabled"] is True
    assert settings["enter_to_send"] is True
    assert settings["chat_density"] == "comfortable"
    assert settings["show_citations"] is True

    # Modes
    assert "modes" in data
    assert len(data["modes"]) >= 6
    modes_map = {m["mode"]: m for m in data["modes"]}
    assert "fast" in modes_map
    assert "normal" in modes_map
    assert "reasoning" in modes_map
    assert "coding" in modes_map
    assert "rag" in modes_map
    assert "deep_research" in modes_map
    assert modes_map["normal"]["is_default"] is True

    # Providers
    assert "providers" in data
    providers_map = {p["provider"]: p for p in data["providers"]}
    assert "groq" in providers_map
    assert "gemini" in providers_map
    assert "mistral" in providers_map

    # Storage
    assert "storage" in data
    assert data["storage"]["status"] == "Connected"
    assert "storage_used_formatted" in data["storage"]
    # Verify no secrets in storage
    assert "b2_application_key" not in str(data)
    assert "b2_key_id" not in str(data)

    # Tools
    assert "tools" in data
    assert len(data["tools"]) >= 11
    tool_names = [t["name"] for t in data["tools"]]
    assert "calculator" in tool_names
    assert "web_search" in tool_names
    assert "search_user_memory" in tool_names


@pytest.mark.asyncio
async def test_update_settings_and_persistence(client: TestClient, db_session: AsyncSession, user: User) -> None:
    """Test updating user settings and verifying persistence."""
    update_payload = {
        "display_name": "Antigravity Engineer",
        "theme": "light",
        "default_mode": "fast",
        "chat_density": "compact",
        "smart_memory_enabled": False,
        "streaming_enabled": False,
        "enter_to_send": False,
        "tool_preferences": {"calculator": True, "web_search": False},
    }

    patch_res = client.patch(f"/api/v1/settings?user_id={user.id}", json=update_payload)
    assert patch_res.status_code == 200
    data = patch_res.json()
    settings = data["settings"]

    assert settings["display_name"] == "Antigravity Engineer"
    assert settings["theme"] == "light"
    assert settings["default_mode"] == "fast"
    assert settings["chat_density"] == "compact"
    assert settings["smart_memory_enabled"] is False
    assert settings["streaming_enabled"] is False
    assert settings["enter_to_send"] is False
    assert settings["tool_preferences"]["web_search"] is False

    # Check that default mode updated in modes list
    modes_map = {m["mode"]: m for m in data["modes"]}
    assert modes_map["fast"]["is_default"] is True
    assert modes_map["normal"]["is_default"] is False

    # Second GET to verify persistence
    get_res = client.get(f"/api/v1/settings?user_id={user.id}")
    assert get_res.status_code == 200
    persisted = get_res.json()["settings"]
    assert persisted["display_name"] == "Antigravity Engineer"
    assert persisted["default_mode"] == "fast"
    assert persisted["smart_memory_enabled"] is False


@pytest.mark.asyncio
async def test_invalid_settings_validation(client: TestClient, user: User) -> None:
    """Test that invalid values for theme, density, or retrieval mode are rejected."""
    # Invalid theme
    res = client.patch(f"/api/v1/settings?user_id={user.id}", json={"theme": "invalid_theme"})
    assert res.status_code == 422

    # Invalid chat density
    res = client.patch(f"/api/v1/settings?user_id={user.id}", json={"chat_density": "ultra_wide"})
    assert res.status_code == 422

    # Invalid default retrieval mode
    res = client.patch(f"/api/v1/settings?user_id={user.id}", json={"default_retrieval_mode": "magic"})
    assert res.status_code == 422

    # Invalid default mode
    res = client.patch(f"/api/v1/settings?user_id={user.id}", json={"default_mode": "nonexistent_mode"})
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_reset_settings_preserves_user_data(client: TestClient, db_session: AsyncSession, user: User) -> None:
    """Test reset settings returns to default without deleting projects, threads, files, or memories."""
    # Create user data
    project = Project(user_id=user.id, name="Project Alpha")
    db_session.add(project)
    thread = Thread(user_id=user.id, title="Thread Alpha", default_mode=ConversationMode.NORMAL)
    db_session.add(thread)
    mem = Memory(
        user_id=user.id,
        category=MemoryCategory.FACT,
        key="role",
        value="Software Architect",
        confidence=1.0,
        importance=0.9,
    )
    db_session.add(mem)
    f = File(
        user_id=user.id,
        original_filename="doc.txt",
        extension=".txt",
        storage_provider="local",
        storage_key="test/doc.txt",
        mime_type="text/plain",
        size_bytes=1024,
    )
    db_session.add(f)
    await db_session.commit()

    # Modify settings first
    client.patch(
        f"/api/v1/settings?user_id={user.id}",
        json={"display_name": "Custom Name", "theme": "light", "default_mode": "reasoning"},
    )

    # Trigger reset
    reset_res = client.post(f"/api/v1/settings/reset?user_id={user.id}")
    assert reset_res.status_code == 200
    res_data = reset_res.json()
    settings = res_data["settings"]

    # Preferences should be factory defaults
    assert settings["display_name"] == "Developer"
    assert settings["theme"] == "dark"
    assert settings["default_mode"] == "normal"

    # User data must remain untouched
    account = res_data["account"]
    assert account["projects_count"] == 1
    assert account["threads_count"] == 1
    assert account["memories_count"] == 1
    assert account["files_count"] == 1


@pytest.mark.asyncio
async def test_user_settings_isolation(client: TestClient, db_session: AsyncSession) -> None:
    """Test that two separate users have completely isolated settings."""
    user1 = User(id=uuid4())
    user2 = User(id=uuid4())
    db_session.add_all([user1, user2])
    await db_session.commit()

    # Update User 1 settings
    client.patch(
        f"/api/v1/settings?user_id={user1.id}",
        json={"display_name": "User One", "default_mode": "reasoning", "theme": "light"},
    )

    # Update User 2 settings
    client.patch(
        f"/api/v1/settings?user_id={user2.id}",
        json={"display_name": "User Two", "default_mode": "fast", "theme": "dark"},
    )

    # Query User 1
    res1 = client.get(f"/api/v1/settings?user_id={user1.id}").json()["settings"]
    assert res1["display_name"] == "User One"
    assert res1["default_mode"] == "reasoning"
    assert res1["theme"] == "light"

    # Query User 2
    res2 = client.get(f"/api/v1/settings?user_id={user2.id}").json()["settings"]
    assert res2["display_name"] == "User Two"
    assert res2["default_mode"] == "fast"
    assert res2["theme"] == "dark"


@pytest.mark.asyncio
async def test_smart_memory_toggle_behavior(client: TestClient, db_session: AsyncSession, user: User) -> None:
    """Test that toggling smart memory off prevents auto-extraction in chat service."""
    from collections.abc import AsyncIterator
    from app.core.config import Settings
    from app.providers.base import AIProvider, NormalizedMessage, ProviderName, ProviderStreamEvent, UsageMetadata
    from app.schemas.chat import ChatRequest
    from app.services.chat.router import ModelRouter
    from app.services.chat.service import ChatService

    class MockChatProvider(AIProvider):
        def __init__(self, name: ProviderName, default_model: str) -> None:
            self.name = name
            self.default_model = default_model

        def supports_model(self, model: str) -> bool:
            return True

        async def stream(
            self, *, messages: list[NormalizedMessage], model: str, mode: ConversationMode, max_tokens: int | None = None
        ) -> AsyncIterator[ProviderStreamEvent]:
            yield ProviderStreamEvent(delta="Response acknowledged.", finish_reason="stop", usage=UsageMetadata(10, 20, 30))

    test_settings = Settings(
        DATABASE_URL="postgresql+asyncpg://tarkai:change-me@localhost:5433/tarkai_test",
        FAST_PROVIDER="groq",
        FAST_MODEL="qwen/qwen3.6-27b",
        NORMAL_PROVIDER="groq",
        NORMAL_MODEL="qwen/qwen3.8-27b",
        DEFAULT_PROVIDER="groq",
        AUTO_FALLBACK=True,
    )

    # 1. Turn Smart Memory OFF
    client.patch(f"/api/v1/settings?user_id={user.id}", json={"smart_memory_enabled": False})

    user_db = await db_session.merge(user)
    thread = Thread(user_id=user_db.id, title="Memory Toggle Test", default_mode=ConversationMode.NORMAL)
    db_session.add(thread)
    await db_session.commit()
    await db_session.refresh(thread)

    groq = MockChatProvider(ProviderName.GROQ, "qwen/qwen3.8-27b")
    router = ModelRouter({ProviderName.GROQ: groq}, settings=test_settings)
    service = ChatService(router=router)

    async def is_disc():
        return False

    # Send a message with a clear personal fact: "I live in Berlin."
    events = [
        ev async for ev in service.stream_chat(
            session=db_session,
            thread_id=thread.id,
            payload=ChatRequest(content="I live in Berlin.", mode=ConversationMode.NORMAL),
            is_disconnected=is_disc,
        )
    ]

    # No memory_saved event should be emitted
    assert not any("event: memory_saved" in ev for ev in events)

    # Database should have 0 memories
    memories_count = await db_session.scalar(
        select(func.count(Memory.id)).where(Memory.user_id == user.id)
    )
    assert memories_count == 0

    # 2. Turn Smart Memory back ON
    client.patch(f"/api/v1/settings?user_id={user.id}", json={"smart_memory_enabled": True})

    # Send another durable fact: "I am a senior frontend engineer."
    events2 = [
        ev async for ev in service.stream_chat(
            session=db_session,
            thread_id=thread.id,
            payload=ChatRequest(content="I am a senior frontend engineer.", mode=ConversationMode.NORMAL),
            is_disconnected=is_disc,
        )
    ]

    # Memory should be extracted & saved
    assert any("event: memory_saved" in ev for ev in events2)
    memories_count_after = await db_session.scalar(
        select(func.count(Memory.id)).where(Memory.user_id == user.id)
    )
    assert memories_count_after > 0
