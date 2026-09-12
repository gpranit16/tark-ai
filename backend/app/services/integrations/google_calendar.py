from datetime import datetime, timedelta, timezone
import logging
from typing import Any, Dict, List, Optional
import urllib.parse
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import (
    create_oauth_state,
    decrypt_secret,
    encrypt_secret,
    verify_oauth_state,
)
from app.models.integration import UserIntegration

logger = logging.getLogger(__name__)

# Minimum required Google Calendar scopes
DEFAULT_SCOPES = [
    "https://www.googleapis.com/auth/calendar.events.readonly",
    "https://www.googleapis.com/auth/calendar.freebusy",
    "https://www.googleapis.com/auth/userinfo.email",
]

WRITE_SCOPE = "https://www.googleapis.com/auth/calendar.events"


class GoogleCalendarService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.client_id = self.settings.google_client_id
        self.client_secret = self.settings.google_client_secret
        self.redirect_uri = self.settings.google_redirect_uri

    def get_authorization_url(self, user_id: UUID, allow_write: bool = True) -> str:
        """Generate Google OAuth 2.0 consent URL with CSRF state protection."""
        if not self.client_id or not self.client_secret:
            raise ValueError("Google OAuth credentials (GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET) are not configured.")

        scopes = list(DEFAULT_SCOPES)
        if allow_write:
            scopes.append(WRITE_SCOPE)

        state = create_oauth_state(user_id=user_id, provider="google", service="calendar")

        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": " ".join(scopes),
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
            "include_granted_scopes": "true",
        }
        return f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(params)}"

    async def handle_oauth_callback(self, code: str, state: str, session: AsyncSession) -> UserIntegration:
        """Exchange authorization code for tokens, encrypt at rest, and upsert UserIntegration."""
        if not self.client_id or not self.client_secret:
            raise ValueError("Google OAuth credentials are not configured.")

        user_id = verify_oauth_state(state, expected_provider="google", expected_service="calendar")

        # 1. Exchange code with Google Token Endpoint
        token_url = "https://oauth2.googleapis.com/token"
        payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": self.redirect_uri,
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(token_url, data=payload)
            if resp.status_code != 200:
                logger.error("Failed Google token exchange: status %d", resp.status_code)
                raise RuntimeError("Failed to exchange authorization code with Google.")

            tokens = resp.json()

        access_token = tokens.get("access_token")
        refresh_token = tokens.get("refresh_token")
        expires_in = tokens.get("expires_in", 3600)
        scope_str = tokens.get("scope", "")
        granted_scopes = scope_str.split(" ") if scope_str else DEFAULT_SCOPES

        if not access_token:
            raise RuntimeError("No access token returned from Google OAuth.")

        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

        # 2. Fetch User Profile Email from Google
        account_email: Optional[str] = None
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                u_resp = await client.get(
                    "https://www.googleapis.com/oauth2/v2/userinfo",
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                if u_resp.status_code == 200:
                    account_email = u_resp.json().get("email")
        except Exception as e:
            logger.warning("Could not fetch user email during Google OAuth: %s", e)

        # 3. Encrypt sensitive tokens at rest
        enc_access = encrypt_secret(access_token)
        enc_refresh = encrypt_secret(refresh_token) if refresh_token else None

        # 4. Upsert UserIntegration
        stmt = select(UserIntegration).where(
            UserIntegration.user_id == user_id,
            UserIntegration.provider == "google",
            UserIntegration.service == "calendar",
        )
        result = await session.execute(stmt)
        integration = result.scalar_one_or_none()

        if integration:
            integration.encrypted_access_token = enc_access
            if enc_refresh:
                integration.encrypted_refresh_token = enc_refresh
            integration.expires_at = expires_at
            integration.scopes = granted_scopes
            integration.account_email = account_email or integration.account_email
            integration.is_active = True
        else:
            integration = UserIntegration(
                user_id=user_id,
                provider="google",
                service="calendar",
                encrypted_access_token=enc_access,
                encrypted_refresh_token=enc_refresh,
                expires_at=expires_at,
                scopes=granted_scopes,
                account_email=account_email,
                is_active=True,
            )
            session.add(integration)

        await session.commit()
        await session.refresh(integration)
        return integration

    async def get_valid_access_token(self, user_id: UUID, session: AsyncSession) -> str:
        """Retrieve valid decrypted access token, automatically refreshing if expired."""
        stmt = select(UserIntegration).where(
            UserIntegration.user_id == user_id,
            UserIntegration.provider == "google",
            UserIntegration.service == "calendar",
            UserIntegration.is_active == True,
        )
        result = await session.execute(stmt)
        integration = result.scalar_one_or_none()

        if not integration:
            raise ValueError("Google Calendar is not connected for this user.")

        now = datetime.now(timezone.utc)
        # Check if token is expired or expiring within 5 minutes
        if integration.expires_at and (integration.expires_at - now).total_seconds() < 300:
            if not integration.encrypted_refresh_token:
                raise ValueError("Google access token expired and no refresh token is stored.")

            refresh_token = decrypt_secret(integration.encrypted_refresh_token)
            new_tokens = await self._refresh_google_token(refresh_token)

            new_access_token = new_tokens["access_token"]
            expires_in = new_tokens.get("expires_in", 3600)

            integration.encrypted_access_token = encrypt_secret(new_access_token)
            integration.expires_at = now + timedelta(seconds=expires_in)
            await session.commit()
            return new_access_token

        return decrypt_secret(integration.encrypted_access_token)

    async def _refresh_google_token(self, refresh_token: str) -> Dict[str, Any]:
        """Perform token refresh with Google token endpoint."""
        token_url = "https://oauth2.googleapis.com/token"
        payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(token_url, data=payload)
            if resp.status_code != 200:
                logger.error("Failed to refresh Google OAuth token: status %d", resp.status_code)
                raise RuntimeError("Failed to refresh Google Calendar token. Connection may have been revoked.")
            return resp.json()

    async def get_status(self, user_id: UUID, session: AsyncSession) -> Dict[str, Any]:
        """Check connection status for user."""
        stmt = select(UserIntegration).where(
            UserIntegration.user_id == user_id,
            UserIntegration.provider == "google",
            UserIntegration.service == "calendar",
            UserIntegration.is_active == True,
        )
        result = await session.execute(stmt)
        integration = result.scalar_one_or_none()

        if not integration:
            return {
                "connected": False,
                "is_connected": False,
                "provider": "google",
                "service": "calendar",
                "account_email": None,
                "scopes": [],
                "expires_at": None,
            }

        return {
            "connected": True,
            "is_connected": True,
            "provider": "google",
            "service": "calendar",
            "account_email": integration.account_email,
            "scopes": integration.scopes or [],
            "expires_at": integration.expires_at.isoformat() if integration.expires_at else None,
            "created_at": integration.created_at.isoformat() if integration.created_at else None,
        }

    async def disconnect(self, user_id: UUID, session: AsyncSession) -> bool:
        """Disconnect and revoke Google Calendar connection for user."""
        stmt = select(UserIntegration).where(
            UserIntegration.user_id == user_id,
            UserIntegration.provider == "google",
            UserIntegration.service == "calendar",
        )
        result = await session.execute(stmt)
        integration = result.scalar_one_or_none()

        if not integration:
            return False

        # Attempt to revoke token at Google
        try:
            if integration.encrypted_access_token:
                token = decrypt_secret(integration.encrypted_access_token)
                async with httpx.AsyncClient(timeout=5.0) as client:
                    await client.post("https://oauth2.googleapis.com/revoke", params={"token": token})
        except Exception as e:
            logger.warning("Could not revoke token with Google during disconnect: %s", e)

        await session.delete(integration)
        await session.commit()
        return True

    async def list_events(
        self,
        user_id: UUID,
        session: AsyncSession,
        time_min: Optional[datetime] = None,
        time_max: Optional[datetime] = None,
        max_results: int = 20,
    ) -> List[Dict[str, Any]]:
        """List events from user's primary calendar."""
        token = await self.get_valid_access_token(user_id, session)

        now = datetime.now(timezone.utc)
        if time_min is None:
            time_min = now - timedelta(hours=1)
        if time_max is None:
            time_max = now + timedelta(days=7)

        params: Dict[str, Any] = {
            "timeMin": time_min.isoformat(),
            "timeMax": time_max.isoformat(),
            "singleEvents": "true",
            "orderBy": "startTime",
            "maxResults": min(max_results, 50),
        }

        url = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
        headers = {"Authorization": f"Bearer {token}"}

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, headers=headers, params=params)
            if resp.status_code == 401 or resp.status_code == 403:
                raise RuntimeError("Google Calendar permission error or token expired.")
            if resp.status_code != 200:
                raise RuntimeError(f"Google Calendar API returned status {resp.status_code}")

            data = resp.json()
            items = data.get("items", [])

            events = []
            for item in items:
                start_obj = item.get("start", {})
                end_obj = item.get("end", {})
                events.append({
                    "id": item.get("id"),
                    "summary": item.get("summary", "(No Title)"),
                    "description": item.get("description", ""),
                    "start": start_obj.get("dateTime") or start_obj.get("date"),
                    "end": end_obj.get("dateTime") or end_obj.get("date"),
                    "location": item.get("location", ""),
                    "html_link": item.get("htmlLink", ""),
                    "status": item.get("status", "confirmed"),
                })
            return events

    async def check_free_busy(
        self,
        user_id: UUID,
        session: AsyncSession,
        time_min: datetime,
        time_max: datetime,
    ) -> Dict[str, Any]:
        """Query free/busy intervals for user's primary calendar."""
        token = await self.get_valid_access_token(user_id, session)

        url = "https://www.googleapis.com/calendar/v3/freeBusy"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        payload = {
            "timeMin": time_min.isoformat(),
            "timeMax": time_max.isoformat(),
            "items": [{"id": "primary"}],
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code != 200:
                raise RuntimeError(f"Google FreeBusy API failed with status {resp.status_code}")

            data = resp.json()
            calendars = data.get("calendars", {})
            primary_cal = calendars.get("primary", {})
            busy_list = primary_cal.get("busy", [])

            return {
                "time_min": time_min.isoformat(),
                "time_max": time_max.isoformat(),
                "busy_slots": busy_list,
                "is_free": len(busy_list) == 0,
            }

    async def get_event(
        self,
        user_id: UUID,
        session: AsyncSession,
        event_id: str,
        calendar_id: str = "primary",
    ) -> Dict[str, Any]:
        """Fetch a specific event by ID from Google Calendar to verify persistence."""
        token = await self.get_valid_access_token(user_id, session)

        url = f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events/{event_id}"
        headers = {"Authorization": f"Bearer {token}"}

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                raise RuntimeError(f"Failed to fetch event '{event_id}': status {resp.status_code}")

            item = resp.json()
            start_obj = item.get("start", {})
            end_obj = item.get("end", {})
            return {
                "id": item.get("id"),
                "summary": item.get("summary"),
                "description": item.get("description", ""),
                "start": start_obj.get("dateTime") or start_obj.get("date"),
                "end": end_obj.get("dateTime") or end_obj.get("date"),
                "timeZone": start_obj.get("timeZone"),
                "html_link": item.get("htmlLink"),
                "status": item.get("status"),
            }

    async def create_event(
        self,
        user_id: UUID,
        session: AsyncSession,
        summary: str,
        start_time_str: str,
        end_time_str: str,
        timezone_str: Optional[str] = None,
        description: Optional[str] = None,
        location: Optional[str] = None,
        calendar_id: str = "primary",
    ) -> Dict[str, Any]:
        """Create a new event on user's calendar with immediate read-back verification."""
        token = await self.get_valid_access_token(user_id, session)

        url = f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        start_payload: Dict[str, Any] = {"dateTime": start_time_str}
        end_payload: Dict[str, Any] = {"dateTime": end_time_str}
        if timezone_str:
            start_payload["timeZone"] = timezone_str
            end_payload["timeZone"] = timezone_str

        payload = {
            "summary": summary,
            "description": description or "",
            "location": location or "",
            "start": start_payload,
            "end": end_payload,
        }

        logger.info(
            "Creating Google Calendar event on %s: summary='%s', start=%s, timezone=%s",
            calendar_id,
            summary,
            start_time_str,
            timezone_str,
        )

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code not in (200, 201):
                err_body = resp.text
                logger.error("Google Calendar create event error: %d %s", resp.status_code, err_body)
                raise RuntimeError(f"Google Calendar API create event failed (status {resp.status_code}): {err_body}")

            created_item = resp.json()
            event_id = created_item.get("id")
            if not event_id:
                raise RuntimeError("Google Calendar API did not return a valid event ID.")

        # Immediate Read-Back Verification
        logger.info("Performing immediate read-back verification for event ID: %s", event_id)
        verified_event = await self.get_event(user_id, session, event_id, calendar_id=calendar_id)
        if not verified_event or verified_event.get("id") != event_id:
            raise RuntimeError(f"Event read-back verification failed for event ID '{event_id}'.")

        logger.info("Event successfully created and verified on Google Calendar: ID=%s", event_id)
        return {
            "id": event_id,
            "calendar_id": calendar_id,
            "summary": verified_event.get("summary") or summary,
            "start": verified_event.get("start"),
            "end": verified_event.get("end"),
            "timezone": timezone_str or verified_event.get("timeZone"),
            "html_link": verified_event.get("html_link") or created_item.get("htmlLink"),
            "status": "created",
            "verified": True,
        }

    async def delete_event(
        self,
        user_id: UUID,
        session: AsyncSession,
        event_id: str,
        calendar_id: str = "primary",
    ) -> bool:
        """Delete an event from the user's Google Calendar."""
        token = await self.get_valid_access_token(user_id, session)
        url = f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events/{event_id}"
        headers = {"Authorization": f"Bearer {token}"}

        logger.info("Deleting Google Calendar event: ID=%s on calendar=%s", event_id, calendar_id)

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.delete(url, headers=headers)
            if resp.status_code in (200, 204):
                logger.info("Google Calendar event %s deleted successfully.", event_id)
                return True
            elif resp.status_code == 404:
                logger.warning("Google Calendar event %s was already deleted or not found.", event_id)
                return True
            elif resp.status_code == 403:
                err_body = resp.text
                logger.error("Google Calendar delete event 403 Forbidden: %s", err_body)
                raise RuntimeError(
                    "Google Calendar returned 403 Forbidden: Insufficient permissions. "
                    "Your Google account was connected with read-only access. "
                    "Please disconnect and reconnect Google Calendar in Settings -> Connections to grant edit/delete permissions."
                )
            elif resp.status_code == 401:
                logger.error("Google Calendar delete event 401 Unauthorized: token expired or invalid.")
                raise RuntimeError("Google Calendar authorization token expired or invalid. Please re-authenticate.")
            else:
                err_body = resp.text
                logger.error("Google Calendar delete event error: %d %s", resp.status_code, err_body)
                raise RuntimeError(f"Google Calendar API delete event failed (status {resp.status_code}): {err_body}")

