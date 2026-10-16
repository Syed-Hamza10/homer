from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func
from sqlmodel import Session, select

from achilles_core.db.models import OutboundLog, TokenCounter, User


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
