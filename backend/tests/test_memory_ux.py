import pytest
from uuid import UUID, uuid4
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ConversationMode, MemoryCategory, MessageRole
from app.models.conversation import Message, Thread, User
from app.models.memory import Memory
from app.schemas.memory import MemoryCreate
from app.services.memory.extractor import ExplicitIntent, MemoryExtractor
from app.services.memory.retriever import MemoryRetriever
from app.services.memory.service import MemoryService
from app.services.chat.service import ChatService


# =====================================================================
# TEST 1: Smart Automatic Memory Detection
# =====================================================================
@pytest.mark.asyncio
async def test_smart_auto_memory_detection(db_session: AsyncSession, user: User) -> None:
    """Smart auto-memory detects name, goals, and style preferences without explicit commands."""
    extractor = MemoryExtractor()
    text = "My name is Pranit. I'm preparing for ML interviews and I prefer concise explanations."
    res = extractor.extract(text)

    assert len(res.candidates) >= 3
    keys = {c.key for c in res.candidates}
    assert "name" in keys
    assert "interview_preparation" in keys
    assert "response_style" in keys

    service = MemoryService(db_session)
    stored = await service.process_and_store_candidates(user.id, res.candidates)
    assert len(stored) == 3

    # Check stored values
    name_mem = next(m for m in stored if m.key == "name")
    assert "Pranit" in name_mem.value

    goal_mem = next(m for m in stored if m.key == "interview_preparation")
    assert "ML interview" in goal_mem.value

    pref_mem = next(m for m in stored if m.key == "response_style")
    assert "concise" in pref_mem.value.lower()


# =====================================================================
# TEST 2: Fluff & Temporary State Rejection
# =====================================================================
@pytest.mark.asyncio
async def test_fluff_and_temporary_state_rejected(db_session: AsyncSession, user: User) -> None:
    """Fluff, moods, and generic questions are strictly not saved."""
    extractor = MemoryExtractor()
    fluff_queries = [
        "I'm tired today.",
        "I'm going out tonight.",
        "What is binary search?",
        "Tell me a joke",
        "How is the weather today?",
    ]

    for q in fluff_queries:
        res = extractor.extract(q)
        assert len(res.candidates) == 0


# =====================================================================
# TEST 3: Privacy & Secrets Rejection
# =====================================================================
@pytest.mark.asyncio
async def test_secrets_and_credentials_never_saved(db_session: AsyncSession, user: User) -> None:
    """Sensitive API keys, tokens, and passwords must never become long-term memories."""
    extractor = MemoryExtractor()
    secret_queries = [
        "My OpenAI API key is sk-1234567890abcdef1234567890abcdef",
        "My GitHub token is ghp_1234567890abcdef1234567890abcdef",
        "My password: SecretPassword123!",
        "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.e30.t-IDcSemACt8x4iTMC6Y5bP3FaVUngTVeYTrspTmGoY",
    ]

    for sq in secret_queries:
        assert extractor.contains_secrets(sq) is True
        res = extractor.extract(sq)
        assert len(res.candidates) == 0
        assert "secrets" in (res.skipped_reason or "").lower()


# =====================================================================
# TEST 4: Natural Language Memory Query ("What do you know about me?")
# =====================================================================
@pytest.mark.asyncio
async def test_query_what_do_you_remember_about_me(db_session: AsyncSession, user: User) -> None:
    """'What do you know about me?' retrieves active memories and formats them clearly."""
    service = MemoryService(db_session)
    extractor = MemoryExtractor()

    # Pre-populate memories
    res = extractor.extract("My name is Pranit. I'm preparing for ML interviews and I prefer concise explanations.")
    await service.process_and_store_candidates(user.id, res.candidates)

    cmd = extractor.detect_explicit_command("What do you know about me?")
    assert cmd.intent == ExplicitIntent.QUERY

    resp_text, evt_type, evt_payload = await service.handle_explicit_memory_command(user.id, cmd)
    assert "Pranit" in resp_text
    assert "ML interview" in resp_text
    assert "concise" in resp_text.lower()


# =====================================================================
# TEST 5: Explicit Forget ("Forget my preference for concise answers")
# =====================================================================
@pytest.mark.asyncio
async def test_explicit_forget_preference(db_session: AsyncSession, user: User) -> None:
    """'Forget my preference for concise answers' removes that memory and confirms."""
    service = MemoryService(db_session)
    extractor = MemoryExtractor()

    # Store preference
    res = extractor.extract("I prefer concise answers.")
    await service.process_and_store_candidates(user.id, res.candidates)

    all_before = await service.list_memories(user.id)
    assert all_before.total == 1

    # Forget command
    cmd = extractor.detect_explicit_command("Forget my preference for concise answers.")
    assert cmd.intent == ExplicitIntent.FORGET

    resp_text, evt_type, evt_payload = await service.handle_explicit_memory_command(user.id, cmd)
    assert evt_type == "memory_forgotten"
    assert "forgotten" in resp_text.lower()

    all_after = await service.list_memories(user.id)
    assert all_after.total == 0


# =====================================================================
# TEST 6: Relevance Awareness After Deletion
# =====================================================================
@pytest.mark.asyncio
async def test_relevance_after_preference_deleted(db_session: AsyncSession, user: User) -> None:
    """When a preference is deleted, subsequent queries no longer retrieve or inject it."""
    service = MemoryService(db_session)
    retriever = MemoryRetriever(db_session)

    # Initial preference
    mem = await service.create_memory(
        user.id,
        MemoryCreate(
            category=MemoryCategory.PREFERENCE,
            key="response_style",
            value="Prefers concise explanations",
        ),
    )

    # Before deletion: retrieved
    mems_before = await retriever.retrieve_relevant_memories(user.id, query="Explain transformers")
    assert len(mems_before) == 1
    assert mems_before[0].key == "response_style"

    # Delete preference
    await service.delete_memory(mem.id, user.id)

    # After deletion: no longer retrieved
    mems_after = await retriever.retrieve_relevant_memories(user.id, query="Explain transformers")
    assert len(mems_after) == 0


# =====================================================================
# TEST 7: Explicit Save ("My preferred language is Python. Remember this.")
# =====================================================================
@pytest.mark.asyncio
async def test_explicit_remember_command(db_session: AsyncSession, user: User) -> None:
    """'My preferred language is Python. Remember this.' explicitly saves and confirms."""
    service = MemoryService(db_session)
    extractor = MemoryExtractor()

    cmd = extractor.detect_explicit_command("My preferred language is Python. Remember this.")
    assert cmd.intent == ExplicitIntent.REMEMBER

    resp_text, evt_type, evt_payload = await service.handle_explicit_memory_command(user.id, cmd)
    assert evt_type == "memory_saved"
    assert "saved" in resp_text.lower()
    assert "Python" in resp_text

    # Verify persisted in database
    active_mems = await service.list_memories(user.id)
    assert active_mems.total == 1
    assert "Python" in active_mems.items[0].value


# =====================================================================
# TEST 8: Full Acceptance Flow (Stream Chat End-to-End)
# =====================================================================
@pytest.mark.asyncio
async def test_stream_chat_acceptance_flow(client: TestClient, db_session: AsyncSession, user: User) -> None:
    """Simulate conversation turns through REST / stream chat endpoint."""
    # 1. Create thread
    thread_res = client.post(
        "/api/v1/threads",
        json={"user_id": str(user.id), "title": "Acceptance Test Chat"},
    )
    assert thread_res.status_code == 201
    thread_id = thread_res.json()["id"]

    # 2. User introduces self with facts & preferences
    chat_res = client.post(
        f"/api/v1/threads/{thread_id}/chat",
        json={
            "content": "My name is Pranit. I'm preparing for ML interviews and I prefer concise explanations.",
            "user_id": str(user.id),
        },
    )
    assert chat_res.status_code == 200
    assert "event: message_complete" in chat_res.text

    service = MemoryService(db_session)
    mems = await service.list_memories(user.id)
    assert mems.total == 3

    # 3. Ask "What do you know about me?"
    query_res = client.post(
        f"/api/v1/threads/{thread_id}/chat",
        json={
            "content": "What do you know about me?",
            "user_id": str(user.id),
        },
    )
    assert query_res.status_code == 200
    assert "Pranit" in query_res.text

    # 4. Explicit forget
    forget_res = client.post(
        f"/api/v1/threads/{thread_id}/chat",
        json={
            "content": "Forget my preference for concise answers.",
            "user_id": str(user.id),
        },
    )
    assert forget_res.status_code == 200
    assert "event: memory_forgotten" in forget_res.text

    mems_after_forget = await service.list_memories(user.id)
    assert mems_after_forget.total == 2
    assert not any(m.key == "response_style" for m in mems_after_forget.items)

    # 5. Explicit remember
    remember_res = client.post(
        f"/api/v1/threads/{thread_id}/chat",
        json={
            "content": "My preferred language is Python. Remember this.",
            "user_id": str(user.id),
        },
    )
    assert remember_res.status_code == 200
    assert "event: memory_saved" in remember_res.text
    assert "Python" in remember_res.text

    mems_after_rem = await service.list_memories(user.id)
    assert mems_after_rem.total == 3
    assert any("Python" in m.value for m in mems_after_rem.items)

    # 6. Clear all
    clear_res = client.delete(f"/api/v1/memory/clear/all?user_id={user.id}")
    assert clear_res.status_code == 200
    assert clear_res.json()["deleted_count"] == 3

    mems_after_clear = await service.list_memories(user.id)
    assert mems_after_clear.total == 0
