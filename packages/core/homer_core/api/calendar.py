from datetime import UTC, datetime, timedelta

from fastapi import APIRouter

from homer_core.api.deps import CurrentUser, RuntimeDep, SessionDep
from homer_core.api.schemas.approvals import ApprovalOut
from homer_core.api.schemas.calendar import (
    EventChange,
    EventCreate,
    EventDetailOut,
    EventRangeOut,
)
from homer_core.api.schemas.skills import EventOut, SlotOut, SlotRequest
from homer_core.services import calendar, calendar_view
from homer_core.services.errors import DomainError
from homer_core.services.rules import get_rules

MAX_RANGE = timedelta(days=62)

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
    slots = await calendar.find_slots(
        runtime.manager,
        rules,
        body.duration_minutes,
        days=body.days,
        attendees=body.attendees,
        limit=body.limit,
        timezone=user.timezone,
    )
    return [SlotOut(**slot) for slot in slots]


@router.get("/events")
async def events(
    start: datetime, end: datetime, user: CurrentUser, session: SessionDep, runtime: RuntimeDep
) -> EventRangeOut:
    if start.tzinfo is None or end.tzinfo is None:
        raise DomainError("start and end need a UTC offset")
    if not start < end <= start + MAX_RANGE:
        raise DomainError("the range must be positive and at most 62 days")
    found, source = await calendar_view.events_between(session, user, runtime.manager, start, end)
    return EventRangeOut(events=[EventDetailOut.model_validate(e) for e in found], source=source)


@router.get("/events/{event_id}")
async def event(event_id: str, user: CurrentUser, runtime: RuntimeDep) -> EventDetailOut:
    return EventDetailOut.model_validate(await calendar_view.event(runtime.manager, event_id))


@router.post("/events")
async def create_event(
    body: EventCreate, user: CurrentUser, session: SessionDep, runtime: RuntimeDep
) -> ApprovalOut:
    approval = await calendar_view.request_create(session, user, runtime.manager, body.model_dump())
    return ApprovalOut.from_row(approval)


@router.patch("/events/{event_id}")
async def update_event(
    event_id: str, body: EventChange, user: CurrentUser, session: SessionDep, runtime: RuntimeDep
) -> ApprovalOut:
    approval = await calendar_view.request_update(
        session, user, runtime.manager, event_id, body.model_dump(exclude_none=True)
    )
    return ApprovalOut.from_row(approval)


@router.post("/events/{event_id}/cancel")
async def cancel_event(
    event_id: str, user: CurrentUser, session: SessionDep, runtime: RuntimeDep
) -> ApprovalOut:
    approval = await calendar_view.request_cancel(session, user, runtime.manager, event_id)
    return ApprovalOut.from_row(approval)
