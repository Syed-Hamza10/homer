import json
import re
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from pydantic_ai.messages import ModelRequest, UserPromptPart

from homer_core.agent.dates import in_zone, span_label, stated_times, weekday_date
from homer_core.agent.intents import (
    Background,
    CreateEvent,
    EditDraft,
    FixLastAction,
    UpdateEvent,
    extract,
    span_minutes,
)
from homer_core.db.models import Approval
from homer_core.services.jobs import change_event, create_event, edit_email
from homer_core.services.jobs.turn import Turn

EVENT_KINDS = frozenset({"create_event", "update_event"})
DRAFT_KINDS = frozenset({"send_email", "edit_draft"})
WHY = re.compile(r"^\W*(?:why|how come|what)\b", re.IGNORECASE)
DEFERS = re.compile(
    r"\b(?:please |you can |you could |you may )?(?:edit|delete|remove)\b[^.]{0,30}"
    r"\b(?:it|that|the event|the draft|this)\b|\bcreate a new one\b|\bmust have made a mistake\b",
    re.IGNORECASE,
)


def last_action(turn: Turn) -> dict[str, Any] | None:
    """The event or draft the previous turn made, if it made one."""
    for item in reversed(turn.previous):
        if item.get("kind") in DRAFT_KINDS or (
            item.get("kind") in EVENT_KINDS and item.get("approval_id")
        ):
            return item
    return None


def original_request(turn: Turn) -> str:
    """The user's previous message, the request the last action came from."""
    for message in reversed(turn.history):
        if isinstance(message, ModelRequest):
            parts = [p.content for p in message.parts if isinstance(p, UserPromptPart)]
            if parts:
                return str(parts[-1])
    return ""


def amended(
    intent: CreateEvent | UpdateEvent, correction: str, today: date
) -> CreateEvent | UpdateEvent | None:
    """The request with the one time and day the correction names put in by code; None when
    it names neither."""
    times, day = stated_times(correction), weekday_date(correction, today)
    if len(times) != 1 and day is None:
        return None
    if isinstance(intent, UpdateEvent):
        update: dict[str, Any] = {"relative_minutes": None}
        if len(times) == 1:
            update |= {"new_start": times[0], "new_end": None}
        return intent.model_copy(update=update | ({"new_date": day.isoformat()} if day else {}))
    update = {"relative_minutes": None, "after_next_event": False}
    if len(times) == 1:
        length = intent.duration_minutes or span_minutes(intent.start, intent.end)
        update |= {"start": times[0], "end": None, "duration_minutes": length}
    return intent.model_copy(update=update | ({"date": day.isoformat()} if day else {}))


async def read_again(turn: Turn, message: str) -> CreateEvent | UpdateEvent | None:
    known = Background(timezone=turn.user.timezone, date_format=turn.date_format)
    found, usage = await extract(turn.runtime.intents, message, [], turn.now, known)
    turn.usage.incr(usage)
    return next((i for i in found if isinstance(i, CreateEvent | UpdateEvent)), None)


async def redone(turn: Turn, original: str, what: str) -> CreateEvent | UpdateEvent | None:
    """The original request read again, with code counting any time from now. The time or day
    a correction names ("I said 4pm") is put in by code; other added facts are read with the
    request; a bare "why 15:00?" adds nothing."""
    said = " ".join(p for p in re.split(r"(?<=[?.!])\s+", what.strip()) if not WHY.match(p))
    intent = await read_again(turn, original)
    if not said:
        return intent
    fixed = amended(intent, said, turn.now.date()) if intent else None
    return fixed or await read_again(turn, f"{original}\n{said}") or intent


async def as_move(turn: Turn, intent: CreateEvent | UpdateEvent) -> UpdateEvent:
    """The corrected request as a move of the event the last action made."""
    if isinstance(intent, UpdateEvent):
        return intent.model_copy(update={"match": "it", "date": None})
    start, end = await create_event.resolve_slot(turn, intent)
    opens, closes = datetime.fromisoformat(start), datetime.fromisoformat(end)
    return UpdateEvent(
        kind="update_event",
        match="it",
        new_date=opens.date().isoformat(),
        new_start=f"{opens:%H:%M}",
        new_end=f"{closes:%H:%M}",
    )


def made(turn: Turn, last: dict[str, Any]) -> tuple[datetime, datetime] | None:
    """When the event the last action proposed starts and ends, from its card, in the user's
    zone."""
    approval = turn.session.get(Approval, last.get("approval_id") or 0)
    if approval is None or approval.user_id != turn.user.id:
        return None
    payload = json.loads(approval.payload_json)
    start, end = payload.get("start"), payload.get("end")
    if not isinstance(start, str) or not isinstance(end, str):
        return None
    zone = ZoneInfo(turn.user.timezone)
    return in_zone(start, zone), in_zone(end, zone)


def unchanged(move: UpdateEvent, start: datetime, end: datetime) -> bool:
    """The request read again gives the same day and times the card already has."""
    if move.relative_minutes or move.new_title or move.duration_minutes:
        return False
    return (
        move.new_date in (None, start.date().isoformat())
        and move.new_start in (None, f"{start:%H:%M}")
        and move.new_end in (None, f"{end:%H:%M}")
    )


def explained(original: str, start: datetime, end: datetime) -> str:
    asked = " ".join(original.split()).rstrip(".?!")
    return f'You asked for "{asked}", so I set {span_label(start, end)}. Want a different time?'


async def fix(turn: Turn, intent: FixLastAction) -> None:
    """Redoes the last action from the user's own request instead of telling them to fix it:
    a draft is edited as they say, an event gets a corrected card. When the request read again
    gives what the card already says, it explains why and makes no card."""
    last = last_action(turn) or {}
    if last.get("kind") in DRAFT_KINDS:
        edit = EditDraft(kind="edit_draft", instruction=intent.what_is_wrong)
        await edit_email.edit(turn, edit)
        return
    original = original_request(turn)
    redo = await redone(turn, original, intent.what_is_wrong)
    if redo is None:
        turn.say("You're right. Tell me the day and time it should be, and I'll fix it.")
        return
    move = await as_move(turn, redo)
    current = made(turn, last)
    if current is not None and unchanged(move, *current):
        turn.say(explained(original, *current))
        return
    turn.say("You're right, that was wrong. Here is the fix.")
    await change_event.update(turn, move)
