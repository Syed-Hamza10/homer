import re
from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlmodel import Session, select

from achilles_core.db.models import Approval, FollowUp, User, utcnow
from achilles_core.mcp.manager import ExecuteFailed, McpManager, ServerUnavailable
from achilles_core.services import approvals
from achilles_core.services.errors import DomainError, NotFound
from achilles_core.services.inbox import sender_email
from achilles_core.services.rules import ClientRules

OPEN = "open"
DRAFTED = "drafted"
CLOSED = "closed"
SUBJECT_PREFIX = re.compile(r"^(re:\s*)+", re.IGNORECASE)


def thread_messages(result: Any) -> list[dict[str, Any]]:
    if isinstance(result, dict):
        messages = result.get("messages")
        return messages if isinstance(messages, list) else []
    return result if isinstance(result, list) else []


def is_from_self(message: dict[str, Any], rules: ClientRules) -> bool:
    if "SENT" in [str(label) for label in message.get("labels", [])]:
        return True
    return bool(rules.self_email) and sender_email(message.get("from", "")) == (
        rules.self_email.lower()
    )


def clean_subject(subject: str) -> str:
    return SUBJECT_PREFIX.sub("", subject).strip()


def contact_of(messages: list[dict[str, Any]], rules: ClientRules) -> str:
    for message in reversed(messages):
        if not is_from_self(message, rules):
            return message.get("from", "")
    return messages[-1].get("from", "") if messages else ""


def due_time(now: datetime, days: int, timezone: str) -> datetime:
    zone = ZoneInfo(timezone)
    local = now.astimezone(zone)
    target = local.date() + timedelta(days=days)
    return datetime.combine(target, time(9, 0), tzinfo=zone).astimezone(UTC)


async def create_followup(
    session: Session,
    user: User,
    manager: McpManager,
    rules: ClientRules,
    thread_id: str,
    days: int | None = None,
    now: datetime | None = None,
) -> FollowUp:
    now = now or datetime.now(UTC)
    result = await manager.call("google", "mail_thread", {"thread_id": thread_id})
    messages = thread_messages(result)
    if not messages:
        raise NotFound(f"thread {thread_id} not found")
    last = messages[-1]
    days = days or rules.follow_up_days
    due_at = due_time(now, days, user.timezone)
    existing = session.exec(
        select(FollowUp).where(
            FollowUp.user_id == user.id,
            FollowUp.thread_id == thread_id,
            FollowUp.status.in_((OPEN, DRAFTED)),
        )
    ).first()
    followup = existing or FollowUp(user_id=user.id, thread_id=thread_id, due_at=due_at)
    followup.subject = clean_subject(last.get("subject", ""))
    followup.contact = contact_of(messages, rules)
    followup.due_at = due_at
    followup.status = OPEN
    followup.updated_at = now
    session.add(followup)
    session.commit()
    session.refresh(followup)
    return followup


def draft_body(followup: FollowUp, rules: ClientRules) -> str:
    email = sender_email(followup.contact)
    name = email.split("@")[0].replace(".", " ").title() if email else "there"
    signature = f"\n\n{rules.signature}" if rules.signature else ""
    return (
        f'Hi {name},\n\nJust following up on "{followup.subject}". '
        f"Is there anything you need from me?{signature}"
    )


async def check_followups(
    session: Session,
    user: User,
    manager: McpManager,
    rules: ClientRules,
    now: datetime | None = None,
) -> dict[str, int]:
    now = now or datetime.now(UTC)
    rows = list(
        session.exec(
            select(FollowUp).where(
                FollowUp.user_id == user.id,
                FollowUp.status.in_((OPEN, DRAFTED)),
                FollowUp.due_at <= now,
            )
        )
    )
    closed = drafted = failed = 0
    for followup in rows:
        try:
            result = await manager.call("google", "mail_thread", {"thread_id": followup.thread_id})
        except (ExecuteFailed, ServerUnavailable):
            failed += 1
            continue
        messages = thread_messages(result)
        if not messages:
            failed += 1
            continue
        if not is_from_self(messages[-1], rules):
            followup.status = CLOSED
            followup.updated_at = now
            session.add(followup)
            session.commit()
            closed += 1
            continue
        if followup.draft_id:
            continue
        draft = await manager.call(
            "google",
            "mail_draft",
            {
                "to": sender_email(followup.contact),
                "subject": f"Re: {followup.subject}",
                "body": draft_body(followup, rules),
                "thread_id": followup.thread_id,
            },
        )
        if isinstance(draft, dict) and draft.get("draft_id"):
            followup.draft_id = str(draft["draft_id"])
            followup.status = DRAFTED
            followup.updated_at = now
            session.add(followup)
            session.commit()
            drafted += 1
        else:
            failed += 1
    return {"checked": len(rows), "closed": closed, "drafted": drafted, "failed": failed}


def list_followups(session: Session, user: User) -> list[FollowUp]:
    statement = (
        select(FollowUp).where(FollowUp.user_id == user.id).order_by(FollowUp.due_at, FollowUp.id)
    )
    return list(session.exec(statement))


def active_followups(session: Session, user: User, until: datetime) -> list[FollowUp]:
    statement = (
        select(FollowUp)
        .where(
            FollowUp.user_id == user.id,
            FollowUp.status.in_((OPEN, DRAFTED)),
            FollowUp.due_at <= until,
        )
        .order_by(FollowUp.due_at, FollowUp.id)
    )
    return list(session.exec(statement))


def get_followup(session: Session, user: User, followup_id: int) -> FollowUp:
    followup = session.get(FollowUp, followup_id)
    if followup is None or followup.user_id != user.id:
        raise NotFound(f"follow-up {followup_id} not found")
    return followup


async def request_send(
    session: Session, user: User, manager: McpManager, followup_id: int
) -> Approval:
    """Asks the google server for the mail_send approval of the follow-up draft and stores it, so
    the normal approval flow decides whether the draft goes out."""
    followup = get_followup(session, user, followup_id)
    if not followup.draft_id:
        raise DomainError(f"follow-up {followup_id} has no draft yet")
    result = await manager.call("google", "mail_send", {"draft_id": followup.draft_id})
    if not approvals.is_approval_object(result):
        raise DomainError(f"draft {followup.draft_id} cannot be sent: {result}")
    return approvals.create_from_tool_result(session, user.id, "google", result)


def close_followup(session: Session, user: User, followup_id: int) -> FollowUp:
    followup = get_followup(session, user, followup_id)
    followup.status = CLOSED
    followup.updated_at = utcnow()
    session.add(followup)
    session.commit()
    session.refresh(followup)
    return followup
