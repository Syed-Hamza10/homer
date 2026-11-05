from datetime import datetime, timedelta

from homer_core.agent.intents import CreateEvent
from homer_core.services.approvals import create_from_tool_result, is_approval_object
from homer_core.services.jobs.recipients import listed, resolve
from homer_core.services.jobs.turn import JobError, Turn

DEFAULT_MINUTES = 30


def at(day: str, clock: str) -> str:
    return f"{day}T{clock}:00"


def span_text(start: str, end: str) -> str:
    opens, closes = datetime.fromisoformat(start), datetime.fromisoformat(end)
    return f"{opens:%a %d %b} {opens:%H:%M}-{closes:%H:%M}"


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
    return slots[0]["start"], slots[0]["end"]


async def resolve_slot(turn: Turn, intent: CreateEvent) -> tuple[str, str]:
    minutes = intent.duration_minutes or DEFAULT_MINUTES
    if intent.start is None:
        return await find_slot(turn, intent, minutes)
    start = at(intent.date, intent.start)
    if intent.end is not None and intent.end > intent.start:
        return start, at(intent.date, intent.end)
    end = datetime.fromisoformat(start) + timedelta(minutes=minutes)
    return start, end.isoformat()


async def run(turn: Turn, intent: CreateEvent) -> None:
    attendees, questions = [], []
    for who in intent.attendees:
        try:
            attendees.append((await resolve(turn, who)).email)
        except JobError as error:
            questions.append(f"I left {who} off the invite. {error}")
    start, end = await resolve_slot(turn, intent)
    args = {
        "title": intent.title,
        "start": start,
        "end": end,
        "attendees": attendees,
        "timezone": turn.user.timezone,
    }
    result = await turn.call("google", "cal_create", args)
    if not is_approval_object(result):
        raise JobError(f"I could not prepare the event: {result}")
    turn.requested(create_from_tool_result(turn.session, turn.user.id, "google", result))
    turn.say(
        f"Event '{intent.title}' on {span_text(start, end)} is ready. Edit it or press Create."
    )
    for question in questions:
        turn.say(question)
