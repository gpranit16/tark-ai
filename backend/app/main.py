from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.db.session import AsyncSessionLocal, engine
from app.models.conversation import User

settings = get_settings()
DEV_TEST_USER_ID = UUID("00000000-0000-0000-0000-000000000001")


async def _ensure_dev_user() -> None:
    """Ensure the hardcoded dev test user always exists on startup (dev only)."""
    if settings.app_env != "development":
        return
    async with AsyncSessionLocal() as session:
        existing = await session.get(User, DEV_TEST_USER_ID)
        if existing is None:
            session.add(User(id=DEV_TEST_USER_ID))
            await session.commit()
            print(f"[startup] Dev test user seeded: {DEV_TEST_USER_ID}")
        else:
            print(f"[startup] Dev test user already exists: {DEV_TEST_USER_ID}")


async def _warmup_ml_models() -> None:
    """Pre-warm embedding and reranker model singletons in background thread pool."""
    if settings.app_env == "test":
        return
    import asyncio
    try:
        from app.services.embeddings.bge import LocalBGEEmbeddingProvider
        from app.services.reranking.bge_reranker import warmup_reranker
        await asyncio.to_thread(LocalBGEEmbeddingProvider()._get_model)
        await asyncio.to_thread(warmup_reranker)
    except Exception as e:
        print(f"[startup] Model warmup skipped or failed: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio
    await _ensure_dev_user()
    asyncio.create_task(_warmup_ml_models())
    yield


def get_allowed_origins() -> list[str]:
    origins: list[str] = []
    if settings.cors_origins:
        for o in settings.cors_origins.split(","):
            cleaned = o.strip().rstrip("/")
            if cleaned and cleaned not in origins:
                origins.append(cleaned)
    if settings.frontend_url:
        fe = settings.frontend_url.strip().rstrip("/")
        if fe and fe not in origins:
            origins.append(fe)
    if settings.app_env in ("development", "test"):
        for local_url in ("http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000"):
            if local_url not in origins:
                origins.append(local_url)
    return origins if origins else ["*"]


app = FastAPI(
    title="TARK AI Backend",
    version="0.1.0",
    debug=settings.app_env == "development",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.post("/dev/seed-test-user", tags=["development"])
async def seed_test_user() -> dict[str, object]:
    if settings.app_env != "development":
        return {"status": "disabled", "message": "Development seeding is only available in APP_ENV=development"}

    async with AsyncSessionLocal() as session:
        existing = await session.get(User, DEV_TEST_USER_ID)
        if existing is not None:
            return {"status": "ok", "created": False, "user_id": str(DEV_TEST_USER_ID)}

        session.add(User(id=DEV_TEST_USER_ID))
        await session.commit()
        return {"status": "ok", "created": True, "user_id": str(DEV_TEST_USER_ID)}
