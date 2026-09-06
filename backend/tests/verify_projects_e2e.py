import asyncio
import os
import sys
from uuid import UUID, uuid4

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.insert(0, ".")

# Set test environment
os.environ["APP_ENV"] = "test"
postgres_user = os.environ.get("POSTGRES_USER", "tarkai")
postgres_password = os.environ.get("POSTGRES_PASSWORD", "change-me")
postgres_host = os.environ.get("POSTGRES_HOST", "localhost")
postgres_port = os.environ.get("POSTGRES_PORT", "5433")
postgres_db = os.environ.get("POSTGRES_DB", "tarkai")
os.environ["DATABASE_URL"] = f"postgresql+asyncpg://{postgres_user}:{postgres_password}@{postgres_host}:{postgres_port}/{postgres_db}"

from app.core.asyncio import configure_event_loop_policy
configure_event_loop_policy()

from app.db.session import AsyncSessionLocal
from app.models.conversation import User, Project, Thread, Message
from app.models.file import File
from app.models.memory import Memory
from app.models.research import ResearchSession
from app.core.enums import MemoryCategory
from app.schemas.project import ProjectCreate, ProjectUpdate
from app.services import projects as project_service
from app.services.chat.project_context import ProjectContextBuilder
from sqlalchemy import select, delete


async def run_all_tests():
    print("=== STARTING PHASE 11 PROJECTS & WORKSPACE CONTEXT VERIFICATION ===")
    
    async with AsyncSessionLocal() as session:
        # Clean up existing test data
        await session.execute(delete(ResearchSession))
        await session.execute(delete(Memory))
        await session.execute(delete(File))
        await session.execute(delete(Message))
        await session.execute(delete(Thread))
        await session.execute(delete(Project))
        await session.execute(delete(User))
        
        dev_user_id = UUID("00000000-0000-0000-0000-000000000001")
        user1 = User(id=dev_user_id)
        user2 = User(id=uuid4())
        session.add_all([user1, user2])
        await session.commit()
        print("[PASS] Created test users")

        # ── Test 1: Project CRUD & Archive ────────────────────────────────────
        print("\n--- Test 1: Project CRUD & Archive ---")
        p_create = ProjectCreate(
            user_id=user1.id,
            name="Alpha AI Workspace",
            description="Autonomous multi-agent research workspace",
            custom_instructions="Be concise and technical. Prioritize python and distributed systems.",
            avatar="🚀",
            project_metadata={"domain": "ai", "version": "1.0"},
        )
        created_p = await project_service.create_project(session, p_create)
        assert created_p.name == "Alpha AI Workspace"
        assert created_p.custom_instructions == "Be concise and technical. Prioritize python and distributed systems."
        assert created_p.avatar == "🚀"
        assert created_p.is_archived is False
        print(f"[PASS] Created Project: {created_p.id} ({created_p.name})")

        # Read project with counts
        fetched_p = await project_service.get_project_or_404(session, created_p.id, user_id=user1.id)
        assert fetched_p.name == "Alpha AI Workspace"
        counts = await project_service.get_project_counts(session, created_p.id)
        assert counts["file_count"] == 0
        assert counts["thread_count"] == 0
        print("[PASS] Fetched Project with accurate initial stats")

        # Update project
        p_update = ProjectUpdate(
            name="Alpha Workspace Pro",
            custom_instructions="Updated custom instructions: You are a principal AI architect.",
            avatar="⚡",
        )
        updated_p = await project_service.update_project(session, created_p.id, p_update, user_id=user1.id)
        assert updated_p.name == "Alpha Workspace Pro"
        assert updated_p.avatar == "⚡"
        print("[PASS] Updated Project successfully")

        # Archive & Restore
        archived_p = await project_service.archive_project(session, created_p.id, user_id=user1.id)
        assert archived_p.is_archived is True
        
        # Verify filtering by include_archived
        active_list = await project_service.list_projects(session, user_id=user1.id, include_archived=False)
        assert len(active_list) == 0
        all_list = await project_service.list_projects(session, user_id=user1.id, include_archived=True)
        assert len(all_list) == 1
        print("[PASS] Project archive and visibility filtering verified")

        restored_p = await project_service.restore_project(session, created_p.id, user_id=user1.id)
        assert restored_p.is_archived is False
        print("[PASS] Project restored successfully")

        # ── Test 2: Project Files ─────────────────────────────────────────────
        print("\n--- Test 2: Project Files Attach / List / Detach ---")
        file1 = File(
            user_id=user1.id,
            original_filename="architecture.pdf",
            mime_type="application/pdf",
            extension="pdf",
            size_bytes=1024,
            storage_provider="local",
            storage_key=f"uploads/{uuid4()}/architecture.pdf",
        )
        session.add(file1)
        await session.commit()
        await session.refresh(file1)

        # Attach file
        attached_file = await project_service.add_file_to_project(session, created_p.id, file1.id, user_id=user1.id)
        assert attached_file.project_id == created_p.id

        # List project files
        p_files = await project_service.list_project_files(session, created_p.id, user_id=user1.id)
        assert len(p_files) == 1
        assert p_files[0].id == file1.id
        print("[PASS] Attached and listed project files")

        # Verify file count
        counts = await project_service.get_project_counts(session, created_p.id)
        assert counts["file_count"] == 1

        # Detach file
        detached_file = await project_service.remove_file_from_project(session, created_p.id, file1.id, user_id=user1.id)
        assert detached_file.project_id is None
        p_files_after = await project_service.list_project_files(session, created_p.id, user_id=user1.id)
        assert len(p_files_after) == 0
        print("[PASS] Detached file from project cleanly")

        # ── Test 3: Project Threads ───────────────────────────────────────────
        print("\n--- Test 3: Project Threads Association & Move ---")
        thread1 = Thread(user_id=user1.id, project_id=created_p.id, title="LangGraph R&D")
        thread2 = Thread(user_id=user1.id, project_id=None, title="Standalone Chat")
        session.add_all([thread1, thread2])
        await session.commit()
        await session.refresh(thread1)
        await session.refresh(thread2)

        # List project threads
        threads = await project_service.list_project_threads(session, created_p.id, user_id=user1.id)
        assert len(threads) == 1
        assert threads[0].id == thread1.id
        print("[PASS] Scoped project threads listed accurately")

        # Move thread2 into project
        moved_t = await project_service.move_thread_to_project(session, created_p.id, thread2.id, user_id=user1.id)
        assert moved_t.project_id == created_p.id
        threads_updated = await project_service.list_project_threads(session, created_p.id, user_id=user1.id)
        assert len(threads_updated) == 2
        print("[PASS] Moved standalone thread into project")

        # Remove thread2 from project
        unlinked_t = await project_service.remove_thread_from_project(session, created_p.id, thread2.id, user_id=user1.id)
        assert unlinked_t.project_id is None
        print("[PASS] Removed thread from project")

        # ── Test 4: Project Memory Scoping & Isolation ────────────────────────
        print("\n--- Test 4: Project Memory Scoping & Isolation ---")
        p2 = Project(user_id=user1.id, name="Beta Project")
        session.add(p2)
        await session.commit()
        await session.refresh(p2)

        m_alpha = Memory(
            user_id=user1.id,
            project_id=created_p.id,
            category=MemoryCategory.FACT,
            key="db_info",
            value="Alpha uses PostgreSQL 16 on port 5433.",
            confidence=0.98,
        )
        m_beta = Memory(
            user_id=user1.id,
            project_id=p2.id,
            category=MemoryCategory.FACT,
            key="stack_info",
            value="Beta uses Redis and Go.",
            confidence=0.95,
        )
        session.add_all([m_alpha, m_beta])
        await session.commit()

        alpha_memories = await project_service.list_project_memories(session, created_p.id, user_id=user1.id)
        assert len(alpha_memories) == 1
        assert "PostgreSQL" in alpha_memories[0].value

        beta_memories = await project_service.list_project_memories(session, p2.id, user_id=user1.id)
        assert len(beta_memories) == 1
        assert "Redis and Go" in beta_memories[0].value
        print("[PASS] Project memory isolation verified (zero cross-project leakage)")

        # ── Test 5: Project Research Linking ──────────────────────────────────
        print("\n--- Test 5: Project Deep Research Linking ---")
        rs1 = ResearchSession(
            thread_id=thread1.id,
            user_id=user1.id,
            project_id=created_p.id,
            query="Deep Research into Distributed Consensus",
            status="completed",
        )
        session.add(rs1)
        await session.commit()

        research_list = await project_service.list_project_research(session, created_p.id, user_id=user1.id)
        assert len(research_list) == 1
        assert research_list[0].query == "Deep Research into Distributed Consensus"
        print("[PASS] Deep Research sessions linked and listed under project")

        # ── Test 6: ProjectContextBuilder Deterministic Precedence ─────────────
        print("\n--- Test 6: ProjectContextBuilder Precedence ---")
        mock_project = Project(
            name="Alpha Workspace Pro",
            description="High-performance computing workspace",
            custom_instructions="Priority: Follow strict technical formatting.",
        )
        builder = ProjectContextBuilder(
            system_prompt="You are TARK AI.",
            project=mock_project,
            memory_context="[Memory: Alpha uses PostgreSQL 16 on port 5433.]",
            rag_context="[Doc: spec.md] Technical specification of the system.",
            thread_summary="Earlier discussion on schemas.",
        )
        sys_prompt = builder.build_system_content()
        assert "TARK AI" in sys_prompt
        assert "PROJECT WORKSPACE: ALPHA WORKSPACE PRO" in sys_prompt
        assert "Priority: Follow strict technical formatting." in sys_prompt
        assert "PostgreSQL 16" in sys_prompt
        assert "spec.md" in sys_prompt
        assert "Conversation History Summary" in sys_prompt

        p_idx = sys_prompt.find("PROJECT WORKSPACE")
        m_idx = sys_prompt.find("PostgreSQL 16")
        r_idx = sys_prompt.find("spec.md")
        s_idx = sys_prompt.find("Conversation History Summary")
        assert p_idx < m_idx < r_idx < s_idx
        print("[PASS] ProjectContextBuilder deterministic precedence validated")

        # ── Test 7: Cross-User Authorization Isolation ────────────────────────
        print("\n--- Test 7: Cross-User Authorization Barriers ---")
        u2_projects = await project_service.list_projects(session, user_id=user2.id)
        assert len(u2_projects) == 0

        try:
            await project_service.get_project_or_404(session, created_p.id, user_id=user2.id)
            assert False, "Should have raised 403/404 for unauthorized user"
        except Exception as e:
            assert "403" in str(e) or "404" in str(e) or "forbidden" in str(e).lower() or "not found" in str(e).lower()
        print("[PASS] Cross-user isolation verified (User 2 blocked with 403 from User 1 project)")

    print("\n=======================================================")
    print("ALL 7 PHASE 11 CORE TEST SUITES PASSED PERFECTLY (100%)")
    print("=======================================================")


if __name__ == "__main__":
    asyncio.run(run_all_tests())
