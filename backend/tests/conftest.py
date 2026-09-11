import os
from collections.abc import AsyncGenerator, Generator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncSession

os.environ.setdefault("APP_ENV", "test")

postgres_user = os.environ.get("POSTGRES_USER", "tarkai")
postgres_password = os.environ.get("POSTGRES_PASSWORD", "change-me")
postgres_host = os.environ.get("POSTGRES_HOST", "localhost")
postgres_port = os.environ.get("POSTGRES_PORT", "5433")
postgres_db = os.environ.get("POSTGRES_DB_TEST", "tarkai_test")
os.environ["DATABASE_URL"] = (
    f"postgresql+asyncpg://{postgres_user}:{postgres_password}@{postgres_host}:{postgres_port}/{postgres_db}"
)

from app.core.asyncio import configure_event_loop_policy

configure_event_loop_policy()

from app.db.session import AsyncSessionLocal
from app.main import app
from app.models.conversation import AuthToken, Message, Project, Thread, User
from app.models.file import File
from app.models.document import ParsedDocument
from app.models.chunk import DocumentChunk
from app.models.memory import Memory
from app.models.research import ResearchSession
from app.models.settings import UserSettings
from app.models.integration import UserIntegration
from app.models.task import Task, TaskCategory, TaskReminder
from app.db.base import Base
from app.db.session import engine


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
async def clean_database() -> AsyncGenerator[None, None]:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncSessionLocal() as session:
        await _clear_tables(session)
    yield
    async with AsyncSessionLocal() as session:
        await _clear_tables(session)


async def _clear_tables(session: AsyncSession) -> None:
    from uuid import UUID
    dev_uid = UUID("00000000-0000-0000-0000-000000000001")
    await session.execute(delete(TaskReminder))
    await session.execute(delete(Task))
    await session.execute(delete(TaskCategory))
    await session.execute(delete(UserIntegration))
    await session.execute(delete(UserSettings))
    await session.execute(delete(ResearchSession))
    await session.execute(delete(Memory))
    await session.execute(delete(DocumentChunk))
    await session.execute(delete(ParsedDocument))
    await session.execute(delete(File))
    await session.execute(delete(Message))
    await session.execute(delete(Thread))
    await session.execute(delete(Project))
    await session.execute(delete(AuthToken))
    await session.execute(delete(User))
    await session.commit()
    
    session.add(User(id=dev_uid))
    await session.commit()



@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


@pytest.fixture
async def user(db_session: AsyncSession) -> User:
    item = User(id=uuid4())
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)
    return item


@pytest.fixture
async def project(db_session: AsyncSession, user: User) -> Project:
    item = Project(user_id=user.id, name="Research")
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)
    return item


@pytest.fixture
async def vector_extension_exists(db_session: AsyncSession) -> bool:
    result = await db_session.scalar(text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')"))
    return bool(result)
