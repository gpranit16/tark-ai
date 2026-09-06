from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.asyncio import configure_event_loop_policy
from app.core.config import get_settings

configure_event_loop_policy()
settings = get_settings()

engine_options = {
    "pool_pre_ping": True,
    "pool_reset_on_return": "rollback",
}
if settings.app_env == "test":
    engine_options["poolclass"] = NullPool

engine = create_async_engine(settings.database_url, **engine_options)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
