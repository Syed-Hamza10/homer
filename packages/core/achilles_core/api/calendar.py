from datetime import UTC, datetime, timedelta

from fastapi import APIRouter

from achilles_core.api.deps import CurrentUser, RuntimeDep, SessionDep
from achilles_core.api.schemas.skills import EventOut, SlotOut, SlotRequest
from achilles_core.services import calendar
from achilles_core.services.rules import get_rules

router = APIRouter(prefix="/api/calendar", tags=["calendar"])


@router.get("")
async def list_events(
    user: CurrentUser, session: SessionDep, runtime: RuntimeDep, days: int = 7
) -> list[EventOut]:
    now = datetime.now(UTC)
    end = now + timedelta(days=days)
    rows = calendar.list_events(session, user, now, end)
    if not rows:
        rows = await calendar.refresh_calendar(session, user, runtime.manager, days=days)
    return [EventOut.from_row(row) for row in rows]


@router.post("/refresh")
async def refresh(
    user: CurrentUser, session: SessionDep, runtime: RuntimeDep, days: int = 14
) -> list[EventOut]:
    rows = await calendar.refresh_calendar(session, user, runtime.manager, days=days)
    return [EventOut.from_row(row) for row in rows]


@router.post("/find-slot")
async def find_slot(
    body: SlotRequest, user: CurrentUser, session: SessionDep, runtime: RuntimeDep
) -> list[SlotOut]:
    rules = get_rules(session, user.id)
    slots = await calendar.find_slots(runtime.manager, rules, body.duration_minutes, days=body.days)
    return [SlotOut(**slot) for slot in slots]
