from datetime import UTC, datetime

import structlog
from fastapi import APIRouter
from sqlmodel import Session, select

from homer_core.agent.runtime import Runtime
from homer_core.api.deps import CurrentUser, RuntimeDep, SchedulerDep, SessionDep
from homer_core.api.schemas.reminders import ReminderOut
from homer_core.api.schemas.skills import (
    BriefOut,
    EventOut,
    FollowUpOut,
    TodayOut,
)
from homer_core.db.models import CalendarEventCache, EmailCache, User
from homer_core.mcp.manager import ExecuteFailed, ServerUnavailable
from homer_core.services import approvals, briefs, followups
from homer_core.services.calendar import list_events, local_day_bounds, refresh_calendar
from homer_core.services.inbox import list_inbox, refresh_inbox
from homer_core.services.rules import get_rules

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/today", tags=["today"])


async def _prime(user: User, session: Session, runtime: Runtime) -> None:
    rules = get_rules(session, user.id)
    events = session.exec(
        select(CalendarEventCache).where(CalendarEventCache.user_id == user.id)
    ).first()
    if events is None:
        try:
            await refresh_calendar(session, user, runtime.manager, days=14)
        except (ExecuteFailed, ServerUnavailable):
            log.exception("today_calendar_failed")
    messages = session.exec(select(EmailCache).where(EmailCache.user_id == user.id)).first()
    if messages is None:
        try:
            await refresh_inbox(session, user, runtime.manager, rules)
        except (ExecuteFailed, ServerUnavailable):
            log.exception("today_inbox_failed")


@router.get("")
async def today(
    user: CurrentUser, session: SessionDep, runtime: RuntimeDep, scheduler: SchedulerDep
) -> TodayOut:
    await _prime(user, session, runtime)
    rules = get_rules(session, user.id)
    now = datetime.now(UTC)
    day = briefs.day_string(now, user.timezone)
    start, end = local_day_bounds(now, user.timezone)
    events = list_events(session, user, start, end)
    messages = list_inbox(session, user)
    reminders = briefs.due_reminders(session, user, end)
    active = followups.active_followups(session, user, end)
    return TodayOut(
        day=day,
        brief=_brief(session, user, briefs.MORNING, day),
        digest=_brief(session, user, briefs.DIGEST, day),
        events=[EventOut.from_row(event) for event in events],
        reminders=[ReminderOut.model_validate(row, from_attributes=True) for row in reminders],
        follow_ups=[FollowUpOut.from_row(row, rules) for row in active],
        unread=len([message for message in messages if message.unread]),
        pending_approvals=len(approvals.list_pending(session, user)),
        health=scheduler.health,
    )


def _brief(session: Session, user: User, kind: str, day: str) -> BriefOut | None:
    row = briefs.brief_for_day(session, user, kind, day)
    return BriefOut.from_row(row) if row else None


@router.post("/brief")
async def morning_brief(user: CurrentUser, session: SessionDep, runtime: RuntimeDep) -> BriefOut:
    rules = get_rules(session, user.id)
    row = await briefs.morning_brief(session, user, runtime.manager, rules)
    return BriefOut.from_row(row)


@router.post("/digest")
async def eod_digest(user: CurrentUser, session: SessionDep, runtime: RuntimeDep) -> BriefOut:
    rules = get_rules(session, user.id)
    row = await briefs.eod_digest(session, user, runtime.manager, rules)
    return BriefOut.from_row(row)
