import json
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import structlog
from sqlmodel import Session

from homer_core.db.models import Approval, CalendarEventCache, User
from homer_core.mcp.manager import McpManager
from homer_core.services.approvals import create, is_approval_object
from homer_core.services.calendar import list_events
from homer_core.services.errors import DomainError
from homer_core.services.jobs.change_event import span
from homer_core.services.jobs.read_calendar import bounds
from homer_core.services.mail import GoogleFailed, checked

log = structlog.get_logger(__name__)


class NothingToChange(DomainError):
    status_code = 422


def cached_event(row: CalendarEventCache) -> dict[str, Any]:
    attendees = json.loads(row.attendees_json)
    return {
        "id": row.event_id,
        "title": row.title,
        "start": row.start_at.isoformat(),
        "end": row.end_at.isoformat(),
        "all_day": False,
        "location": row.location,
        "description": row.description,
        "attendees": attendees,
        "people": [
            {"email": email, "name": "", "response": "needsAction", "organizer": False}
            for email in attendees
        ],
        "organizer": "",
        "video_link": "",
    }


async def events_between(
    session: Session, user: User, manager: McpManager, start: datetime, end: datetime
) -> tuple[list[dict[str, Any]], str]:
    """Events from Google for the range; the saved copy (marked "cache") when Google fails."""
    result = await manager.call(
        "google", "cal_list", {"start": start.isoformat(), "end": end.isoformat()}
    )
    if isinstance(result, dict) and isinstance(result.get("events"), list):
        return result["events"], "google"
    log.warning("calendar_range_failed", error=result)
    return [cached_event(row) for row in list_events(session, user, start, end)], "cache"


async def event(manager: McpManager, event_id: str) -> dict[str, Any]:
    return checked(await manager.call("google", "cal_get", {"event_id": event_id}))


def local_time(value: str, zone: ZoneInfo) -> datetime:
    """A wall time from the dashboard (no offset) read in the user's zone; an offset is kept."""
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=zone)


def approval_from(session: Session, user: User, result: Any, preview: str | None) -> Approval:
    if not is_approval_object(result):
        checked(result)
        raise GoogleFailed(f"unexpected answer from the google server: {result!r}")
    return create(
        session,
        user.id,
        "google",
        result["action"],
        result["payload"],
        preview or result["preview"],
    )


async def request_create(
    session: Session,
    user: User,
    manager: McpManager,
    fields: dict[str, Any],
) -> Approval:
    """A `cal_create` approval; times are wall times in the user's timezone."""
    args = {**fields, "timezone": user.timezone}
    return approval_from(session, user, await manager.call("google", "cal_create", args), None)


def changed_fields(
    current: dict[str, Any], wanted: dict[str, Any], zone: ZoneInfo
) -> dict[str, Any]:
    changes: dict[str, Any] = {}
    opens, closes = bounds(current, zone)
    start = local_time(wanted["start"], zone) if wanted.get("start") else opens
    end = local_time(wanted["end"], zone) if wanted.get("end") else closes
    if (start, end) != (opens, closes):
        changes |= {"start": start.isoformat(), "end": end.isoformat()}
    for key in ("title", "description", "location"):
        if wanted.get(key) is not None and wanted[key] != current.get(key, ""):
            changes[key] = wanted[key]
    attendees = wanted.get("attendees")
    if attendees is not None and sorted(map(str.lower, attendees)) != sorted(
        map(str.lower, current.get("attendees", []))
    ):
        changes["attendees"] = attendees
    return changes


def update_preview(current: dict[str, Any], changes: dict[str, Any], zone: ZoneInfo) -> str:
    title = current.get("title", "")
    lines = []
    if "start" in changes:
        after = span({"start": changes["start"], "end": changes["end"]}, zone)
        lines.append(f"Move '{title}' from {span(current, zone)} to {after}")
    else:
        lines.append(f"Change '{title}' on {span(current, zone)}")
    if "title" in changes:
        lines.append(f"Title: {title} -> {changes['title']}")
    if "attendees" in changes:
        before = ", ".join(current.get("attendees", [])) or "nobody"
        lines.append(f"Attendees: {before} -> {', '.join(changes['attendees']) or 'nobody'}")
    for key in ("location", "description"):
        if key in changes:
            lines.append(f"{key.capitalize()}: {changes[key] or '(empty)'}")
    return "\n".join(lines)


async def request_update(
    session: Session, user: User, manager: McpManager, event_id: str, wanted: dict[str, Any]
) -> Approval:
    """A `cal_update` approval with before and after; only fields that differ are sent."""
    zone = ZoneInfo(user.timezone)
    current = await event(manager, event_id)
    changes = changed_fields(current, wanted, zone)
    if not changes:
        raise NothingToChange("nothing to change")
    args = {"event_id": event_id, **changes, "timezone": user.timezone}
    result = await manager.call("google", "cal_update", args)

    return approval_from(session, user, result, update_preview(current, changes, zone))


async def request_cancel(
    session: Session, user: User, manager: McpManager, event_id: str
) -> Approval:
    zone = ZoneInfo(user.timezone)
    current = await event(manager, event_id)
    preview = f"Delete '{current.get('title', '')}' on {span(current, zone)}"
    if current.get("attendees"):
        preview += f" with {', '.join(current['attendees'])}"
    result = await manager.call("google", "cal_delete", {"event_id": event_id})
    return approval_from(session, user, result, preview)
