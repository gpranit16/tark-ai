"""Integration tests for Calendar tool calling inside Chat Tool Loop."""
from datetime import datetime, timezone
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

from app.core.enums import ConversationMode, MessageRole
from app.models.integration import UserIntegration
from app.providers.base import NormalizedMessage, ProviderStreamEvent, UsageMetadata
from app.services.chat.router import ModelRouter, ProviderSelection
from app.services.chat.tool_loop import (
    ToolCallOrchestrator,
    format_tools_system_prompt,
    parse_tool_calls,
)
from app.tools.base import ToolExecutionContext, ToolResult
from app.tools.builtins.calendar import (
    CheckCalendarAvailabilityTool,
    CreateCalendarEventTool,
    GetCalendarEventsTool,
)
from app.tools.registry import ToolRegistry, get_tool_registry

USER_A_ID = UUID("11111111-1111-1111-1111-111111111111")
USER_B_ID = UUID("22222222-2222-2222-2222-222222222222")


@pytest.fixture
def mock_session():
    session = AsyncMock()
    return session


@pytest.mark.asyncio
async def test_calendar_tools_registration():
    registry = get_tool_registry()
    assert registry.has_tool("get_calendar_events")
    assert registry.has_tool("check_calendar_availability")
    assert registry.has_tool("create_calendar_event")
    assert registry.has_tool("calendar")
    assert registry.has_tool("calendar_events")
    assert registry.has_tool("free_busy")


@pytest.mark.asyncio
async def test_format_tools_system_prompt_connected_vs_disconnected():
    registry = get_tool_registry()
    
    prompt_connected = format_tools_system_prompt(registry, allowed_tools=["get_calendar_events", "web_search"], has_calendar=True)
    assert "get_calendar_events" in prompt_connected
    assert "PERSONAL CALENDAR & SCHEDULE INTEGRATION" in prompt_connected
    assert "Google Calendar IS connected" in prompt_connected

    prompt_disconnected = format_tools_system_prompt(registry, allowed_tools=["web_search"], has_calendar=False)
    assert "get_calendar_events" not in prompt_disconnected
    assert "Google Calendar is NOT connected" in prompt_disconnected


@pytest.mark.asyncio
async def test_get_calendar_events_tool_tomorrow(mock_session):
    tool = GetCalendarEventsTool()
    ctx = ToolExecutionContext(user_id=USER_A_ID, session=mock_session)

    mock_events = [
        {"id": "ev1", "summary": "Team Sync", "start": "2026-09-12T10:00:00Z", "end": "2026-09-12T11:00:00Z"}
    ]
    with patch("app.tools.builtins.calendar.GoogleCalendarService") as MockService:
        instance = MockService.return_value
        instance.list_events = AsyncMock(return_value=mock_events)

        result = await tool.execute({"time_frame": "tomorrow"}, ctx)
        assert result.success is True
        assert result.data["event_count"] == 1
        assert result.data["time_frame"] == "tomorrow"
        assert result.data["events"][0]["summary"] == "Team Sync"


@pytest.mark.asyncio
async def test_check_calendar_availability_tool(mock_session):
    tool = CheckCalendarAvailabilityTool()
    ctx = ToolExecutionContext(user_id=USER_A_ID, session=mock_session)

    mock_freebusy = {"is_free": True, "busy_slots": []}
    with patch("app.tools.builtins.calendar.GoogleCalendarService") as MockService:
        instance = MockService.return_value
        instance.check_free_busy = AsyncMock(return_value=mock_freebusy)

        result = await tool.execute({"target_date": "tomorrow", "start_time": "17:00", "end_time": "18:00"}, ctx)
        assert result.success is True
        assert result.data["is_free"] is True
        assert result.data["busy_slots"] == []


@pytest.mark.asyncio
async def test_create_calendar_event_permission_enforcement(mock_session):
    tool = CreateCalendarEventTool()
    ctx = ToolExecutionContext(user_id=USER_A_ID, session=mock_session)

    # 1. No integration found
    mock_result1 = MagicMock()
    mock_result1.scalars.return_value.first.return_value = None
    mock_session.execute = AsyncMock(return_value=mock_result1)

    res = await tool.execute({"title": "DSA Practice", "start_time": "2026-09-12T19:00:00Z", "end_time": "2026-09-12T20:00:00Z"}, ctx)
    assert res.success is False
    assert "not connected" in res.error.lower()

    # 2. Integration has write permission
    mock_integration = UserIntegration(
        user_id=USER_A_ID,
        provider="google",
        service="calendar",
        is_active=True,
        scopes=["https://www.googleapis.com/auth/calendar.events"],
        encrypted_access_token="fake",
    )
    mock_result2 = MagicMock()
    mock_result2.scalars.return_value.first.return_value = mock_integration
    mock_session.execute = AsyncMock(return_value=mock_result2)

    with patch("app.tools.builtins.calendar.GoogleCalendarService") as MockService:
        instance = MockService.return_value
        instance.create_event = AsyncMock(return_value={
            "id": "evt_new",
            "summary": "DSA Practice",
            "start": "2026-09-12T19:00:00+05:30",
            "end": "2026-09-12T20:00:00+05:30",
            "status": "created",
            "verified": True,
        })

        res2 = await tool.execute({"title": "DSA Practice", "start_time": "2026-09-12T19:00:00+05:30", "end_time": "2026-09-12T20:00:00+05:30"}, ctx)
        assert res2.success is True
        assert res2.data["status"] == "created"
        assert res2.data["event_id"] == "evt_new"
        assert res2.data["verified"] is True


@pytest.mark.asyncio
async def test_create_calendar_event_service_with_read_back(mock_session):
    """Verify GoogleCalendarService.create_event calls events.insert and then events.get to verify read-back."""
    from app.services.integrations.google_calendar import GoogleCalendarService

    service = GoogleCalendarService()
    service.get_valid_access_token = AsyncMock(return_value="mock_access_token")

    mock_insert_response = MagicMock()
    mock_insert_response.status_code = 200
    mock_insert_response.json.return_value = {
        "id": "google_evt_12345",
        "summary": "TARK API TEST",
        "htmlLink": "https://calendar.google.com/event?eid=12345",
        "status": "confirmed",
    }

    mock_get_response = MagicMock()
    mock_get_response.status_code = 200
    mock_get_response.json.return_value = {
        "id": "google_evt_12345",
        "summary": "TARK API TEST",
        "start": {"dateTime": "2026-09-12T19:00:00+05:30", "timeZone": "Asia/Kolkata"},
        "end": {"dateTime": "2026-09-12T19:30:00+05:30", "timeZone": "Asia/Kolkata"},
        "htmlLink": "https://calendar.google.com/event?eid=12345",
        "status": "confirmed",
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post, \
         patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_post.return_value = mock_insert_response
        mock_get.return_value = mock_get_response

        created = await service.create_event(
            user_id=USER_A_ID,
            session=mock_session,
            summary="TARK API TEST",
            start_time_str="2026-09-12T19:00:00+05:30",
            end_time_str="2026-09-12T19:30:00+05:30",
            timezone_str="Asia/Kolkata",
            calendar_id="primary",
        )

        assert created["id"] == "google_evt_12345"
        assert created["status"] == "created"
        assert created["verified"] is True
        assert created["summary"] == "TARK API TEST"
        mock_post.assert_called_once()
        mock_get.assert_called_once()



@pytest.mark.asyncio
async def test_user_isolation_calendar():
    """Verify User A's execution context only uses User A's tokens."""
    tool = GetCalendarEventsTool()
    session_a = AsyncMock()
    ctx_a = ToolExecutionContext(user_id=USER_A_ID, session=session_a)

    with patch("app.tools.builtins.calendar.GoogleCalendarService") as MockService:
        instance = MockService.return_value
        instance.list_events = AsyncMock(return_value=[])

        await tool.execute({"time_frame": "today"}, ctx_a)
        instance.list_events.assert_called_once()
        args, kwargs = instance.list_events.call_args
        assert kwargs["user_id"] == USER_A_ID


@pytest.mark.asyncio
async def test_tool_loop_orchestration_with_calendar(mock_session):
    """Verify tool loop triggers get_calendar_events and synthesizes final answer."""
    router = MagicMock(spec=ModelRouter)
    
    # Mock user integration query in DB
    mock_integ = UserIntegration(
        user_id=USER_A_ID,
        provider="google",
        service="calendar",
        is_active=True,
        scopes=["https://www.googleapis.com/auth/calendar.events.readonly"],
        encrypted_access_token="fake",
    )
    mock_scalars = MagicMock()
    mock_scalars.first.return_value = mock_integ
    mock_exec_res = MagicMock()
    mock_exec_res.scalars.return_value = mock_scalars
    mock_session.execute = AsyncMock(return_value=mock_exec_res)

    orchestrator = ToolCallOrchestrator(router=router)

    # Iteration 1: Model outputs tool call
    async def fake_stream_it1(*args, **kwargs):
        messages = kwargs.get("messages", [])
        # Check if this is iteration 1 or iteration 2
        is_iter2 = any(m.role == MessageRole.USER and "<tool_response" in (m.content or "") for m in messages)
        selection = ProviderSelection(provider=None, provider_name="groq", model="qwen/qwen3.8-27b")
        if not is_iter2:
            yield selection, ProviderStreamEvent(delta='<tool_call>{"name": "get_calendar_events", "arguments": {"time_frame": "tomorrow"}}</tool_call>')
        else:
            yield selection, ProviderStreamEvent(delta="Tomorrow you have Team Sync from 10:00 to 11:00 AM.")

    router.stream = fake_stream_it1

    with patch("app.tools.builtins.calendar.GoogleCalendarService") as MockService:
        instance = MockService.return_value
        instance.list_events = AsyncMock(return_value=[
            {"summary": "Team Sync", "start": "2026-09-12T10:00:00Z", "end": "2026-09-12T11:00:00Z"}
        ])

        messages = [
            NormalizedMessage(role=MessageRole.USER, content="What do I have on my calendar tomorrow?")
        ]
        ctx = ToolExecutionContext(user_id=USER_A_ID, session=mock_session)

        chunks = []
        async for chunk in orchestrator.run_tool_loop(
            messages=messages,
            mode=ConversationMode.NORMAL,
            provider="groq",
            model="qwen/qwen3.8-27b",
            context=ctx,
            is_disconnected=AsyncMock(return_value=False),
        ):
            chunks.append(chunk)

        combined = "".join(chunks)
        assert "tool_available" in combined
        assert "tool_started" in combined
        assert "get_calendar_events" in combined
        assert "Tomorrow you have Team Sync" in combined


@pytest.mark.asyncio
async def test_document_qa_does_not_call_calendar():
    """Verify regular non-calendar queries do not trigger calendar tools."""
    calls = parse_tool_calls("Based on Pan.pdf, the PAN number is ABCDE1234F.")
    assert len(calls) == 0


@pytest.mark.asyncio
async def test_calendar_zero_events_produces_empty_response(mock_session):
    """Test A: Google API returns [] -> structured response has event_count 0 and empty status."""
    tool = GetCalendarEventsTool()
    ctx = ToolExecutionContext(user_id=USER_A_ID, session=mock_session)

    with patch("app.tools.builtins.calendar.GoogleCalendarService") as MockService:
        instance = MockService.return_value
        instance.list_events = AsyncMock(return_value=[])

        res = await tool.execute({"time_frame": "this_week"}, ctx)
        assert res.success is True
        assert res.data["event_count"] == 0
        assert res.data["events"] == []
        assert res.data["status"] == "empty"
        assert res.data["source"] == "google_calendar"
        assert "Zero events found" in res.data["message"]


@pytest.mark.asyncio
async def test_calendar_two_real_events_only_returns_exact_data(mock_session):
    """Test B: Google API returns 2 real events -> only those 2 are in tool response."""
    tool = GetCalendarEventsTool()
    ctx = ToolExecutionContext(user_id=USER_A_ID, session=mock_session)

    real_events = [
        {"id": "ev_1", "summary": "System Architecture Review", "start": "2026-09-14T15:00:00Z", "end": "2026-09-14T16:00:00Z"},
        {"id": "ev_2", "summary": "Product Launch Planning", "start": "2026-09-15T18:00:00Z", "end": "2026-09-15T19:00:00Z"},
    ]
    with patch("app.tools.builtins.calendar.GoogleCalendarService") as MockService:
        instance = MockService.return_value
        instance.list_events = AsyncMock(return_value=real_events)

        res = await tool.execute({"time_frame": "this_week"}, ctx)
        assert res.success is True
        assert res.data["event_count"] == 2
        assert len(res.data["events"]) == 2
        assert res.data["events"][0]["summary"] == "System Architecture Review"
        assert res.data["events"][1]["summary"] == "Product Launch Planning"


@pytest.mark.asyncio
async def test_calendar_api_failure_controlled_error(mock_session):
    """Test C: Google API fails -> returns controlled error."""
    tool = GetCalendarEventsTool()
    ctx = ToolExecutionContext(user_id=USER_A_ID, session=mock_session)

    with patch("app.tools.builtins.calendar.GoogleCalendarService") as MockService:
        instance = MockService.return_value
        instance.list_events = AsyncMock(side_effect=RuntimeError("Google Calendar API connection timed out."))

        res = await tool.execute({"time_frame": "today"}, ctx)
        assert res.success is False
        assert "Failed to fetch calendar events from Google Calendar" in res.error


@pytest.mark.asyncio
async def test_calendar_this_week_date_range_verification(mock_session):
    """Test E: 'this_week' calculates 7-day query window."""
    tool = GetCalendarEventsTool()
    ctx = ToolExecutionContext(user_id=USER_A_ID, session=mock_session)

    with patch("app.tools.builtins.calendar.GoogleCalendarService") as MockService:
        instance = MockService.return_value
        instance.list_events = AsyncMock(return_value=[])

        res = await tool.execute({"time_frame": "this_week"}, ctx)
        assert res.success is True
        assert res.data["time_frame"] == "this_week"
        instance.list_events.assert_called_once()
        _, kwargs = instance.list_events.call_args
        time_min = kwargs["time_min"]
        time_max = kwargs["time_max"]
        diff = (time_max - time_min).total_seconds()
        assert diff >= 6 * 86400  # Approximately 7 days


@pytest.mark.asyncio
async def test_delete_calendar_event_by_title(mock_session):
    """Test deleting calendar event by title search."""
    from app.tools.builtins.calendar import DeleteCalendarEventTool
    tool = DeleteCalendarEventTool()
    ctx = ToolExecutionContext(user_id=USER_A_ID, session=mock_session)

    with patch("app.tools.builtins.calendar.GoogleCalendarService") as MockService:
        instance = MockService.return_value
        instance.list_events = AsyncMock(return_value=[
            {"id": "ev_test_123", "summary": "test event", "start": "2026-09-12T19:00:00Z"}
        ])
        instance.delete_event = AsyncMock(return_value=True)

        res = await tool.execute({"title": "test event"}, ctx)
        assert res.success is True
        assert res.data["status"] == "deleted"
        assert res.data["event_id"] == "ev_test_123"
        instance.delete_event.assert_called_once_with(
            user_id=USER_A_ID,
            session=mock_session,
            event_id="ev_test_123",
            calendar_id="primary",
        )


@pytest.mark.asyncio
async def test_delete_calendar_event_by_id(mock_session):
    """Test deleting calendar event directly by ID."""
    from app.tools.builtins.calendar import DeleteCalendarEventTool
    tool = DeleteCalendarEventTool()
    ctx = ToolExecutionContext(user_id=USER_A_ID, session=mock_session)

    with patch("app.tools.builtins.calendar.GoogleCalendarService") as MockService:
        instance = MockService.return_value
        instance.delete_event = AsyncMock(return_value=True)

        res = await tool.execute({"event_id": "direct_id_999"}, ctx)
        assert res.success is True
        assert res.data["status"] == "deleted"
        assert res.data["event_id"] == "direct_id_999"
        instance.delete_event.assert_called_once_with(
            user_id=USER_A_ID,
            session=mock_session,
            event_id="direct_id_999",
            calendar_id="primary",
        )

