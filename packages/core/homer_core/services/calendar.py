import json
from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import delete
from sqlmodel import Session, select

from homer_core.db.models import CalendarEventCache, User, as_utc
from homer_core.mcp.manager import McpManager
from homer_core.services.rules import ClientRules

log = structlog.get_logger(__name__)


def parse_time(value: str, timezone: str = "UTC") -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo(timezone))
    return parsed.astimezone(UTC)


def normalise_events(result: Any) -> list[dict[str, Any]]:
    if isinstance(result, dict):
        events = result.get("events")
        return events if isinstance(events, list) else []
    return result if isinstance(result, list) else []


def event_from_tool(
    user_id: int, event: dict[str, Any], timezone: str, now: datetime
) -> CalendarEventCache:
    return CalendarEventCache(
        user_id=user_id,
        event_id=str(event["id"]),
        title=event.get("title", ""),
        start_at=parse_time(event["start"], timezone),
        end_at=parse_time(event["end"], timezone),
        location=event.get("location", ""),
        description=event.get("description", ""),
        attendees_json=json.dumps(event.get("attendees", [])),
        updated_at=now,
    )


async def refresh_calendar(
    session: Session,
    user: User,
    manager: McpManager,
    days: int = 14,
    now: datetime | None = None,
) -> list[CalendarEventCache]:
    now = now or datetime.now(UTC)
    start, _ = local_day_bounds(now, user.timezone)
    end = now + timedelta(days=days)
    result = await manager.call(
        "google",
        "cal_list",
        {"start": start.isoformat(), "end": end.isoformat()},
    )
    if isinstance(result, dict) and result.get("error"):
        log.warning("calendar_refresh_failed", error=result.get("error"))
        return list(
            session.exec(select(CalendarEventCache).where(CalendarEventCache.user_id == user.id))
        )
    rows = [
        event_from_tool(user.id, event, user.timezone, now)
        for event in normalise_events(result)
        if event.get("id") and event.get("start") and event.get("end")
    ]
    session.exec(delete(CalendarEventCache).where(CalendarEventCache.user_id == user.id))
    for row in rows:
        session.add(row)
    session.commit()
    return rows


def list_events(
    session: Session,
    user: User,
    start: datetime,
    end: datetime,
) -> list[CalendarEventCache]:
    statement = (
        select(CalendarEventCache)
        .where(
            CalendarEventCache.user_id == user.id,
            CalendarEventCache.start_at < end,
            CalendarEventCache.end_at > start,
        )
        .order_by(CalendarEventCache.start_at)
    )
    return list(session.exec(statement))


def local_day_bounds(now: datetime, timezone: str) -> tuple[datetime, datetime]:
    zone = ZoneInfo(timezone)
    local = now.astimezone(zone)
    start = datetime.combine(local.date(), time.min, tzinfo=zone)
    return start.astimezone(UTC), (start + timedelta(days=1)).astimezone(UTC)


async def find_slots(
    manager: McpManager,
    rules: ClientRules,
    duration_minutes: int = 30,
    now: datetime | None = None,
    days: int = 7,
    attendees: list[str] | None = None,
    limit: int | None = None,
    timezone: str = "UTC",
) -> list[dict[str, Any]]:
    """Free slots inside business hours in `timezone`; any attendees must be free too."""
    now = (now or datetime.now(UTC)).astimezone(ZoneInfo(timezone))
    args: dict[str, Any] = {
        "start": now.isoformat(),
        "end": (now + timedelta(days=days)).isoformat(),
        "duration_minutes": duration_minutes,
        "working_hours": rules.business_hours,
    }
    if attendees:
        args["attendees"] = attendees
    if limit:
        args["limit"] = limit
    result = await manager.call("google", "cal_find_free_slots", args)
    if isinstance(result, dict):
        slots = result.get("slots", [])
    else:
        slots = result if isinstance(result, list) else []
    return [slot for slot in slots if isinstance(slot, dict)]


def describe_event(event: CalendarEventCache, timezone: str) -> str:
    start = as_utc(event.start_at).astimezone(ZoneInfo(timezone))
    return f"{start:%H:%M} {event.title}"
