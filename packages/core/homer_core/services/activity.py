import json
import re
from datetime import UTC, datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel
from sqlalchemy import func
from sqlmodel import Session, col, select

from homer_core.db.models import Approval, Fact, User, as_utc

ActivityKind = Literal["email", "calendar", "memory", "account"]
ActivityFilter = Literal["all", "email", "calendar", "memory"]

PAGE_SIZE = 30
QUOTED = re.compile(r"'([^']+)'")
EMAIL_ACTIONS = ("mail_send",)
CALENDAR_ACTIONS = ("cal_create", "cal_update", "cal_delete")


class ActivityItem(BaseModel):
    id: str
    kind: ActivityKind
    at: datetime
    text: str
    detail: str | None = None
    status: str
    link: str | None = None


class ActivityPage(BaseModel):
    items: list[ActivityItem]
    next: datetime | None


def person(address: str) -> str:
    name = address.split("<", 1)[0].strip().strip('"')
    return name or address.strip("<> ")


def when(value: str | None, zone: ZoneInfo) -> str:
    if not value:
        return ""
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return ""
    return f"{as_utc(moment).astimezone(zone):%a %H:%M}"


def event_title(payload: dict[str, Any], preview: str) -> str:
    quoted = QUOTED.search(preview)
    return str(payload.get("title") or (quoted.group(1) if quoted else "event"))


MAIL_TEXT = {
    "done": "Sent email to {who}",
    "pending": "Drafted email to {who}, waiting for approval",
    "running": "Sending email to {who}",
    "rejected": "Rejected draft to {who}",
    "expired": "Draft to {who} expired",
    "failed": "Could not send email to {who}",
    "unknown": "Email to {who} may not have sent",
    "superseded": "Replaced draft to {who}",
}

CALENDAR_TEXT = {
    "cal_create": {
        "done": "Added '{title}' {at}",
        "pending": "Proposed '{title}' {at}, waiting for approval",
        "rejected": "Rejected event '{title}'",
    },
    "cal_update": {
        "done": "Moved '{title}' to {at}",
        "pending": "Proposed moving '{title}' to {at}, waiting for approval",
        "rejected": "Rejected moving '{title}'",
    },
    "cal_delete": {
        "done": "Deleted '{title}'",
        "pending": "Proposed deleting '{title}', waiting for approval",
        "rejected": "Kept '{title}'",
    },
}

OTHER_STATUS = {
    "running": "Working on '{title}'",
    "expired": "Change to '{title}' expired",
    "failed": "Could not change '{title}'",
    "unknown": "Change to '{title}' may not have applied",
    "superseded": "Replaced the proposal for '{title}'",
}


def approval_link(approval: Approval, payload: dict[str, Any]) -> str | None:
    if approval.status == "pending":
        return f"/approvals#approval-{approval.id}"
    if approval.conversation_id is not None:
        return f"/?conversation={approval.conversation_id}"
    if payload.get("thread_id"):
        return f"/inbox?thread={payload['thread_id']}"
    if payload.get("event_id"):
        return f"/calendar?event={payload['event_id']}"
    return "/approvals"


def describe(approval: Approval, zone: ZoneInfo) -> ActivityItem:
    payload = json.loads(approval.payload_json)
    at = as_utc(approval.decided_at or approval.created_at)
    base = {
        "id": f"approval-{approval.id}",
        "at": at,
        "status": approval.status,
        "link": approval_link(approval, payload),
    }
    if approval.action in EMAIL_ACTIONS:
        template = MAIL_TEXT.get(approval.status, "Email to {who}: " + approval.status)
        return ActivityItem(
            kind="email",
            text=template.format(who=person(str(payload.get("to", "")))),
            detail=payload.get("subject") or None,
            **base,
        )
    title = event_title(payload, approval.preview)
    texts = CALENDAR_TEXT.get(approval.action, {}) | OTHER_STATUS
    template = texts.get(approval.status, "'{title}': " + approval.status)
    text = template.format(title=title, at=when(payload.get("start"), zone)).strip()
    return ActivityItem(kind="calendar", text=text, **base)


def approval_items(
    session: Session, user: User, before: datetime, kinds: tuple[str, ...], limit: int
) -> list[ActivityItem]:
    stamp = func.coalesce(col(Approval.decided_at), col(Approval.created_at))
    statement = (
        select(Approval)
        .where(Approval.user_id == user.id, stamp < before, col(Approval.action).in_(kinds))
        .order_by(stamp.desc(), col(Approval.id).desc())
        .limit(limit)
    )
    zone = ZoneInfo(user.timezone)
    return [describe(approval, zone) for approval in session.exec(statement)]


def fact_items(session: Session, user: User, before: datetime, limit: int) -> list[ActivityItem]:
    statement = (
        select(Fact)
        .where(Fact.user_id == user.id, Fact.created_at < before)
        .order_by(col(Fact.created_at).desc(), col(Fact.id).desc())
        .limit(limit)
    )
    return [
        ActivityItem(
            id=f"fact-{fact.id}",
            kind="memory",
            at=as_utc(fact.created_at),
            text=f"Remembered: {fact.text}",
            status="done",
        )
        for fact in session.exec(statement)
    ]


def account_items(connected_at: datetime | None, before: datetime) -> list[ActivityItem]:
    if connected_at is None or as_utc(connected_at) >= before:
        return []
    return [
        ActivityItem(
            id="google-connected",
            kind="account",
            at=as_utc(connected_at),
            text="Google connected",
            status="done",
            link="/settings",
        )
    ]


def timeline(
    session: Session,
    user: User,
    google_connected_at: datetime | None,
    before: datetime | None = None,
    kind: ActivityFilter = "all",
    limit: int = PAGE_SIZE,
) -> ActivityPage:
    """Newest first, built from approvals, facts and the Google token's consent time; `next`
    is the cursor for the following page, or None at the end."""
    before = as_utc(before) if before else datetime.now(UTC)
    actions = {
        "all": EMAIL_ACTIONS + CALENDAR_ACTIONS,
        "email": EMAIL_ACTIONS,
        "calendar": CALENDAR_ACTIONS,
        "memory": (),
    }[kind]
    items = approval_items(session, user, before, actions, limit + 1) if actions else []
    if kind in ("all", "memory"):
        items += fact_items(session, user, before, limit + 1)
    if kind == "all":
        items += account_items(google_connected_at, before)
    items.sort(key=lambda item: item.at, reverse=True)
    page = items[:limit]
    return ActivityPage(items=page, next=page[-1].at if len(items) > limit else None)
