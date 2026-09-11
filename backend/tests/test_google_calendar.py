from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
import pytest

from app.core.config import get_settings
from app.core.security import encrypt_secret
from app.models.integration import UserIntegration
from app.services.integrations.google_calendar import GoogleCalendarService
from app.tools.base import ToolExecutionContext
from app.tools.builtins.calendar import (
    CheckCalendarAvailabilityTool,
    CreateCalendarEventTool,
    GetCalendarEventsTool,
)


@pytest.fixture
def google_service():
    service = GoogleCalendarService()
    service.client_id = "test-client-id.apps.googleusercontent.com"
    service.client_secret = "test-client-secret"
    service.redirect_uri = "http://localhost:8001/api/v1/integrations/google/calendar/callback"
    return service


def test_get_authorization_url(google_service: GoogleCalendarService):
    user_id = uuid4()
    url = google_service.get_authorization_url(user_id=user_id, allow_write=True)
    assert "https://accounts.google.com/o/oauth2/v2/auth" in url
    assert "client_id=test-client-id.apps.googleusercontent.com" in url
    assert "state=" in url
    assert "access_type=offline" in url
    assert "calendar.events" in url


@pytest.mark.asyncio
async def test_get_status_disconnected(google_service: GoogleCalendarService):
    user_id = uuid4()
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_result

    status = await google_service.get_status(user_id, mock_session)
    assert status["connected"] is False
    assert status["account_email"] is None


@pytest.mark.asyncio
async def test_get_status_connected(google_service: GoogleCalendarService):
    user_id = uuid4()
    mock_session = AsyncMock()
    mock_result = MagicMock()
    now = datetime.now(timezone.utc)
    mock_integration = UserIntegration(
        user_id=user_id,
        provider="google",
        service="calendar",
        encrypted_access_token=encrypt_secret("test-access-token"),
        encrypted_refresh_token=encrypt_secret("test-refresh-token"),
        expires_at=now + timedelta(hours=1),
        account_email="student@gmail.com",
        scopes=["https://www.googleapis.com/auth/calendar.events.readonly"],
        is_active=True,
    )
    mock_result.scalar_one_or_none.return_value = mock_integration
    mock_session.execute.return_value = mock_result

    status = await google_service.get_status(user_id, mock_session)
    assert status["connected"] is True
    assert status["account_email"] == "student@gmail.com"
    assert "calendar.events.readonly" in status["scopes"][0]


@pytest.mark.asyncio
async def test_disconnect(google_service: GoogleCalendarService):
    user_id = uuid4()
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_integration = UserIntegration(
        user_id=user_id,
        provider="google",
        service="calendar",
        encrypted_access_token=encrypt_secret("test-token"),
        is_active=True,
    )
    mock_result.scalar_one_or_none.return_value = mock_integration
    mock_session.execute.return_value = mock_result

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_revoke:
        mock_revoke.return_value = MagicMock(status_code=200)
        success = await google_service.disconnect(user_id, mock_session)
        assert success is True
        mock_session.delete.assert_called_once_with(mock_integration)
        mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_list_events(google_service: GoogleCalendarService):
    user_id = uuid4()
    mock_session = AsyncMock()

    # Mock token retrieval
    with patch.object(google_service, "get_valid_access_token", new_callable=AsyncMock) as mock_token:
        mock_token.return_value = "decrypted-token-xyz"

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "items": [
                {
                    "id": "event_1",
                    "summary": "DSA Mock Interview",
                    "description": "LeetCode algorithms practice",
                    "start": {"dateTime": "2026-09-12T14:00:00Z"},
                    "end": {"dateTime": "2026-09-12T15:00:00Z"},
                    "location": "Google Meet",
                    "htmlLink": "https://calendar.google.com/event?id=1",
                    "status": "confirmed",
                }
            ]
        }

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_resp
            events = await google_service.list_events(user_id, mock_session)

            assert len(events) == 1
            assert events[0]["summary"] == "DSA Mock Interview"
            assert events[0]["start"] == "2026-09-12T14:00:00Z"
            assert events[0]["location"] == "Google Meet"


@pytest.mark.asyncio
async def test_check_free_busy(google_service: GoogleCalendarService):
    user_id = uuid4()
    mock_session = AsyncMock()

    with patch.object(google_service, "get_valid_access_token", new_callable=AsyncMock) as mock_token:
        mock_token.return_value = "decrypted-token-xyz"

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "calendars": {
                "primary": {
                    "busy": [
                        {"start": "2026-09-12T10:00:00Z", "end": "2026-09-12T11:00:00Z"}
                    ]
                }
            }
        }

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp
            t_min = datetime(2026, 9, 12, 9, 0, tzinfo=timezone.utc)
            t_max = datetime(2026, 9, 12, 18, 0, tzinfo=timezone.utc)
            result = await google_service.check_free_busy(user_id, mock_session, t_min, t_max)

            assert result["is_free"] is False
            assert len(result["busy_slots"]) == 1
            assert result["busy_slots"][0]["start"] == "2026-09-12T10:00:00Z"


@pytest.mark.asyncio
async def test_get_calendar_events_tool():
    tool = GetCalendarEventsTool()
    user_id = uuid4()
    mock_session = AsyncMock()
    context = ToolExecutionContext(user_id=user_id, session=mock_session)

    with patch("app.services.integrations.google_calendar.GoogleCalendarService.list_events", new_callable=AsyncMock) as mock_list:
        mock_list.return_value = [
            {"id": "1", "summary": "Math Lecture", "start": "2026-09-12T09:00:00Z", "end": "2026-09-12T10:00:00Z"}
        ]

        result = await tool.execute({"time_frame": "today"}, context)
        assert result.success is True
        assert result.data["event_count"] == 1
        assert result.data["events"][0]["summary"] == "Math Lecture"


@pytest.mark.asyncio
async def test_get_calendar_events_tool_unauthenticated():
    tool = GetCalendarEventsTool()
    context = ToolExecutionContext(user_id=None, session=None)
    result = await tool.execute({"time_frame": "today"}, context)
    assert result.success is False
    assert "authentication is required" in result.error
