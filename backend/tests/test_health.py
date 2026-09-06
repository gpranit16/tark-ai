from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def test_health_endpoint(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_database_connectivity(db_session: AsyncSession, vector_extension_exists: bool) -> None:
    result = await db_session.scalar(text("SELECT 1"))

    assert result == 1
    assert vector_extension_exists is True
