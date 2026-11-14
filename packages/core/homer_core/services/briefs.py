import re
from datetime import UTC, date, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

import structlog
from sqlmodel import Session, select

from homer_core.db.models import CalendarEventCache, DailyBrief, FollowUp, Reminder, User, as_utc
from homer_core.mcp.manager import (
    EXECUTOR_TOOL,
    PROFILE_TOOL,
    ExecuteFailed,
    McpManager,
    ServerUnavailable,
)
from homer_core.services import approvals, day, followups
from homer_core.services.calendar import describe_event, local_day_bounds, refresh_calendar
from homer_core.services.day import EmailNeed, Snapshot, greeting
from homer_core.services.inbox import refresh_inbox, triage
from homer_core.services.names import humanise, known_names, person
from homer_core.services.rules import ClientRules

log = structlog.get_logger(__name__)

MORNING = "morning"
DIGEST = "digest"
DIGEST_FROM = 15
LISTED = 5
ABOUT_SOMEONE = re.compile(
    r"^(?:remind\s+)?(?P<address>[\w.+-]+@[\w-]+(?:\.[\w-]+)+)\s+(?:that\s+\w+\s+)?"
    r"(?:owns|owes|has|needs|wants|promised|is\s+doing|is\s+handling)\s+(?P<topic>.+)$",
    re.IGNORECASE,
)
SelfEmailStatus = Literal["off", "ok", "mismatch", "unknown"]


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


def plural(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"


def when(moment: datetime, zone: ZoneInfo, today: date) -> str:
    local = as_utc(moment).astimezone(zone)
    return f"{local:%H:%M}" if local.date() == today else f"{local:%a %-d %b %H:%M}"


def sentence(text: str) -> str:
    text = text.strip().rstrip(".")
    return text[:1].upper() + text[1:]


def follow_up(name: str, topic: str) -> str:
    return f"Follow up with {name} about {topic or 'your email'}"


def reminder_line(text: str, known: dict[str, str]) -> str:
    """A reminder about someone else ("x@y.com owns the report") reads as a follow-up with
    them; any other reminder is its own text with addresses turned into names."""
    about = ABOUT_SOMEONE.match(text.strip().rstrip("."))
    if about:
        return follow_up(person(about["address"], known), about["topic"])
    return sentence(humanise(text, known))


def todo_lines(
    reminders: list[Reminder],
    open_followups: list[FollowUp],
    zone: ZoneInfo,
    today: date,
    known: dict[str, str],
) -> list[str]:
    """Reminders and follow-ups as "09:00 Follow up with Hassan about the report", by time."""
    items = [(as_utc(row.due_at), reminder_line(row.text, known)) for row in reminders] + [
        (as_utc(row.due_at), follow_up(person(row.contact, known), row.subject))
        for row in open_followups
    ]
    return [f"{when(due, zone, today)} {text}" for due, text in sorted(items, key=lambda x: x[0])]


def mail_line(unread: int, needs: list[EmailNeed], known: dict[str, str]) -> str:
    text = f"{plural(unread, 'unread email')} in your inbox" if unread else "Your inbox is read"
    if needs:
        listed = "; ".join(
            f"{need.subject or '(no subject)'} from {person(need.sender, known)}"
            for need in needs[:LISTED]
        )
        verb = "needs" if len(needs) == 1 else "need"
        text += f", {len(needs)} {verb} you: {listed}"
    return text + "."


def approvals_line(waiting: int) -> list[str]:
    return [f"{plural(waiting, 'approval')} waiting for you."] if waiting else []


def morning_text(session: Session, user: User, now: datetime, snap: Snapshot, name: str) -> str:
    zone = ZoneInfo(user.timezone)
    local = now.astimezone(zone)
    _, end = local_day_bounds(now, user.timezone)
    known = known_names(session, user)
    parts = [f"{greeting(name, now, user.timezone)} Today is {local:%A %-d %B}."]
    if snap.events:
        listed = "; ".join(describe_event(event, user.timezone) for event in snap.events[:LISTED])
        parts.append(f"On your calendar: {listed}.")
    else:
        parts.append("Nothing on your calendar today.")
    parts.append(mail_line(snap.unread, snap.needs_you, known))
    todos = todo_lines(
        due_reminders(session, user, end),
        followups.active_followups(session, user, end),
        zone,
        local.date(),
        known,
    )
    if todos:
        parts.append(f"Due today: {'; '.join(todos[:LISTED])}.")
    parts.extend(approvals_line(len(approvals.list_pending(session, user))))
    return " ".join(parts)


def digest_text(
    session: Session,
    user: User,
    now: datetime,
    snap: Snapshot,
    tomorrow: list[CalendarEventCache],
    name: str,
) -> str:
    zone = ZoneInfo(user.timezone)
    _, end = local_day_bounds(now, user.timezone)
    known = known_names(session, user)
    parts = [greeting(name, now, user.timezone)]
    if tomorrow:
        listed = "; ".join(describe_event(event, user.timezone) for event in tomorrow[:LISTED])
        parts.append(f"Tomorrow: {listed}.")
    else:
        parts.append("Nothing on your calendar tomorrow.")
    parts.append(mail_line(snap.unread, snap.needs_you, known))
    todos = todo_lines(
        due_reminders(session, user, end),
        followups.active_followups(session, user, end + timedelta(days=1)),
        zone,
        now.astimezone(zone).date(),
        known,
    )
    if todos:
        parts.append(f"Still open: {'; '.join(todos[:LISTED])}.")
    parts.extend(approvals_line(len(approvals.list_pending(session, user))))
    return " ".join(parts)


def current_kind(now: datetime, timezone: str) -> str:
    """The morning brief until 15:00 local time, the end-of-day digest after."""
    return MORNING if now.astimezone(ZoneInfo(timezone)).hour < DIGEST_FROM else DIGEST


async def account_email(manager: McpManager) -> str | None:
    try:
        result = await manager.call("google", PROFILE_TOOL, {})
    except (ExecuteFailed, ServerUnavailable):
        return None
    email = result.get("email") if isinstance(result, dict) else None
    return str(email).strip().lower() if email else None


def self_email_status(rules: ClientRules, account: str | None) -> SelfEmailStatus:
    """Email-to-self is tier 2 only because it goes to the user's own mailbox, so the address
    typed in Settings must match the connected account."""
    if not rules.email_to_self or not rules.self_email:
        return "off"
    if account is None:
        return "unknown"
    return "ok" if rules.self_email.strip().lower() == account else "mismatch"


async def send_to_self(
    manager: McpManager, rules: ClientRules, subject: str, body: str
) -> str | None:
    if not rules.email_to_self or not rules.self_email:
        return None
    account = await account_email(manager)
    status = self_email_status(rules, account)
    if status != "ok":
        log.warning("self_email_skipped", status=status)
        return None
    draft = await manager.call(
        "google",
        "mail_draft",
        {"to": account, "subject": subject, "body": body},
    )
    draft_id = draft.get("draft_id") if isinstance(draft, dict) else None
    if not draft_id:
        return None
    await manager.call(
        "google", EXECUTOR_TOOL, {"action": "mail_send", "payload": {"draft_id": draft_id}}
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
    snap = await day.snapshot(session, user, manager, rules, now)
    name = await day.greeting_name(user, manager)
    content = morning_text(session, user, now, snap, name)
    brief = save_brief(session, user, MORNING, day_string(now, user.timezone), content, now)
    try:
        await send_to_self(manager, rules, "Homer morning brief", content)
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
    snap = await day.snapshot(session, user, manager, rules, now)
    _, end = local_day_bounds(now, user.timezone)
    tomorrow = await day.events_between(session, user, manager, end, end + timedelta(days=1), now)
    name = await day.greeting_name(user, manager)
    content = digest_text(session, user, now, snap, tomorrow, name)
    brief = save_brief(session, user, DIGEST, day_string(now, user.timezone), content, now)
    try:
        await send_to_self(manager, rules, "Homer end-of-day digest", content)
    except (ExecuteFailed, ServerUnavailable):
        log.exception("digest_email_failed")
    return brief
