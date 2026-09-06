import pytest
from uuid import UUID, uuid4
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ConversationMode, MemoryCategory, MessageRole
from app.models.conversation import Message, Project, Thread, User
from app.models.memory import Memory
from app.schemas.memory import MemoryCandidate, MemoryCreate, MemorySearchRequest, MemoryUpdate
from app.services.memory.extractor import MemoryExtractor
from app.services.memory.repository import MemoryRepository
from app.services.memory.retriever import MemoryRetriever
from app.services.memory.service import MemoryService
from app.services.memory.summarizer import ThreadSummaryService


# =====================================================================
# TEST A: Preference Extraction & Storage
# =====================================================================
@pytest.mark.asyncio
async def test_a_preference_extraction_and_storage(db_session: AsyncSession, user: User) -> None:
    """TEST A: User says 'I prefer concise answers.' -> memory stored."""
    extractor = MemoryExtractor()
    text = "I prefer concise answers."
    result = extractor.extract(text)

    assert len(result.candidates) >= 1
    candidate = result.candidates[0]
    assert candidate.category == MemoryCategory.PREFERENCE
    assert candidate.key == "response_style"
    assert candidate.confidence >= 0.70
    assert candidate.importance >= 0.60

    # Store via MemoryService
    service = MemoryService(db_session)
    stored = await service.process_and_store_candidates(
        user_id=user.id,
        candidates=result.candidates,
        source="conversation",
    )

    assert len(stored) == 1
    assert stored[0].key == "response_style"
    assert stored[0].user_id == user.id
    assert stored[0].is_active is True


# =====================================================================
# TEST B: Deduplication and Merging
# =====================================================================
@pytest.mark.asyncio
async def test_b_deduplication_and_merging(db_session: AsyncSession, user: User) -> None:
    """TEST B: User repeats same preference in different words -> merged/updated, no duplicate."""
    service = MemoryService(db_session)

    # Initial preference
    cand1 = MemoryCandidate(
        category=MemoryCategory.PREFERENCE,
        key="response_style",
        value="Prefers concise and brief responses",
        confidence=0.90,
        importance=0.80,
    )
    stored1 = await service.process_and_store_candidates(user.id, [cand1])
    assert len(stored1) == 1
    first_id = stored1[0].id

    # User repeats in different words mapping to same key & value concept
    extractor = MemoryExtractor()
    result = extractor.extract("Keep answers short.")
    assert len(result.candidates) >= 1

    stored2 = await service.process_and_store_candidates(user.id, result.candidates)
    assert len(stored2) == 1
    assert stored2[0].id == first_id  # Same record updated, not duplicated

    # Verify total memories for user is still exactly 1
    all_mems = await service.list_memories(user.id)
    assert all_mems.total == 1


# =====================================================================
# TEST C: Random One-off Question -> No Unnecessary Memory
# =====================================================================
@pytest.mark.asyncio
async def test_c_random_one_off_question_no_memory(db_session: AsyncSession, user: User) -> None:
    """TEST C: User asks a random one-off question -> no unnecessary long-term memory."""
    extractor = MemoryExtractor()

    # Fluff / Generic questions
    queries = [
        "hello",
        "thanks",
        "okay",
        "what is the capital of France?",
        "who is Albert Einstein?",
        "tell me a joke",
        "how does photosynthesis work?",
    ]

    for q in queries:
        result = extractor.extract(q)
        assert len(result.candidates) == 0
        assert result.skipped_reason is not None

    # Service should store nothing
    service = MemoryService(db_session)
    stored = await service.process_and_store_candidates(user.id, [])
    assert len(stored) == 0


# =====================================================================
# TEST D: Temporary Chat Mode -> No Long-Term Memory
# =====================================================================
@pytest.mark.asyncio
async def test_d_temporary_chat_no_memory(client: TestClient, db_session: AsyncSession, user: User) -> None:
    """TEST D: Temporary chat enabled -> no long-term memory write."""
    # Create a temporary thread
    thread_res = client.post(
        "/api/v1/threads",
        json={"user_id": str(user.id), "title": "Incognito Chat", "is_temporary": True},
    )
    assert thread_res.status_code == 201
    thread_id = thread_res.json()["id"]

    # Post chat in temporary thread with a preference statement
    chat_res = client.post(
        f"/api/v1/threads/{thread_id}/chat",
        json={
            "content": "I prefer concise answers.",
            "is_temporary": True,
            "user_id": str(user.id),
        },
    )
    assert chat_res.status_code == 200

    # Verify no memory was written
    service = MemoryService(db_session)
    memories = await service.list_memories(user.id)
    assert memories.total == 0


# =====================================================================
# TEST E: Preference Update & Conflict Handling
# =====================================================================
@pytest.mark.asyncio
async def test_e_preference_update_and_conflict_handling(db_session: AsyncSession, user: User) -> None:
    """TEST E: User updates preference -> old memory handled correctly and new value becomes current."""
    service = MemoryService(db_session)
    extractor = MemoryExtractor()

    # Old preference: "I prefer Python"
    res1 = extractor.extract("I prefer Python")
    assert len(res1.candidates) >= 1
    stored1 = await service.process_and_store_candidates(user.id, res1.candidates)
    assert len(stored1) == 1
    mem_id = stored1[0].id
    assert "Python" in stored1[0].value

    # Later: "I mostly use JavaScript now."
    res2 = extractor.extract("I mostly use JavaScript now.")
    assert len(res2.candidates) >= 1

    stored2 = await service.process_and_store_candidates(user.id, res2.candidates)
    assert len(stored2) == 1
    assert stored2[0].id == mem_id  # Same memory record updated
    assert "JavaScript" in stored2[0].value  # New value is current
    assert stored2[0].metadata_ is not None
    assert "history" in stored2[0].metadata_
    assert len(stored2[0].metadata_["history"]) == 1
    assert "Python" in stored2[0].metadata_["history"][0]["previous_value"]


# =====================================================================
# TEST F: Project A Memory -> Not Visible in Project B
# =====================================================================
@pytest.mark.asyncio
async def test_f_project_scoping_isolation(db_session: AsyncSession, user: User) -> None:
    """TEST F: Project A memory is not visible in Project B."""
    proj_a = Project(user_id=user.id, name="Project A")
    proj_b = Project(user_id=user.id, name="Project B")
    db_session.add_all([proj_a, proj_b])
    await db_session.commit()
    await db_session.refresh(proj_a)
    await db_session.refresh(proj_b)

    service = MemoryService(db_session)

    # Store memory scoped to Project A
    mem_a = await service.create_memory(
        user.id,
        MemoryCreate(
            category=MemoryCategory.PROJECT_CONTEXT,
            key="backend_framework",
            value="Backend uses FastAPI",
            project_id=proj_a.id,
        ),
    )
    assert mem_a.project_id == proj_a.id

    # Retrieve for Project B using MemoryRetriever
    retriever = MemoryRetriever(db_session)
    retrieved_for_b = await retriever.retrieve_relevant_memories(
        user_id=user.id,
        query="What backend framework do we use?",
        project_id=proj_b.id,
    )

    # Project A memory should NOT be retrieved for Project B
    assert not any(m.id == mem_a.id for m in retrieved_for_b)

    # Retrieve for Project A -> should find it
    retrieved_for_a = await retriever.retrieve_relevant_memories(
        user_id=user.id,
        query="What backend framework do we use?",
        project_id=proj_a.id,
    )
    assert any(m.id == mem_a.id for m in retrieved_for_a)


# =====================================================================
# TEST G: User A Memory -> Not Visible to User B
# =====================================================================
@pytest.mark.asyncio
async def test_g_user_ownership_isolation(client: TestClient, db_session: AsyncSession, user: User) -> None:
    """TEST G: User A memory is not visible or modifiable by User B."""
    user_b = User(id=uuid4())
    db_session.add(user_b)
    await db_session.commit()
    await db_session.refresh(user_b)

    service = MemoryService(db_session)
    mem_a = await service.create_memory(
        user.id,
        MemoryCreate(
            category=MemoryCategory.FACT,
            key="user_role",
            value="Works as Senior Backend Engineer",
        ),
    )

    # User B list memories -> 0 items
    list_res = client.get(f"/api/v1/memory?user_id={user_b.id}")
    assert list_res.status_code == 200
    assert list_res.json()["total"] == 0

    # User B attempts to get User A's memory -> 404
    get_res = client.get(f"/api/v1/memory/{mem_a.id}?user_id={user_b.id}")
    assert get_res.status_code == 404

    # User B attempts to patch User A's memory -> 404
    patch_res = client.patch(
        f"/api/v1/memory/{mem_a.id}?user_id={user_b.id}",
        json={"value": "Hacked value"},
    )
    assert patch_res.status_code == 404

    # User B attempts to delete User A's memory -> 404
    del_res = client.delete(f"/api/v1/memory/{mem_a.id}?user_id={user_b.id}")
    assert del_res.status_code == 404


# =====================================================================
# TEST H: Long Conversation -> Thread Summary Created
# =====================================================================
@pytest.mark.asyncio
async def test_h_long_conversation_thread_summary(db_session: AsyncSession, user: User) -> None:
    """TEST H: Long conversation triggers thread summary while recent messages remain available."""
    thread = Thread(user_id=user.id, title="Architecture Discussion")
    db_session.add(thread)
    await db_session.commit()
    await db_session.refresh(thread)

    # Add 12 messages to exceed threshold of 10
    messages = []
    for i in range(12):
        role = MessageRole.USER if i % 2 == 0 else MessageRole.ASSISTANT
        content = f"Turn {i}: Discussing architectural decision point #{i}"
        msg = Message(thread_id=thread.id, role=role, content=content)
        messages.append(msg)
    db_session.add_all(messages)
    await db_session.commit()

    summarizer = ThreadSummaryService(db_session)
    summary = await summarizer.maybe_update_thread_summary(thread.id, threshold=10, recent_window=4)

    assert summary is not None
    assert "Turn 0" in summary
    assert "Turn 1" in summary

    # Verify thread in DB has summary recorded
    await db_session.refresh(thread)
    assert thread.summary is not None
    assert thread.summarized_message_id is not None
    assert thread.summary_updated_at is not None


# =====================================================================
# Additional Tests: REST API CRUD, Search, Thresholds, & Edge Cases
# =====================================================================
def test_memory_rest_api_crud(client: TestClient, user: User) -> None:
    """Verify REST API create, read, update, delete, search, and extract."""
    # 1. Create
    res = client.post(
        f"/api/v1/memory?user_id={user.id}",
        json={
            "category": "preference",
            "key": "formatting_preference",
            "value": "Always use markdown tables for tabular data",
            "confidence": 0.9,
            "importance": 0.8,
        },
    )
    assert res.status_code == 201
    mem_id = res.json()["id"]
    assert res.json()["key"] == "formatting_preference"

    # 2. Get
    get_res = client.get(f"/api/v1/memory/{mem_id}?user_id={user.id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == mem_id

    # 3. Update
    patch_res = client.patch(
        f"/api/v1/memory/{mem_id}?user_id={user.id}",
        json={"value": "Updated formatting preference", "is_active": False},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["value"] == "Updated formatting preference"
    assert patch_res.json()["is_active"] is False

    # 4. Search
    search_res = client.post(
        f"/api/v1/memory/search?user_id={user.id}",
        json={"query": "formatting"},
    )
    assert search_res.status_code == 200

    # 5. Extract API
    ext_res = client.post(
        "/api/v1/memory/extract",
        json={"text": "I'm learning LangChain."},
    )
    assert ext_res.status_code == 200
    assert len(ext_res.json()["candidates"]) >= 1
    assert ext_res.json()["candidates"][0]["key"] == "learning_topic"

    # 6. Delete
    del_res = client.delete(f"/api/v1/memory/{mem_id}?user_id={user.id}")
    assert del_res.status_code == 204


@pytest.mark.asyncio
async def test_document_fact_not_becoming_user_memory(db_session: AsyncSession, user: User) -> None:
    """Verify document RAG queries do not pollute long-term user memory."""
    extractor = MemoryExtractor()

    # RAG document question
    doc_query = "Summarize the revenue figures on page 3 of the attached PDF."
    result = extractor.extract(doc_query, is_rag_query=True)

    assert len(result.candidates) == 0
    assert "RAG document query" in (result.skipped_reason or "")
