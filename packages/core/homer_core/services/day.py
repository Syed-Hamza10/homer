import json
from datetime import datetime
from zoneinfo import ZoneInfo

from pydantic import BaseModel
from sqlmodel import Session, col, select

from homer_core.db.models import CalendarEventCache, EmailCache, User, as_utc
from homer_core.services import approvals, followups
from homer_core.services.calendar import list_events, local_day_bounds

EMAIL_LIMIT = 3
PRIORITY_CATEGORY = "Clients"


class Meeting(BaseModel):
    event_id: str
    title: str
    start: datetime
    end: datetime
    attendees: list[str]
    join_url: str | None


class EmailNeed(BaseModel):
    message_id: str
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
    follow_ups: list[FollowUpDue]
    approvals: list[ApprovalWaiting]


def greeting(name: str, now: datetime, timezone: str) -> str:
    hour = now.astimezone(ZoneInfo(timezone)).hour
    part = "morning" if 5 <= hour < 12 else "afternoon" if 12 <= hour < 18 else "evening"
    first = name.split()[0] if name.strip() else ""
    return f"Good {part}, {first}." if first else f"Good {part}."


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


def replied_threads(session: Session, user: User) -> set[str]:
    statement = select(EmailCache.thread_id).where(
        EmailCache.user_id == user.id, col(EmailCache.labels_json).contains('"SENT"')
    )
    return {thread for thread in session.exec(statement) if thread}


def emails_needing_you(session: Session, user: User) -> list[EmailNeed]:
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
        if row.priority or row.category == PRIORITY_CATEGORY:
            reason = "Priority contact"
        elif row.thread_id in replied:
            reason = "Waiting on your reply"
        else:
            continue
        found.append(
            EmailNeed(
                message_id=row.message_id,
                thread_id=row.thread_id,
                sender=row.sender,
                subject=row.subject,
                received_at=as_utc(row.received_at),
                reason=reason,
            )
        )
        if len(found) == EMAIL_LIMIT:
            break
    return found


def day_card(session: Session, user: User, now: datetime) -> DayCard:
    """Everything the Today card shows, read from the caches with no model call."""
    start, end = local_day_bounds(now, user.timezone)
    meetings = [meeting(event) for event in list_events(session, user, start, end)]
    upcoming = next((item for item in meetings if item.end > now), None)
    return DayCard(
        greeting=greeting(user.name, now, user.timezone),
        meetings=meetings,
        next_event_id=upcoming.event_id if upcoming else None,
        emails=emails_needing_you(session, user),
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
    )
