import json
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import structlog
from sqlmodel import Session, select

from homer_core.db.models import EmailCache, User
from homer_core.mcp.manager import ExecuteFailed, McpManager, ServerUnavailable
from homer_core.services.errors import DomainError, NotFound
from homer_core.services.rules import ClientRules

log = structlog.get_logger(__name__)

DEFAULT_CATEGORY = "To review"
INBOX_QUERY = "in:inbox"
PRIORITY_LABEL = "Priority"
CATEGORY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Invoices", ("invoice", "payment", "receipt", "billing", "remittance", "paid")),
    (
        "Meetings",
        ("meeting", "call", "kickoff", "schedule", "slot", "calendar", "standup", "sync"),
    ),
    ("Newsletters", ("newsletter", "unsubscribe", "digest", "promotion", "offer", "webinar")),
    ("Clients", ("client", "proposal", "partnership", "contract", "project", "brief", "quote")),
)


def clean(text: str) -> str:
    return text.replace("<untrusted>", "").replace("</untrusted>", "").strip()


def normalise(result: Any) -> list[dict[str, Any]]:
    if isinstance(result, dict):
        messages = result.get("messages")
        return messages if isinstance(messages, list) else []
    return result if isinstance(result, list) else []


def sender_email(sender: str) -> str:
    if "<" in sender and ">" in sender:
        return sender.rsplit("<", 1)[1].split(">", 1)[0].strip().lower()
    return sender.strip().lower()


def category_for(subject: str, sender: str, rules: ClientRules) -> str:
    if any(contact.lower() in sender.lower() for contact in rules.priority_contacts if contact):
        return "Clients"
    haystack = f"{subject} {sender}".lower()
    for category, words in CATEGORY_RULES:
        if any(word in haystack for word in words):
            return category
    return DEFAULT_CATEGORY


def received_at(message: dict[str, Any], now: datetime) -> datetime:
    internal = (message.get("metadata") or {}).get("internal_date")
    if internal:
        return datetime.fromtimestamp(int(internal) / 1000, UTC)
    header = message.get("date", "")
    if header:
        try:
            parsed = parsedate_to_datetime(header)
            return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except (TypeError, ValueError):
            pass
    return now


def email_from_message(
    user_id: int, message: dict[str, Any], rules: ClientRules, now: datetime
) -> EmailCache:
    labels = [str(label) for label in message.get("labels", [])]
    sender = message.get("from", "")
    subject = message.get("subject", "")
    return EmailCache(
        user_id=user_id,
        message_id=str(message["id"]),
        thread_id=str(message.get("thread_id", "")),
        sender=sender,
        subject=subject,
        snippet=clean(message.get("snippet", "")),
        received_at=received_at(message, now),
        labels_json=json.dumps(labels),
        category=category_for(subject, sender, rules),
        unread="UNREAD" in labels,
        priority=any(c.lower() in sender.lower() for c in rules.priority_contacts if c),
        archived=False,
        updated_at=now,
    )


def upsert_email(
    session: Session, user_id: int, message: dict[str, Any], rules: ClientRules, now: datetime
) -> EmailCache:
    message_id = str(message["id"])
    row = session.exec(
        select(EmailCache).where(EmailCache.user_id == user_id, EmailCache.message_id == message_id)
    ).first()
    fresh = email_from_message(user_id, message, rules, now)
    if row is None:
        session.add(fresh)
        session.commit()
        session.refresh(fresh)
        return fresh
    for field in ("thread_id", "sender", "subject", "snippet", "received_at", "labels_json"):
        setattr(row, field, getattr(fresh, field))
    row.category = fresh.category
    row.unread = fresh.unread
    row.priority = fresh.priority
    row.updated_at = now
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


async def refresh_inbox(
    session: Session,
    user: User,
    manager: McpManager,
    rules: ClientRules,
    limit: int = 25,
    now: datetime | None = None,
) -> list[EmailCache]:
    now = now or datetime.now(UTC)
    result = await manager.call(
        "google", "mail_search", {"query": INBOX_QUERY, "max_results": limit}
    )
    rows = [
        upsert_email(session, user.id, message, rules, now)
        for message in normalise(result)[:limit]
        if message.get("id")
    ]
    log.info("inbox_refreshed", messages=len(rows))
    return rows


async def label_rows(manager: McpManager, rows: list[EmailCache]) -> dict[str, int]:
    labeled = 0
    failed = 0
    for row in rows:
        labels = [row.category]
        if row.priority:
            labels.append(PRIORITY_LABEL)
        try:
            result = await manager.call(
                "google",
                "mail_label",
                {"message_id": row.message_id, "add": labels, "remove": []},
            )
        except (ExecuteFailed, ServerUnavailable):
            log.exception("triage_label_failed", message_id=row.message_id)
            failed += 1
            continue
        if isinstance(result, dict) and result.get("error"):
            failed += 1
        else:
            labeled += 1
    return {"labeled": labeled, "failed": failed}


async def triage(
    session: Session, user: User, manager: McpManager, rules: ClientRules
) -> dict[str, int]:
    rows = list(
        session.exec(
            select(EmailCache).where(
                EmailCache.user_id == user.id,
                EmailCache.archived.is_(False),
            )
        )
    )
    return await label_rows(manager, rows)


def list_inbox(
    session: Session,
    user: User,
    category: str | None = None,
    unread: bool | None = None,
    limit: int = 100,
) -> list[EmailCache]:
    statement = select(EmailCache).where(
        EmailCache.user_id == user.id,
        EmailCache.archived.is_(False),
    )
    if category:
        statement = statement.where(EmailCache.category == category)
    if unread is not None:
        statement = statement.where(EmailCache.unread == unread)
    statement = statement.order_by(EmailCache.received_at.desc()).limit(limit)
    return list(session.exec(statement))


def get_email(session: Session, user: User, message_id: str) -> EmailCache:
    row = session.exec(
        select(EmailCache).where(EmailCache.user_id == user.id, EmailCache.message_id == message_id)
    ).first()
    if row is None:
        raise NotFound(f"message {message_id} not found")
    return row


def get_email_by_thread(session: Session, user: User, thread_id: str) -> EmailCache | None:
    return session.exec(
        select(EmailCache)
        .where(EmailCache.user_id == user.id, EmailCache.thread_id == thread_id)
        .order_by(EmailCache.received_at.desc())
    ).first()


async def archive(session: Session, user: User, manager: McpManager, message_id: str) -> EmailCache:
    row = get_email(session, user, message_id)
    result = await manager.call("google", "mail_archive", {"message_id": message_id})
    if isinstance(result, dict) and result.get("error"):
        raise DomainError(str(result["error"]))
    row.archived = True
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def summary(session: Session, user: User) -> str:
    rows = list_inbox(session, user)
    if not rows:
        return "The inbox cache is empty. Run /inbox again after a mail refresh."
    unread = [row for row in rows if row.unread]
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.category] = counts.get(row.category, 0) + 1
    parts = [f"{len(rows)} messages in the inbox cache, {len(unread)} unread."]
    parts.append("By category: " + ", ".join(f"{name} {count}" for name, count in counts.items()))
    if unread:
        subjects = "; ".join(f"{row.subject} from {row.sender}" for row in unread[:3])
        parts.append(f"Unread: {subjects}.")
    return " ".join(parts)
