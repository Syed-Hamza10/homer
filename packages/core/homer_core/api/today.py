from datetime import UTC, datetime

from fastapi import APIRouter
from sqlmodel import Session

from homer_core.api.deps import CurrentUser, RuntimeDep, SchedulerDep, SessionDep, SettingsDep
from homer_core.api.schemas.reminders import ReminderOut
from homer_core.api.schemas.skills import BriefOut, FollowUpOut, TodayOut
from homer_core.db.models import User
from homer_core.services import briefs, followups, google_account
from homer_core.services import day as day_service
from homer_core.services.calendar import local_day_bounds
from homer_core.services.rules import get_rules

router = APIRouter(prefix="/api/today", tags=["today"])


@router.get("")
async def today(
    user: CurrentUser,
    session: SessionDep,
    runtime: RuntimeDep,
    scheduler: SchedulerDep,
    settings: SettingsDep,
) -> TodayOut:
    rules = get_rules(session, user.id)
    now = datetime.now(UTC)
    day = briefs.day_string(now, user.timezone)
    _, end = local_day_bounds(now, user.timezone)
    snap = await day_service.snapshot(session, user, runtime.manager, rules, now)
    name = await day_service.greeting_name(user, runtime.manager)
    return TodayOut(
        day=day,
        brief=_brief(session, user, briefs.MORNING, day),
        digest=_brief(session, user, briefs.DIGEST, day),
        showing=briefs.current_kind(now, user.timezone),
        reminders=[
            ReminderOut.model_validate(row, from_attributes=True)
            for row in briefs.due_reminders(session, user, end)
        ],
        follow_ups=[
            FollowUpOut.from_row(row, rules)
            for row in followups.active_followups(session, user, end)
        ],
        background_refresh=settings.scheduler_enabled,
        health=scheduler.health,
        google=google_account.local_status(settings, now),
        card=day_service.day_card(session, user, snap, name, now),
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
