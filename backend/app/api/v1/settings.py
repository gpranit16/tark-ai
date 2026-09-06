"""Settings API router for user configuration and system status."""
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth_deps import get_optional_current_user
from app.db.session import get_db_session
from app.models.conversation import User
from app.schemas.settings import (
    SettingsEnvelope,
    UserSettingsRead,
    UserSettingsUpdate,
)
from app.services.settings import DEFAULT_USER_ID, settings_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=SettingsEnvelope)
async def get_settings(
    user_id: UUID | None = Query(default=None, description="Optional user ID for scoping settings"),
    current_user: User | None = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> SettingsEnvelope:
    """Get full user settings, model routing info, provider health, storage metrics, and tool preferences."""
    effective_user_id = current_user.id if current_user else (user_id or DEFAULT_USER_ID)
    return await settings_service.get_settings_envelope(session, effective_user_id)


@router.patch("", response_model=SettingsEnvelope)
async def update_settings(
    payload: UserSettingsUpdate,
    user_id: UUID | None = Query(default=None, description="Optional user ID for scoping settings"),
    current_user: User | None = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> SettingsEnvelope:
    """Update user preferences and return the refreshed settings envelope."""
    effective_user_id = current_user.id if current_user else (user_id or DEFAULT_USER_ID)
    await settings_service.update_user_settings(session, effective_user_id, payload)
    return await settings_service.get_settings_envelope(session, effective_user_id)


@router.post("/reset", response_model=SettingsEnvelope)
async def reset_settings(
    user_id: UUID | None = Query(default=None, description="Optional user ID for scoping settings"),
    current_user: User | None = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> SettingsEnvelope:
    """Reset user preferences to factory defaults without deleting chats, files, or memories."""
    effective_user_id = current_user.id if current_user else (user_id or DEFAULT_USER_ID)
    await settings_service.reset_user_settings(session, effective_user_id)
    return await settings_service.get_settings_envelope(session, effective_user_id)
