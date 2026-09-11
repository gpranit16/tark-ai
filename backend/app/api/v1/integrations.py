from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth_deps import get_current_user
from app.core.config import get_settings
from app.db.session import get_db_session
from app.models.conversation import User
from app.services.integrations.google_calendar import GoogleCalendarService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations", tags=["integrations"])


class FreeBusyRequest(BaseModel):
    time_min: datetime
    time_max: datetime


class CreateEventRequest(BaseModel):
    summary: str = Field(min_length=1, max_length=255)
    start_time: datetime
    end_time: datetime
    description: Optional[str] = None
    location: Optional[str] = None


@router.get("/google/calendar/authorize")
async def authorize_google_calendar(
    allow_write: bool = Query(default=True),
    current_user: User = Depends(get_current_user),
) -> Dict[str, str]:
    """Generate Google OAuth authorization URL for the authenticated user."""
    service = GoogleCalendarService()
    try:
        auth_url = service.get_authorization_url(user_id=current_user.id, allow_write=allow_write)
        return {"authorization_url": auth_url}
    except ValueError as val_err:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(val_err))


@router.get("/google/calendar/callback")
async def google_calendar_callback(
    code: Optional[str] = Query(default=None),
    state: Optional[str] = Query(default=None),
    error: Optional[str] = Query(default=None),
    session: AsyncSession = Depends(get_db_session),
):
    """Google OAuth callback handler. Exchanges code for tokens and redirects to frontend."""
    settings = get_settings()
    frontend_base = settings.frontend_url.rstrip("/") if settings.frontend_url else "http://localhost:5173"
    redirect_target = f"{frontend_base}/settings?tab=connections"

    if error or not code or not state:
        logger.warning("Google OAuth callback error: %s", error or "Missing code or state")
        return RedirectResponse(url=f"{redirect_target}&error=oauth_denied", status_code=302)

    service = GoogleCalendarService()
    try:
        await service.handle_oauth_callback(code=code, state=state, session=session)
        return RedirectResponse(url=f"{redirect_target}&status=google_calendar_connected", status_code=302)
    except Exception as exc:
        logger.error("Failed to process Google OAuth callback: %s", exc)
        return RedirectResponse(url=f"{redirect_target}&error=oauth_exchange_failed", status_code=302)


@router.get("/google/calendar/status")
async def get_google_calendar_status(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Get Google Calendar connection status for the current user."""
    service = GoogleCalendarService()
    return await service.get_status(user_id=current_user.id, session=session)


@router.post("/google/calendar/disconnect")
async def disconnect_google_calendar(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Disconnect Google Calendar integration for the current user."""
    service = GoogleCalendarService()
    success = await service.disconnect(user_id=current_user.id, session=session)
    return {"success": success, "message": "Google Calendar disconnected successfully."}


@router.get("/google/calendar/events")
async def get_upcoming_events(
    time_min: Optional[datetime] = Query(default=None),
    time_max: Optional[datetime] = Query(default=None),
    max_results: int = Query(default=20, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Fetch calendar events for the authenticated user."""
    service = GoogleCalendarService()
    try:
        events = await service.list_events(
            user_id=current_user.id,
            session=session,
            time_min=time_min,
            time_max=time_max,
            max_results=max_results,
        )
        return {"events": events, "count": len(events)}
    except ValueError as val_err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(val_err))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.post("/google/calendar/freebusy")
async def check_free_busy_slots(
    payload: FreeBusyRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Check availability / free-busy intervals on user's primary calendar."""
    service = GoogleCalendarService()
    try:
        result = await service.check_free_busy(
            user_id=current_user.id,
            session=session,
            time_min=payload.time_min,
            time_max=payload.time_max,
        )
        return result
    except ValueError as val_err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(val_err))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.post("/google/calendar/events")
async def create_calendar_event(
    payload: CreateEventRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Create a new event on user's primary Google Calendar."""
    if payload.end_time <= payload.start_time:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="End time must be after start time.")

    service = GoogleCalendarService()
    try:
        event = await service.create_event(
            user_id=current_user.id,
            session=session,
            summary=payload.summary,
            start_time=payload.start_time,
            end_time=payload.end_time,
            description=payload.description,
            location=payload.location,
        )
        return {"event": event, "success": True}
    except ValueError as val_err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(val_err))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


# =============================================================================
# GITHUB MCP INTEGRATION ENDPOINTS
# =============================================================================

class SaveGitHubTokenRequest(BaseModel):
    token: str = Field(min_length=1, max_length=255)


@router.get("/github/status")
async def get_github_integration_status(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Check GitHub MCP integration status for the authenticated user."""
    from app.services.integrations.github import get_github_service

    service = get_github_service()
    return await service.get_status(user_id=current_user.id, session=session)


@router.post("/github/token")
async def save_github_token(
    payload: SaveGitHubTokenRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Validate and securely save personal access token for user."""
    from app.services.integrations.github import get_github_service

    service = get_github_service()
    try:
        res = await service.save_user_token(
            user_id=current_user.id,
            token=payload.token,
            session=session,
        )
        return res
    except Exception as exc:
        logger.error("Failed to save GitHub token: %s", exc)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/github/disconnect")
async def disconnect_github_integration(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Disconnect user-specific GitHub integration."""
    from app.services.integrations.github import get_github_service

    service = get_github_service()
    success = await service.disconnect_user(user_id=current_user.id, session=session)
    return {"success": success, "message": "GitHub connection removed."}
