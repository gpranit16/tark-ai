import asyncio
from uuid import UUID

from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.models.conversation import User

TEST_USER_ID = UUID("00000000-0000-0000-0000-000000000001")


async def main() -> None:
    settings = get_settings()
    if settings.app_env != "development":
        print("Development seeding is only enabled when APP_ENV=development")
        return

    async with AsyncSessionLocal() as session:
        existing = await session.get(User, TEST_USER_ID)
        if existing is not None:
            print(f"User already exists: {TEST_USER_ID}")
            return

        session.add(User(id=TEST_USER_ID))
        await session.commit()
        print(f"Created dev test user: {TEST_USER_ID}")


if __name__ == "__main__":
    asyncio.run(main())
