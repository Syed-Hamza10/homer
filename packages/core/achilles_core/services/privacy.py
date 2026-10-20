from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, func
from sqlmodel import Session, select

from achilles_core.db.models import (
    Approval,
    CalendarEventCache,
    Conversation,
    DailyBrief,
    EmailCache,
    FollowUp,
    Message,
    OutboundLog,
    Reminder,
    TokenCounter,
    User,
)
from achilles_core.services.store import read_setting, write_setting

WEB_SEARCH_KEY = "web_search"


@dataclass(frozen=True)
class HostUsage:
    host: str
    calls: int
    last_seen: datetime


def host_usage(session: Session) -> list[HostUsage]:
    statement = (
        select(OutboundLog.host, func.count(OutboundLog.id), func.max(OutboundLog.ts))
        .group_by(OutboundLog.host)
        .order_by(func.count(OutboundLog.id).desc())
    )
    return [HostUsage(host, calls, last_seen) for host, calls, last_seen in session.exec(statement)]


def token_usage(session: Session, user: User) -> TokenCounter:
    return session.get(TokenCounter, user.id) or TokenCounter(user_id=user.id)


def get_web_search(session: Session, user_id: int) -> bool | None:
    value = read_setting(session, user_id, WEB_SEARCH_KEY)
    return None if value is None else value == "true"


def set_web_search(session: Session, user_id: int, enabled: bool) -> None:
    write_setting(session, user_id, WEB_SEARCH_KEY, "true" if enabled else "false")


def wipe(session: Session, user: User) -> dict[str, int]:
    deleted: dict[str, int] = {}
    conversations = select(Conversation.id).where(Conversation.user_id == user.id)
    deleted["messages"] = session.exec(
        delete(Message).where(Message.conversation_id.in_(conversations))
    ).rowcount
    deleted["conversations"] = session.exec(
        delete(Conversation).where(Conversation.user_id == user.id)
    ).rowcount
    tables = (
        ("approvals", Approval),
        ("reminders", Reminder),
        ("email_cache", EmailCache),
        ("calendar_cache", CalendarEventCache),
        ("daily_briefs", DailyBrief),
        ("follow_ups", FollowUp),
    )
    for name, table in tables:
        deleted[name] = session.exec(delete(table).where(table.user_id == user.id)).rowcount
    deleted["token_counter"] = session.exec(
        delete(TokenCounter).where(TokenCounter.user_id == user.id)
    ).rowcount
    deleted["outbound_log"] = session.exec(delete(OutboundLog)).rowcount
    session.commit()
    return deleted
