import re
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from homer_core.agent.dates import from_now, in_zone, span_label
from homer_core.agent.intents import CORRECTION, CreateEvent
from homer_core.agent.voice import phrase
from homer_core.db.models import Approval
from homer_core.services.approval_edits import SUPERSEDED
from homer_core.services.approvals import (
    NotPending,
    create_from_tool_result,
    is_approval_object,
    transition_from_pending,
)
from homer_core.services.jobs.choice import Choice
from homer_core.services.jobs.read_calendar import bounds
from homer_core.services.jobs.recipients import listed, resolve
from homer_core.services.jobs.turn import JobError, Turn

DEFAULT_MINUTES = 30
NEXT_DAYS = 30
READY = (
    "Event '{title}' on {when} is ready. Edit it or press Create.",
    "Ready to book '{title}' on {when}. Edit it or press Create.",
)
WITH = re.compile(r"\bwith\s+(.+)$", re.IGNORECASE)


def at(day: str, clock: str) -> str:
    return f"{day}T{clock}:00"


def wall_time(value: str, zone: ZoneInfo) -> str:
    """The time as a wall time in the user's zone, with no offset."""
    return in_zone(value, zone).replace(tzinfo=None).isoformat()


async def find_slot(turn: Turn, intent: CreateEvent, minutes: int) -> tuple[str, str]:
    opens, closes = turn.rules.business_hours.split("-")
    opens, closes = intent.window_start or opens, intent.window_end or closes
    args = {
        "start": at(intent.date, opens),
        "end": at(intent.date, closes),
        "duration_minutes": minutes,
        "working_hours": f"{opens}-{closes}",
        "timezone": turn.user.timezone,
    }
    slots = listed(await turn.call("google", "cal_find_free_slots", args), "slots")
    if not slots:
        raise JobError(
            f"No free {minutes}-minute slot on {intent.date} between {opens} and {closes}."
        )
    zone = ZoneInfo(turn.user.timezone)
    return wall_time(slots[0]["start"], zone), wall_time(slots[0]["end"], zone)


def kept_minutes(turn: Turn) -> int | None:
    """A correction ("make it 2pm instead") keeps the length of the event it corrects."""
    if not CORRECTION.search(turn.message):
        return None
    for item in reversed(turn.previous):
        if item.get("kind") == "create_event" and item.get("start") and item.get("end"):
            opens, closes = time.fromisoformat(item["start"]), time.fromisoformat(item["end"])
            minutes = (closes.hour * 60 + closes.minute) - (opens.hour * 60 + opens.minute)
            return minutes if minutes > 0 else None
    return None


async def next_end(turn: Turn) -> datetime:
    """When the next event that has not started yet ends, in the user's zone."""
    zone = ZoneInfo(turn.user.timezone)
    first = datetime.combine(turn.now.date(), time.min, zone)
    args = {
        "start": first.isoformat(),
        "end": (first + timedelta(days=NEXT_DAYS)).isoformat(),
    }
    events = listed(await turn.call("google", "cal_list", args), "events")
    ahead = sorted(
        (bounds(event, zone) for event in events if "T" in str(event.get("start", ""))),
        key=lambda span: span[0],
    )
    upcoming = [span for span in ahead if span[0] >= turn.now]
    if not upcoming:
        raise JobError("You have no meeting coming up in the next 30 days to book after.")
    return upcoming[0][1]


async def resolve_slot(turn: Turn, intent: CreateEvent) -> tuple[str, str]:
    minutes = intent.duration_minutes or kept_minutes(turn) or DEFAULT_MINUTES
    if intent.after_next_event:
        opens = (await next_end(turn)).replace(tzinfo=None)
        return opens.isoformat(), (opens + timedelta(minutes=minutes)).isoformat()
    if intent.relative_minutes:
        opens = from_now(turn.now, intent.relative_minutes).replace(tzinfo=None)
        return opens.isoformat(), (opens + timedelta(minutes=minutes)).isoformat()
    if intent.start is None:
        return await find_slot(turn, intent, minutes)
    start = at(intent.date, intent.start)
    if intent.end is not None and intent.end > intent.start:
        return start, at(intent.date, intent.end)
    end = datetime.fromisoformat(start) + timedelta(minutes=minutes)
    return start, end.isoformat()


def people(intent: CreateEvent) -> list[str]:
    """The attendees, or the person in a "Meeting with Maya" title when the model left them out."""
    if intent.attendees:
        return intent.attendees
    found = WITH.search(intent.title)
    return [found.group(1).strip()] if found else []


def supersede_previous(turn: Turn) -> None:
    """A correction replaces the event card the previous turn left pending."""
    for item in turn.previous:
        if item.get("kind") != "create_event" or not item.get("approval_id"):
            continue
        approval = turn.session.get(Approval, item["approval_id"])
        if approval is None or approval.user_id != turn.user.id:
            continue
        try:
            transition_from_pending(turn.session, approval, SUPERSEDED)
        except NotPending:
            continue


async def run(turn: Turn, intent: CreateEvent) -> None:
    attendees, questions = [], []
    for who in people(intent):
        try:
            attendees.append((await resolve(turn, who)).email)
        except Choice:
            raise
        except JobError as error:
            questions.append(f"I left {who} off the invite. {error}")
    start, end = await resolve_slot(turn, intent)
    args = {
        "title": intent.title,
        "start": start,
        "end": end,
        "attendees": attendees,
        "description": intent.description or "",
        "timezone": turn.user.timezone,
    }
    result = await turn.call("google", "cal_create", args)
    if not is_approval_object(result):
        raise JobError(f"I could not prepare the event: {result}")
    approval = create_from_tool_result(turn.session, turn.user.id, "google", result)
    turn.requested(approval)
    turn.note(approval_id=approval.id, start=start[11:16], end=end[11:16])
    if CORRECTION.search(turn.message):
        supersede_previous(turn)
    zone = ZoneInfo(turn.user.timezone)
    when = span_label(in_zone(start, zone), in_zone(end, zone))
    turn.say(phrase(turn.history, READY, title=intent.title, when=when))
    for question in questions:
        turn.say(question)
