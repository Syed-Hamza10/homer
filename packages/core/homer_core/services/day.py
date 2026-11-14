import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

import structlog
from pydantic import BaseModel
from sqlalchemy import delete, func
from sqlmodel import Session, col, select

from homer_core.agent.prompt import known_name
from homer_core.db.models import CalendarEventCache, EmailCache, User, as_utc
from homer_core.mcp.manager import PROFILE_TOOL, ExecuteFailed, McpManager, ServerUnavailable
from homer_core.services import approvals, followups
from homer_core.services.calendar import (
    event_from_tool,
    list_events,
    local_day_bounds,
    normalise_events,
)
from homer_core.services.inbox import category_for, sender_email
from homer_core.services.names import call_name
from homer_core.services.rules import ClientRules

log = structlog.get_logger(__name__)

EMAIL_LIMIT = 3
UNREAD_SCAN = 25
INBOX = "INBOX"
PRIORITY_CATEGORY = "Clients"
FAILURES = (ExecuteFailed, ServerUnavailable)
PROFILES: dict[int, dict[str, str]] = {}


class Meeting(BaseModel):
    event_id: str
    title: str
    start: datetime
    end: datetime
    attendees: list[str]
    join_url: str | None


class EmailNeed(BaseModel):
    thread_id: str
    sender: str
    subject: str
    received_at: datetime
    reason: str


class FollowUpDue(BaseModel):
    id: int
    thread_id: str
    subject: str
    contact: str
    due_at: datetime


class ApprovalWaiting(BaseModel):
    id: int
    action: str
    preview: str


class DayCard(BaseModel):
    greeting: str
    meetings: list[Meeting]
    next_event_id: str | None
    emails: list[EmailNeed]
    needs_you: int
    unread: int
    follow_ups: list[FollowUpDue]
    approvals: list[ApprovalWaiting]
    live: bool
    as_of: datetime | None


@dataclass
class Snapshot:
    """Today's events and mail counts, read from Google when it answers, else from the cache
    as it stood at `as_of`."""

    events: list[CalendarEventCache]
    unread: int
    needs_you: list[EmailNeed]
    live: bool
    as_of: datetime | None


def part_of_day(now: datetime, timezone: str) -> str:
    hour = now.astimezone(ZoneInfo(timezone)).hour
    return "morning" if 5 <= hour < 12 else "afternoon" if 12 <= hour < 18 else "evening"


def greeting(name: str, now: datetime, timezone: str) -> str:
    part = part_of_day(now, timezone)
    return f"Good {part}, {name}." if name else f"Good {part}."


async def account(user: User, manager: McpManager) -> dict[str, str]:
    """The connected mailbox's address and display name, looked up once; empty while Google
    does not answer."""
    if user.id not in PROFILES:
        try:
            found = await manager.call("google", PROFILE_TOOL, {"with_name": True})
        except FAILURES:
            return {}
        if not isinstance(found, dict) or "error" in found:
            return {}
        PROFILES[user.id] = {
            "email": str(found.get("email") or "").lower(),
            "name": str(found.get("name") or ""),
        }
    return PROFILES[user.id]


async def greeting_name(user: User, manager: McpManager) -> str:
    """The name from Settings, else the Gmail display name, else ""."""
    chosen = known_name(user.name)
    if chosen:
        return call_name(chosen)
    return call_name((await account(user, manager)).get("name", ""))


def join_url(event: CalendarEventCache) -> str | None:
    for text in (event.location, event.description):
        for word in text.split():
            if word.startswith("https://"):
                return word
    return None


def meeting(event: CalendarEventCache) -> Meeting:
    return Meeting(
        event_id=event.event_id,
        title=event.title,
        start=as_utc(event.start_at),
        end=as_utc(event.end_at),
        attendees=json.loads(event.attendees_json),
        join_url=join_url(event),
    )


def need_reason(priority: bool, replied: bool) -> str | None:
    if priority:
        return "Priority contact"
    return "Waiting on your reply" if replied else None


def replied_threads(session: Session, user: User) -> set[str]:
    statement = select(EmailCache.thread_id).where(
        EmailCache.user_id == user.id, col(EmailCache.labels_json).contains('"SENT"')
    )
    return {thread for thread in session.exec(statement) if thread}


def cached_needs(session: Session, user: User) -> list[EmailNeed]:
    """Unread mail from priority contacts, or unread replies in threads the user wrote in."""
    statement = (
        select(EmailCache)
        .where(
            EmailCache.user_id == user.id,
            EmailCache.unread.is_(True),
            EmailCache.archived.is_(False),
        )
        .order_by(col(EmailCache.received_at).desc())
    )
    replied = replied_threads(session, user)
    found: list[EmailNeed] = []
    for row in session.exec(statement):
        reason = need_reason(
            row.priority or row.category == PRIORITY_CATEGORY, row.thread_id in replied
        )
        if reason:
            found.append(
                EmailNeed(
                    thread_id=row.thread_id,
                    sender=row.sender,
                    subject=row.subject,
                    received_at=as_utc(row.received_at),
                    reason=reason,
                )
            )
    return found


def cached_unread(session: Session, user: User) -> int:
    statement = select(func.count()).where(
        EmailCache.user_id == user.id,
        EmailCache.unread.is_(True),
        EmailCache.archived.is_(False),
    )
    return session.exec(statement).one()


def last_update(session: Session, user: User, table: type[Any]) -> datetime | None:
    found = session.exec(select(func.max(table.updated_at)).where(table.user_id == user.id)).one()
    return as_utc(found) if found else None


async def live_events(
    session: Session,
    user: User,
    manager: McpManager,
    start: datetime,
    end: datetime,
    now: datetime,
) -> list[CalendarEventCache] | None:
    """Events between start and end straight from Google, saved over the cached copy of that
    span; None when Google does not answer."""
    try:
        result = await manager.call(
            "google", "cal_list", {"start": start.isoformat(), "end": end.isoformat()}
        )
    except FAILURES as error:
        log.warning("day_calendar_failed", error=str(error))
        return None
    if isinstance(result, dict) and "error" in result:
        log.warning("day_calendar_failed", error=result["error"])
        return None
    rows = [
        event_from_tool(user.id, event, user.timezone, now)
        for event in normalise_events(result)
        if event.get("id") and event.get("start") and event.get("end")
    ]
    session.exec(
        delete(CalendarEventCache).where(
            CalendarEventCache.user_id == user.id,
            CalendarEventCache.start_at < end,
            CalendarEventCache.end_at > start,
        )
    )
    session.add_all(row for row in rows if row.start_at < end and row.end_at > start)
    session.commit()
    return list_events(session, user, start, end)


async def events_between(
    session: Session,
    user: User,
    manager: McpManager,
    start: datetime,
    end: datetime,
    now: datetime,
) -> list[CalendarEventCache]:
    rows = await live_events(session, user, manager, start, end, now)
    return rows if rows is not None else list_events(session, user, start, end)


async def live_unread(manager: McpManager) -> int | None:
    try:
        result = await manager.call("google", "mail_labels", {})
    except FAILURES as error:
        log.warning("day_unread_failed", error=str(error))
        return None
    labels = result.get("labels") if isinstance(result, dict) else None
    for label in labels if isinstance(labels, list) else []:
        if label.get("id") == INBOX:
            return int(label.get("unread", 0))
    return None


def received(thread: dict[str, Any], now: datetime) -> datetime:
    stamp = thread.get("internal_date")
    return datetime.fromtimestamp(int(stamp) / 1000, UTC) if stamp else now


def thread_need(
    thread: dict[str, Any], rules: ClientRules, me: str, now: datetime
) -> EmailNeed | None:
    """None when nothing waits on the user, including when they wrote the latest message."""
    sender = str(thread.get("from", ""))
    subject = str(thread.get("subject", ""))
    if me and sender_email(sender) == me:
        return None
    priority = category_for(subject, sender, rules) == PRIORITY_CATEGORY
    reason = need_reason(priority, "SENT" in thread.get("label_ids", []))
    if reason is None:
        return None
    return EmailNeed(
        thread_id=str(thread["id"]),
        sender=sender,
        subject=subject,
        received_at=received(thread, now),
        reason=reason,
    )


async def live_needs(
    user: User, manager: McpManager, rules: ClientRules, now: datetime
) -> list[EmailNeed] | None:
    args = {"query": "is:unread", "label": INBOX, "max_results": UNREAD_SCAN}
    try:
        result = await manager.call("google", "mail_list_threads", args)
    except FAILURES as error:
        log.warning("day_needs_failed", error=str(error))
        return None
    threads = result.get("threads") if isinstance(result, dict) else None
    if not isinstance(threads, list):
        return None
    me = (await account(user, manager)).get("email", "")
    found = (thread_need(thread, rules, me, now) for thread in threads if thread.get("id"))
    return [need for need in found if need]


async def snapshot(
    session: Session, user: User, manager: McpManager, rules: ClientRules, now: datetime
) -> Snapshot:
    start, end = local_day_bounds(now, user.timezone)
    events, unread, needs = await asyncio.gather(
        live_events(session, user, manager, start, end, now),
        live_unread(manager),
        live_needs(user, manager, rules, now),
    )
    stale: list[datetime | None] = []
    if events is None:
        events = list_events(session, user, start, end)
        stale.append(last_update(session, user, CalendarEventCache))
    if unread is None or needs is None:
        stale.append(last_update(session, user, EmailCache))
    known = [moment for moment in stale if moment]
    return Snapshot(
        events=events,
        unread=cached_unread(session, user) if unread is None else unread,
        needs_you=cached_needs(session, user) if needs is None else needs,
        live=not stale,
        as_of=min(known) if known else None,
    )


def day_card(session: Session, user: User, snap: Snapshot, name: str, now: datetime) -> DayCard:
    """Everything the Today card shows, from one snapshot so every count agrees."""
    _, end = local_day_bounds(now, user.timezone)
    meetings = [meeting(event) for event in snap.events]
    upcoming = next((item for item in meetings if item.end > now), None)
    return DayCard(
        greeting=greeting(name, now, user.timezone),
        meetings=meetings,
        next_event_id=upcoming.event_id if upcoming else None,
        emails=snap.needs_you[:EMAIL_LIMIT],
        needs_you=len(snap.needs_you),
        unread=snap.unread,
        follow_ups=[
            FollowUpDue(
                id=row.id,
                thread_id=row.thread_id,
                subject=row.subject,
                contact=row.contact,
                due_at=as_utc(row.due_at),
            )
            for row in followups.active_followups(session, user, end)
        ],
        approvals=[
            ApprovalWaiting(id=row.id, action=row.action, preview=row.preview)
            for row in approvals.list_pending(session, user)
        ],
        live=snap.live,
        as_of=snap.as_of,
    )
