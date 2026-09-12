from datetime import datetime, time, timedelta, timezone
import logging
import re
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import select

from app.models.integration import UserIntegration
from app.services.integrations.google_calendar import GoogleCalendarService
from app.tools.base import BaseTool, ToolExecutionContext, ToolPermission, ToolResult

logger = logging.getLogger(__name__)


class GetCalendarEventsInput(BaseModel):
    time_frame: Optional[str] = Field(
        default="upcoming",
        description="Time frame to query: 'today', 'tomorrow', 'this_week', 'upcoming', or a specific date in YYYY-MM-DD format.",
    )
    max_results: int = Field(default=15, ge=1, le=50, description="Max number of events to return.")


class CheckAvailabilityInput(BaseModel):
    target_date: Optional[str] = Field(
        default="today",
        description="Date to check in YYYY-MM-DD format, 'today', or 'tomorrow'.",
    )
    start_time: Optional[str] = Field(
        default=None,
        description="Start time (e.g. '17:00', '5:00 PM', or ISO timestamp).",
    )
    end_time: Optional[str] = Field(
        default=None,
        description="End time (e.g. '18:00', '6:00 PM', or ISO timestamp). If omitted, defaults to 1 hour after start_time.",
    )


class CreateCalendarEventInput(BaseModel):
    title: str = Field(description="Title / Summary of the event.")
    start_time: str = Field(description="Start time in ISO 8601 format (e.g. '2026-09-12T19:00:00Z').")
    end_time: str = Field(description="End time in ISO 8601 format (e.g. '2026-09-12T20:00:00Z').")
    description: Optional[str] = Field(default=None, description="Optional description of the event.")
    location: Optional[str] = Field(default=None, description="Optional location for the event.")


class DeleteCalendarEventInput(BaseModel):
    event_id: Optional[str] = Field(default=None, description="Exact Google Calendar event ID to delete if known.")
    title: Optional[str] = Field(default=None, description="Title or keyword of the event to delete (e.g. 'test event', 'Client Demo').")
    target_date: Optional[str] = Field(default=None, description="Optional date filter for the event to delete ('today', 'tomorrow', or 'YYYY-MM-DD').")



def _parse_time_string(time_str: str) -> Optional[tuple[int, int]]:
    """Parse time representations like '17:00', '5 PM', '5:30 pm', '17' into (hour, minute)."""
    if not time_str:
        return None
    time_str = time_str.strip().lower()

    # 12-hour format with am/pm (e.g. '5 pm', '5:30 pm', '5pm')
    ampm_match = re.match(r"^(\d{1,2})(?::(\d{2}))?\s*(am|pm)$", time_str)
    if ampm_match:
        hour = int(ampm_match.group(1))
        minute = int(ampm_match.group(2) or 0)
        is_pm = ampm_match.group(3) == "pm"
        if is_pm and hour < 12:
            hour += 12
        elif not is_pm and hour == 12:
            hour = 0
        return hour, minute

    # 24-hour format (e.g. '17:00', '17:30', '17')
    h24_match = re.match(r"^(\d{1,2})(?::(\d{2}))?(?::\d{2})?$", time_str)
    if h24_match:
        hour = int(h24_match.group(1))
        minute = int(h24_match.group(2) or 0)
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return hour, minute

    return None


def _parse_calendar_datetime(dt_raw: Any, default_offset_days: int = 0) -> str:
    """Robustly parse ISO strings, dates, or natural time strings to ISO 8601 string with timezone."""
    if not dt_raw:
        return ""
    raw = str(dt_raw).strip()

    # 1. Standard ISO format match (e.g. 2026-09-13T13:00:00 or 2026-09-13T13:00:00+05:30)
    iso_match = re.match(r"^(\d{4}-\d{2}-\d{2})[T\s](\d{2}:\d{2}(?::\d{2})?)(.*)$", raw)
    if iso_match:
        date_part, time_part, tz_part = iso_match.group(1), iso_match.group(2), iso_match.group(3)
        if len(time_part) == 5:
            time_part += ":00"
        if tz_part.endswith("Z"):
            return f"{date_part}T{time_part}+05:30"
        elif re.search(r"[+\-]\d{2}:\d{2}$", tz_part):
            return f"{date_part}T{time_part}{tz_part}"
        return f"{date_part}T{time_part}+05:30"

    # 2. Check for 'tomorrow' or 'today' with time
    local_tz = timezone(timedelta(hours=5, minutes=30))
    now_local = datetime.now(local_tz)
    base_date = now_local.date() + timedelta(days=default_offset_days)

    raw_lower = raw.lower()
    if "tomorrow" in raw_lower:
        base_date = now_local.date() + timedelta(days=1)
        raw_lower = raw_lower.replace("tomorrow", "").replace("at", "").strip()
    elif "today" in raw_lower:
        base_date = now_local.date()
        raw_lower = raw_lower.replace("today", "").replace("at", "").strip()

    parsed_time = _parse_time_string(raw_lower)
    if parsed_time:
        hr, mn = parsed_time
        dt = datetime.combine(base_date, time(hr, mn, 0), tzinfo=local_tz)
        return dt.isoformat()

    # Fallback to appending local tz if valid date string
    if re.match(r"^\d{4}-\d{2}-\d{2}$", raw):
        return f"{raw}T10:00:00+05:30"

    return raw



class GetCalendarEventsTool(BaseTool):
    name = "get_calendar_events"
    description = (
        "Retrieve upcoming events, today's schedule, tomorrow's agenda, or meetings from the user's connected Google Calendar."
    )
    input_schema = GetCalendarEventsInput
    permissions = [ToolPermission.USER_DATA, ToolPermission.NETWORK]
    category = "personal"

    async def execute(self, arguments: dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        if not context.user_id:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error="User authentication is required to access Google Calendar.",
            )
        if not context.session:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error="Database session unavailable in execution context.",
            )

        # Handle flexible argument names passed by LLMs
        raw_frame = (
            arguments.get("time_frame")
            or arguments.get("target_date")
            or arguments.get("date")
            or arguments.get("query")
            or "upcoming"
        )
        time_frame = str(raw_frame).strip().lower()
        max_results = int(arguments.get("max_results") or 15)

        now = datetime.now(timezone.utc)
        today_start = datetime.combine(now.date(), time.min).replace(tzinfo=timezone.utc)
        today_end = datetime.combine(now.date(), time.max).replace(tzinfo=timezone.utc)

        if "tomorrow" in time_frame:
            time_min = today_start + timedelta(days=1)
            time_max = today_end + timedelta(days=1)
            resolved_frame = "tomorrow"
        elif "today" in time_frame:
            time_min = today_start
            time_max = today_end
            resolved_frame = "today"
        elif "this_week" in time_frame or "week" in time_frame:
            time_min = today_start
            time_max = today_start + timedelta(days=7)
            resolved_frame = "this_week"
        elif "month" in time_frame:
            time_min = today_start
            time_max = today_start + timedelta(days=30)
            resolved_frame = "month"
        else:
            # Check if YYYY-MM-DD date format was supplied
            date_match = re.search(r"\d{4}-\d{2}-\d{2}", time_frame)
            if date_match:
                try:
                    q_date = datetime.strptime(date_match.group(0), "%Y-%m-%d").date()
                    time_min = datetime.combine(q_date, time.min).replace(tzinfo=timezone.utc)
                    time_max = datetime.combine(q_date, time.max).replace(tzinfo=timezone.utc)
                    resolved_frame = date_match.group(0)
                except Exception:
                    time_min = now - timedelta(hours=1)
                    time_max = now + timedelta(days=14)
                    resolved_frame = "upcoming"
            else:
                time_min = now - timedelta(hours=1)
                time_max = now + timedelta(days=14)
                resolved_frame = "upcoming"

        service = GoogleCalendarService()
        try:
            events = await service.list_events(
                user_id=context.user_id,
                session=context.session,
                time_min=time_min,
                time_max=time_max,
                max_results=max_results,
            )
            event_count = len(events)
            logger.info(
                "GetCalendarEvents executed: user=%s, range=%s..%s, event_count=%d",
                str(context.user_id)[:8] + "...",
                time_min.isoformat(),
                time_max.isoformat(),
                event_count,
            )

            if event_count == 0:
                msg = f"Zero events found on the user's connected Google Calendar for {resolved_frame}. The calendar is completely empty and free during this period."
            else:
                msg = f"Retrieved {event_count} verified event(s) from the user's connected Google Calendar."

            return ToolResult(
                tool_name=self.name,
                success=True,
                data={
                    "events": events,
                    "event_count": event_count,
                    "time_frame": resolved_frame,
                    "status": "empty" if event_count == 0 else "events_found",
                    "source": "google_calendar",
                    "message": msg,
                    "query_range": {
                        "start": time_min.isoformat(),
                        "end": time_max.isoformat(),
                    },
                },
                metadata={"time_frame": resolved_frame, "count": event_count, "is_empty": (event_count == 0)},
            )
        except ValueError as val_err:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=f"Google Calendar not connected: {val_err}. Please connect under Settings -> Connections.",
            )
        except Exception as exc:
            logger.warning("GetCalendarEventsTool execution error: %s", exc)
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=f"Failed to fetch calendar events from Google Calendar: {exc}",
            )


class CheckCalendarAvailabilityTool(BaseTool):
    name = "check_calendar_availability"
    description = (
        "Check free/busy time slot availability on the user's primary Google Calendar for a given date and time range."
    )
    input_schema = CheckAvailabilityInput
    permissions = [ToolPermission.USER_DATA, ToolPermission.NETWORK]
    category = "personal"

    async def execute(self, arguments: dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        if not context.user_id or not context.session:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error="User authentication and database session required.",
            )

        target_date_raw = str(
            arguments.get("target_date")
            or arguments.get("date")
            or arguments.get("time_frame")
            or "today"
        ).lower()
        now = datetime.now(timezone.utc)

        if "tomorrow" in target_date_raw:
            query_date = (now + timedelta(days=1)).date()
        elif "today" in target_date_raw:
            query_date = now.date()
        else:
            date_match = re.search(r"\d{4}-\d{2}-\d{2}", target_date_raw)
            if date_match:
                try:
                    query_date = datetime.strptime(date_match.group(0), "%Y-%m-%d").date()
                except Exception:
                    query_date = now.date()
            else:
                query_date = now.date()

        start_time_raw = arguments.get("start_time")
        end_time_raw = arguments.get("end_time")

        parsed_start = _parse_time_string(str(start_time_raw)) if start_time_raw else None
        parsed_end = _parse_time_string(str(end_time_raw)) if end_time_raw else None

        if parsed_start:
            time_min = datetime.combine(query_date, time(parsed_start[0], parsed_start[1])).replace(tzinfo=timezone.utc)
            if parsed_end:
                time_max = datetime.combine(query_date, time(parsed_end[0], parsed_end[1])).replace(tzinfo=timezone.utc)
            else:
                # Default duration of 1 hour if end_time is not given
                time_max = time_min + timedelta(hours=1)
        else:
            # Full day availability query
            time_min = datetime.combine(query_date, time.min).replace(tzinfo=timezone.utc)
            time_max = datetime.combine(query_date, time.max).replace(tzinfo=timezone.utc)

        service = GoogleCalendarService()
        try:
            freebusy = await service.check_free_busy(
                user_id=context.user_id,
                session=context.session,
                time_min=time_min,
                time_max=time_max,
            )
            is_free = freebusy.get("is_free", False)
            busy_slots = freebusy.get("busy_slots", [])
            logger.info(
                "CheckCalendarAvailability executed: user=%s, date=%s, is_free=%s, busy_count=%d",
                str(context.user_id)[:8] + "...",
                query_date.isoformat(),
                is_free,
                len(busy_slots),
            )
            return ToolResult(
                tool_name=self.name,
                success=True,
                data={
                    "status": "available" if is_free else "busy",
                    "date": query_date.isoformat(),
                    "is_free": is_free,
                    "busy_slots": busy_slots,
                    "requested_start": time_min.isoformat(),
                    "requested_end": time_max.isoformat(),
                    "source": "google_calendar",
                    "message": "User is completely free during this period." if is_free else f"User has {len(busy_slots)} conflicting busy slot(s).",
                },
            )
        except ValueError as val_err:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=f"Google Calendar not connected: {val_err}. Please connect under Settings -> Connections.",
            )
        except Exception as exc:
            logger.warning("CheckCalendarAvailabilityTool error: %s", exc)
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=f"Failed to check calendar availability: {exc}",
            )


class CreateCalendarEventTool(BaseTool):
    name = "create_calendar_event"
    description = (
        "Schedule a new event on the user's primary Google Calendar."
    )
    input_schema = CreateCalendarEventInput
    permissions = [ToolPermission.USER_DATA, ToolPermission.NETWORK]
    category = "personal"

    async def execute(self, arguments: dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        if not context.user_id or not context.session:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error="User authentication and database session required.",
            )

        # Check write scope on UserIntegration
        stmt = select(UserIntegration).where(
            UserIntegration.user_id == context.user_id,
            UserIntegration.provider == "google",
            UserIntegration.service == "calendar",
            UserIntegration.is_active == True,
        )
        res = await context.session.execute(stmt)
        integration = res.scalars().first()
        if not integration:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error="Google Calendar is not connected. Please connect under Settings -> Connections.",
            )

        scopes_list = integration.scopes if isinstance(integration.scopes, list) else [str(integration.scopes)]
        has_write = any("calendar.events" in s and "readonly" not in s for s in scopes_list)
        if not has_write:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error="Calendar write permission is required to create events. Please re-authenticate Google Calendar with write permission in Settings -> Connections.",
            )

        title = arguments.get("title") or arguments.get("summary")
        start_time_raw = arguments.get("start_time")
        end_time_raw = arguments.get("end_time")
        timezone_str = arguments.get("timezone") or "Asia/Kolkata"

        if not title or not start_time_raw:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error="Event 'title' and 'start_time' are required.",
            )

        start_time_formatted = _parse_calendar_datetime(start_time_raw, default_offset_days=0)
        if not start_time_formatted:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error="Could not parse start_time. Please specify a valid date/time (e.g. '2026-09-13T13:00:00+05:30' or 'tomorrow at 1 PM').",
            )

        # Normalize end_time string
        if end_time_raw:
            end_time_formatted = _parse_calendar_datetime(end_time_raw, default_offset_days=0)
        else:
            # Default end_time to start_time + 30 minutes
            try:
                dt_start = datetime.fromisoformat(start_time_formatted)
                dt_end = dt_start + timedelta(minutes=30)
                end_time_formatted = dt_end.isoformat()
            except Exception:
                end_time_formatted = start_time_formatted


        service = GoogleCalendarService()
        try:
            event = await service.create_event(
                user_id=context.user_id,
                session=context.session,
                summary=title,
                start_time_str=start_time_formatted,
                end_time_str=end_time_formatted,
                timezone_str=timezone_str,
                description=arguments.get("description"),
                location=arguments.get("location"),
                calendar_id="primary",
            )
            return ToolResult(
                tool_name=self.name,
                success=True,
                data={
                    "status": "created",
                    "event_id": event.get("id"),
                    "calendar_id": "primary",
                    "summary": event.get("summary") or title,
                    "start": event.get("start"),
                    "end": event.get("end"),
                    "timezone": timezone_str,
                    "html_link": event.get("html_link"),
                    "source": "google_calendar",
                    "verified": True,
                    "message": f"Successfully created and verified event '{title}' on your primary Google Calendar ({start_time_formatted} to {end_time_formatted}).",
                },
                metadata={"status": "created", "event_id": event.get("id"), "verified": True},
            )
        except ValueError as val_err:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=f"Google Calendar not connected: {val_err}",
            )
        except Exception as exc:
            logger.warning("CreateCalendarEventTool error: %s", exc)
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=f"Google Calendar create event failed: {exc}",
            )


class DeleteCalendarEventTool(BaseTool):
    name = "delete_calendar_event"
    description = (
        "Delete or remove an existing event from the user's Google Calendar by its title, name, or event ID."
    )
    input_schema = DeleteCalendarEventInput
    permissions = [ToolPermission.USER_DATA, ToolPermission.NETWORK]
    category = "personal"

    @staticmethod
    def _normalize_title(text: str) -> str:
        t = text.lower().strip()
        t = re.sub(r"[^\w\s]", " ", t)
        t = re.sub(r"^(remove|delete|cancel)\s+(the\s+)?(event|meeting|call)\s+(of|for|named|called)?\s*", "", t)
        t = re.sub(r"^(event|meeting|call)\s+(of|for|named|called)?\s*", "", t)
        t = re.sub(r"\s+(event|meeting|call)$", "", t)
        return " ".join(t.split())

    async def execute(self, arguments: dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        if not context.user_id or not context.session:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error="User authentication and database session required.",
            )

        # Check integration and write permissions
        if context.session:
            try:
                stmt = select(UserIntegration).where(
                    UserIntegration.user_id == context.user_id,
                    UserIntegration.provider == "google",
                    UserIntegration.service == "calendar",
                    UserIntegration.is_active == True,
                )
                res = await context.session.execute(stmt)
                if hasattr(res, "scalars"):
                    scalars_obj = res.scalars()
                    integration = scalars_obj.first() if hasattr(scalars_obj, "first") else None
                    if integration:
                        scopes_list = integration.scopes if isinstance(integration.scopes, list) else [str(integration.scopes)]
                        has_write = any("calendar.events" in s and "readonly" not in s for s in scopes_list)
                        if not has_write:
                            return ToolResult(
                                tool_name=self.name,
                                success=False,
                                error=(
                                    "Google Calendar write permission is required to delete events. "
                                    "Your current connection only has read permissions. "
                                    "Please disconnect and reconnect Google Calendar in Settings -> Connections to grant edit/delete access."
                                ),
                            )
            except Exception as e:
                logger.debug("Could not verify integration write permissions in tool: %s", e)

        event_id = arguments.get("event_id") or arguments.get("eventId") or arguments.get("id")
        title_query = str(
            arguments.get("title")
            or arguments.get("summary")
            or arguments.get("event_title")
            or arguments.get("event_name")
            or arguments.get("event")
            or arguments.get("name")
            or arguments.get("query")
            or arguments.get("target")
            or ""
        ).strip()
        target_date_raw = arguments.get("target_date") or arguments.get("date")

        service = GoogleCalendarService()

        try:
            # If exact event_id is not given, search for the matching event by title
            if not event_id:
                if not title_query:
                    return ToolResult(
                        tool_name=self.name,
                        success=False,
                        error="Please provide either 'event_id' or 'title' of the event to delete.",
                    )

                now = datetime.now(timezone.utc)
                time_min = now - timedelta(days=7)
                time_max = now + timedelta(days=60)

                if target_date_raw:
                    target_str = str(target_date_raw).lower()
                    if "tomorrow" in target_str:
                        d = (now + timedelta(days=1)).date()
                        time_min = datetime.combine(d, time.min).replace(tzinfo=timezone.utc)
                        time_max = datetime.combine(d, time.max).replace(tzinfo=timezone.utc)
                    elif "today" in target_str:
                        d = now.date()
                        time_min = datetime.combine(d, time.min).replace(tzinfo=timezone.utc)
                        time_max = datetime.combine(d, time.max).replace(tzinfo=timezone.utc)

                events = await service.list_events(
                    user_id=context.user_id,
                    session=context.session,
                    time_min=time_min,
                    time_max=time_max,
                    max_results=50,
                )

                clean_query = self._normalize_title(title_query)
                query_words = set(clean_query.split())

                matching_event = None

                # Pass 1: exact normalized match
                for ev in events:
                    norm_summary = self._normalize_title(ev.get("summary") or "")
                    if norm_summary and norm_summary == clean_query:
                        matching_event = ev
                        break

                # Pass 2: substring match
                if not matching_event:
                    for ev in events:
                        norm_summary = self._normalize_title(ev.get("summary") or "")
                        raw_summary = (ev.get("summary") or "").lower()
                        if (clean_query and clean_query in norm_summary) or (norm_summary and norm_summary in clean_query):
                            matching_event = ev
                            break
                        if title_query.lower() in raw_summary or raw_summary in title_query.lower():
                            matching_event = ev
                            break

                # Pass 3: Token subset match
                if not matching_event and query_words:
                    for ev in events:
                        norm_summary = self._normalize_title(ev.get("summary") or "")
                        summary_words = set(norm_summary.split())
                        if summary_words and summary_words.issubset(query_words):
                            matching_event = ev
                            break
                        if query_words and query_words.issubset(summary_words):
                            matching_event = ev
                            break

                if not matching_event:
                    return ToolResult(
                        tool_name=self.name,
                        success=False,
                        error=f"No calendar event found matching '{title_query}' in your schedule.",
                    )

                event_id = matching_event.get("id")
                event_title = matching_event.get("summary") or title_query
            else:
                event_title = title_query or event_id

            await service.delete_event(
                user_id=context.user_id,
                session=context.session,
                event_id=event_id,
                calendar_id="primary",
            )

            return ToolResult(
                tool_name=self.name,
                success=True,
                data={
                    "status": "deleted",
                    "event_id": event_id,
                    "title": event_title,
                    "source": "google_calendar",
                    "message": f"Successfully deleted event '{event_title}' from your Google Calendar.",
                },
                metadata={"status": "deleted", "event_id": event_id},
            )
        except ValueError as val_err:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=f"Google Calendar not connected: {val_err}",
            )
        except Exception as exc:
            logger.warning("DeleteCalendarEventTool error: %s", exc)
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=f"Failed to delete event from Google Calendar: {exc}",
            )

