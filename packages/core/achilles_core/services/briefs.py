from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import structlog
from sqlmodel import Session, select

from achilles_core.db.models import DailyBrief, Reminder, User
from achilles_core.mcp.manager import ExecuteFailed, McpManager, ServerUnavailable
from achilles_core.services import approvals, followups
from achilles_core.services.calendar import (
    describe_event,
    list_events,
    local_day_bounds,
    refresh_calendar,
)
from achilles_core.services.inbox import list_inbox, refresh_inbox, triage
from achilles_core.services.rules import ClientRules

log = structlog.get_logger(__name__)

MORNING = "morning"
DIGEST = "digest"


def save_brief(
    session: Session, user: User, kind: str, day: str, content: str, now: datetime
) -> DailyBrief:
    row = session.exec(
        select(DailyBrief).where(
            DailyBrief.user_id == user.id, DailyBrief.kind == kind, DailyBrief.day == day
        )
    ).first()
    if row is None:
        row = DailyBrief(user_id=user.id, kind=kind, day=day, content=content)
    else:
        row.content = content
        row.created_at = now
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def brief_for_day(session: Session, user: User, kind: str, day: str) -> DailyBrief | None:
    return session.exec(
        select(DailyBrief).where(
            DailyBrief.user_id == user.id, DailyBrief.kind == kind, DailyBrief.day == day
        )
    ).first()


def day_string(now: datetime, timezone: str) -> str:
    return now.astimezone(ZoneInfo(timezone)).date().isoformat()


def due_reminders(session: Session, user: User, until: datetime) -> list[Reminder]:
    statement = (
        select(Reminder)
        .where(
            Reminder.user_id == user.id,
            Reminder.status.in_(("pending", "due")),
            Reminder.due_at <= until,
        )
        .order_by(Reminder.due_at)
    )
    return list(session.exec(statement))


async def refresh_sources(
    session: Session, user: User, manager: McpManager, rules: ClientRules
) -> None:
    try:
        refresh_email = await refresh_inbox(session, user, manager, rules)
    except (ExecuteFailed, ServerUnavailable):
        log.exception("brief_inbox_failed")
        refresh_email = []
    if refresh_email:
        try:
            await triage(session, user, manager, rules)
        except (ExecuteFailed, ServerUnavailable):
            log.exception("brief_triage_failed")
    try:
        await refresh_calendar(session, user, manager, days=14)
    except (ExecuteFailed, ServerUnavailable):
        log.exception("brief_calendar_failed")


def morning_text(session: Session, user: User, now: datetime) -> str:
    zone = ZoneInfo(user.timezone)
    local = now.astimezone(zone)
    start, end = local_day_bounds(now, user.timezone)
    events = list_events(session, user, start, end)
    messages = list_inbox(session, user)
    unread = [message for message in messages if message.unread]
    reminders = due_reminders(session, user, end)
    open_followups = followups.active_followups(session, user, end)
    waiting = len(approvals.list_pending(session, user))

    parts = [f"Good morning. Today is {local:%A %d %B}."]
    if events:
        listed = "; ".join(describe_event(event, user.timezone) for event in events[:5])
        parts.append(f"{len(events)} events today: {listed}.")
    else:
        parts.append("No events today.")
    parts.append(f"{len(unread)} unread of {len(messages)} messages in the inbox cache.")
    if reminders:
        listed = "; ".join(
            f"{reminder.due_at.astimezone(zone):%H:%M} {reminder.text}"
            for reminder in reminders[:5]
        )
        parts.append(f"Due today: {listed}.")
    if open_followups:
        listed = "; ".join(followup.subject for followup in open_followups[:5])
        parts.append(f"{len(open_followups)} follow-ups need attention: {listed}.")
    parts.append(f"{waiting} approval{'s' if waiting != 1 else ''} waiting.")
    return " ".join(parts)


def digest_text(session: Session, user: User, now: datetime) -> str:
    _, end = local_day_bounds(now, user.timezone)
    tomorrow_end = end + timedelta(days=1)
    events = list_events(session, user, end, tomorrow_end)
    messages = list_inbox(session, user)
    unread = [message for message in messages if message.unread]
    open_followups = followups.active_followups(session, user, tomorrow_end)
    waiting = len(approvals.list_pending(session, user))

    parts = ["End of day."]
    if events:
        listed = "; ".join(describe_event(event, user.timezone) for event in events[:5])
        parts.append(f"Tomorrow: {listed}.")
    else:
        parts.append("Nothing on the calendar tomorrow.")
    parts.append(f"Inbox: {len(messages)} messages, {len(unread)} unread.")
    if open_followups:
        listed = "; ".join(followup.subject for followup in open_followups[:5])
        parts.append(f"Still open: {listed}.")
    parts.append(f"{waiting} approval{'s' if waiting != 1 else ''} waiting.")
    return " ".join(parts)


async def send_to_self(
    manager: McpManager, rules: ClientRules, subject: str, body: str
) -> str | None:
    if not rules.email_to_self or not rules.self_email:
        return None
    draft = await manager.call(
        "google",
        "mail_draft",
        {"to": rules.self_email, "subject": subject, "body": body},
    )
    draft_id = draft.get("draft_id") if isinstance(draft, dict) else None
    if not draft_id:
        return None
    await manager.call(
        "google", "execute", {"action": "mail_send", "payload": {"draft_id": draft_id}}
    )
    return str(draft_id)


async def morning_brief(
    session: Session,
    user: User,
    manager: McpManager,
    rules: ClientRules,
    now: datetime | None = None,
    refresh: bool = True,
) -> DailyBrief:
    now = now or datetime.now(UTC)
    if refresh:
        await refresh_sources(session, user, manager, rules)
    content = morning_text(session, user, now)
    brief = save_brief(session, user, MORNING, day_string(now, user.timezone), content, now)
    try:
        await send_to_self(manager, rules, "Achilles morning brief", content)
    except (ExecuteFailed, ServerUnavailable):
        log.exception("brief_email_failed")
    return brief


async def eod_digest(
    session: Session,
    user: User,
    manager: McpManager,
    rules: ClientRules,
    now: datetime | None = None,
    refresh: bool = False,
) -> DailyBrief:
    now = now or datetime.now(UTC)
    if refresh:
        await refresh_sources(session, user, manager, rules)
    await followups.check_followups(session, user, manager, rules, now)
    content = digest_text(session, user, now)
    brief = save_brief(session, user, DIGEST, day_string(now, user.timezone), content, now)
    try:
        await send_to_self(manager, rules, "Achilles end-of-day digest", content)
    except (ExecuteFailed, ServerUnavailable):
        log.exception("digest_email_failed")
    return brief
