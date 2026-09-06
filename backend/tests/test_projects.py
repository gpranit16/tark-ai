from uuid import uuid4
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession
import pytest

from app.core.enums import MemoryCategory
from app.models.conversation import Project, Thread, User
from app.models.file import File
from app.models.memory import Memory
from app.models.research import ResearchSession
from app.services.chat.project_context import ProjectContextBuilder


def test_project_crud_and_archive(client: TestClient, user: User):
    # 1. Create project
    create_payload = {
        "user_id": str(user.id),
        "name": "Phase 11 AI Workspace",
        "description": "Comprehensive workspace testing",
        "custom_instructions": "Always respond in JSON format with concise keys.",
        "avatar": "🚀",
        "project_metadata": {"domain": "engineering", "priority": "high"},
    }
    res = client.post("/api/v1/projects", json=create_payload)
    assert res.status_code == 201
    data = res.json()
    project_id = data["id"]
    assert data["name"] == "Phase 11 AI Workspace"
    assert data["custom_instructions"] == "Always respond in JSON format with concise keys."
    assert data["avatar"] == "🚀"
    assert data["is_archived"] is False
    assert data["project_metadata"]["domain"] == "engineering"

    # 2. Get project by ID
    res = client.get(f"/api/v1/projects/{project_id}")
    assert res.status_code == 200
    assert res.json()["name"] == "Phase 11 AI Workspace"
    assert res.json()["file_count"] == 0
    assert res.json()["thread_count"] == 0

    # 3. Update project
    update_payload = {
        "name": "Updated AI Workspace",
        "custom_instructions": "You are a senior staff engineer.",
        "avatar": "⚡",
    }
    res = client.patch(f"/api/v1/projects/{project_id}", json=update_payload)
    assert res.status_code == 200
    assert res.json()["name"] == "Updated AI Workspace"
    assert res.json()["custom_instructions"] == "You are a senior staff engineer."
    assert res.json()["avatar"] == "⚡"

    # 4. Archive project
    res = client.post(f"/api/v1/projects/{project_id}/archive")
    assert res.status_code == 200
    assert res.json()["is_archived"] is True

    # 5. List projects without archived
    res = client.get(f"/api/v1/projects?user_id={user.id}&include_archived=false")
    assert res.status_code == 200
    assert len(res.json()) == 0

    # List projects with archived
    res = client.get(f"/api/v1/projects?user_id={user.id}&include_archived=true")
    assert res.status_code == 200
    assert len(res.json()) == 1

    # 6. Restore project
    res = client.post(f"/api/v1/projects/{project_id}/restore")
    assert res.status_code == 200
    assert res.json()["is_archived"] is False

    # 7. Delete project
    res = client.delete(f"/api/v1/projects/{project_id}")
    assert res.status_code == 204

    # Verify deleted
    res = client.get(f"/api/v1/projects/{project_id}")
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_project_files_attachment_and_scoping(client: TestClient, db_session: AsyncSession, user: User, project: Project):
    # Create file record
    file1 = File(
        user_id=user.id,
        original_filename="notes.pdf",
        mime_type="application/pdf",
        extension="pdf",
        size_bytes=1024,
        storage_provider="local",
        storage_key=f"uploads/{user.id}/notes.pdf",
    )
    db_session.add(file1)
    await db_session.commit()
    await db_session.refresh(file1)

    # Attach file1 to project
    res = client.post(f"/api/v1/projects/{project.id}/files/{file1.id}")
    assert res.status_code == 200
    assert res.json()["project_id"] == str(project.id)

    # List project files
    res = client.get(f"/api/v1/projects/{project.id}/files")
    assert res.status_code == 200
    files = res.json()
    assert len(files) == 1
    assert files[0]["id"] == str(file1.id)

    # Verify project file_count reflects in project detail
    res = client.get(f"/api/v1/projects/{project.id}")
    assert res.status_code == 200
    assert res.json()["file_count"] == 1

    # Detach file1 from project
    res = client.delete(f"/api/v1/projects/{project.id}/files/{file1.id}")
    assert res.status_code == 200
    assert res.json()["project_id"] is None

    # Verify empty now
    res = client.get(f"/api/v1/projects/{project.id}/files")
    assert res.status_code == 200
    assert len(res.json()) == 0


def test_project_threads_association_and_move(client: TestClient, user: User, project: Project):
    # 1. Create a thread directly associated with project
    create_thread_payload = {
        "user_id": str(user.id),
        "project_id": str(project.id),
        "title": "Architecture Discussions",
    }
    res = client.post("/api/v1/threads", json=create_thread_payload)
    assert res.status_code == 201
    thread1_id = res.json()["id"]
    assert res.json()["project_id"] == str(project.id)

    # 2. Create standalone thread
    res = client.post("/api/v1/threads", json={"user_id": str(user.id), "title": "Random Idea"})
    assert res.status_code == 201
    thread2_id = res.json()["id"]
    assert res.json()["project_id"] is None

    # 3. Move standalone thread2 to project
    res = client.post(f"/api/v1/projects/{project.id}/threads/{thread2_id}")
    assert res.status_code == 200
    assert res.json()["project_id"] == str(project.id)

    # 4. List project threads
    res = client.get(f"/api/v1/projects/{project.id}/threads")
    assert res.status_code == 200
    threads = res.json()
    assert len(threads) == 2

    # 5. Remove thread2 from project
    res = client.delete(f"/api/v1/projects/{project.id}/threads/{thread2_id}")
    assert res.status_code == 200
    assert res.json()["project_id"] is None

    # Verify project thread list now has 1 thread
    res = client.get(f"/api/v1/projects/{project.id}/threads")
    assert res.status_code == 200
    assert len(res.json()) == 1
    assert res.json()[0]["id"] == thread1_id


from app.core.enums import MemoryCategory


@pytest.mark.asyncio
async def test_project_memory_scoping_and_cross_project_isolation(client: TestClient, db_session: AsyncSession, user: User):
    # Create two projects
    p1 = Project(user_id=user.id, name="Project Alpha")
    p2 = Project(user_id=user.id, name="Project Beta")
    db_session.add_all([p1, p2])
    await db_session.commit()
    await db_session.refresh(p1)
    await db_session.refresh(p2)

    # Add memory to Project Alpha
    m1 = Memory(
        user_id=user.id,
        project_id=p1.id,
        category=MemoryCategory.FACT,
        key="database",
        value="Alpha project uses PostgreSQL 16 on port 5433.",
        confidence=0.95,
    )
    # Add memory to Project Beta
    m2 = Memory(
        user_id=user.id,
        project_id=p2.id,
        category=MemoryCategory.FACT,
        key="database",
        value="Beta project is built in Go with DynamoDB.",
        confidence=0.90,
    )
    # Add global memory (no project)
    m3 = Memory(
        user_id=user.id,
        project_id=None,
        category=MemoryCategory.PREFERENCE,
        key="ui_theme",
        value="User prefers dark theme and concise code samples.",
        confidence=0.88,
    )
    db_session.add_all([m1, m2, m3])
    await db_session.commit()

    # Query Project Alpha memories
    res = client.get(f"/api/v1/projects/{p1.id}/memory")
    assert res.status_code == 200
    memories = res.json()
    assert len(memories) == 1
    assert "PostgreSQL" in memories[0]["value"]

    # Query Project Beta memories
    res = client.get(f"/api/v1/projects/{p2.id}/memory")
    assert res.status_code == 200
    memories = res.json()
    assert len(memories) == 1
    assert "Go with DynamoDB" in memories[0]["value"]


@pytest.mark.asyncio
async def test_project_deep_research_linking(client: TestClient, db_session: AsyncSession, user: User, project: Project):
    thread = Thread(user_id=user.id, title="Research Thread")
    db_session.add(thread)
    await db_session.commit()
    await db_session.refresh(thread)

    # Create a research session linked to project
    session1 = ResearchSession(
        user_id=user.id,
        project_id=project.id,
        thread_id=thread.id,
        query="Distributed consensus in modern LLM clusters",
        status="completed",
        research_metadata={"report_markdown": "# Distributed Consensus Report\n\nDetailed findings..."},
    )
    # Create an unlinked research session
    session2 = ResearchSession(
        user_id=user.id,
        project_id=None,
        thread_id=thread.id,
        query="Quantum computing overview",
        status="completed",
        research_metadata={"report_markdown": "# Quantum Report"},
    )
    db_session.add_all([session1, session2])
    await db_session.commit()

    # Query project research history
    res = client.get(f"/api/v1/projects/{project.id}/research")
    assert res.status_code == 200
    sessions = res.json()
    assert len(sessions) == 1
    assert sessions[0]["query"] == "Distributed consensus in modern LLM clusters"


def test_project_context_builder_precedence():
    proj = Project(
        name="TarkAI Workspace",
        custom_instructions="Respond only in bullet points. Be extremely direct.",
    )
    builder = ProjectContextBuilder(
        system_prompt="Base system prompt",
        project=proj,
        memory_context="Prefers async python. Uses FastAPI and SQLAlchemy.",
        rag_context="[Document: architecture.md] High level architecture of TarkAI.",
        thread_summary="Discussed database schemas and Alembic migrations in previous turns.",
    )
    system_text = builder.build_system_content()

    assert "Base system prompt" in system_text
    assert "PROJECT WORKSPACE: TARKAI WORKSPACE" in system_text
    assert "Respond only in bullet points. Be extremely direct." in system_text
    assert "Prefers async python" in system_text
    assert "architecture.md" in system_text
    assert "Alembic migrations" in system_text

    # Precedence check: instructions appear before memories, memories before rag, rag before summary
    idx_instructions = system_text.find("Custom Project Instructions")
    idx_memory = system_text.find("Prefers async python")
    idx_rag = system_text.find("architecture.md")
    idx_summary = system_text.find("Conversation History Summary")
    assert idx_instructions < idx_memory < idx_rag < idx_summary


def test_cross_user_isolation(client: TestClient, user: User):
    user2_id = uuid4()

    # Create project owned by user 1
    create_payload = {
        "user_id": str(user.id),
        "name": "User1 Private Project",
    }
    res = client.post("/api/v1/projects", json=create_payload)
    assert res.status_code == 201
    p1_id = res.json()["id"]

    # User 2 listing should NOT see project1
    res = client.get(f"/api/v1/projects?user_id={user2_id}")
    assert res.status_code == 200
    assert len(res.json()) == 0

    # User 2 cannot access user 1's project
    res = client.get(f"/api/v1/projects/{p1_id}?user_id={user2_id}")
    assert res.status_code == 403
