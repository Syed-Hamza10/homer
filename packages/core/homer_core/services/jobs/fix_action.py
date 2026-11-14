import re
from datetime import datetime
from typing import Any

from pydantic_ai.messages import ModelRequest, UserPromptPart

from homer_core.agent.intents import (
    Background,
    CreateEvent,
    EditDraft,
    FixLastAction,
    UpdateEvent,
    extract,
)
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


async def redone(turn: Turn, original: str, what: str) -> CreateEvent | UpdateEvent | None:
    """The original request read again, with code counting any time from now; a correction
    that adds facts ("I said 3pm") is read with it, a bare "why 15:00?" is not."""
    said = [part for part in re.split(r"(?<=[?.!])\s+", what.strip()) if not WHY.match(part)]
    message = "\n".join([original, *said]) if said else original
    known = Background(timezone=turn.user.timezone, date_format=turn.date_format)
    found, usage = await extract(turn.runtime.intents, message, [], turn.now, known)
    turn.usage.incr(usage)
    return next((i for i in found if isinstance(i, CreateEvent | UpdateEvent)), None)


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


async def fix(turn: Turn, intent: FixLastAction) -> None:
    """Redoes the last action from the user's own request instead of telling them to fix it:
    a draft is edited as they say, an event gets a corrected card."""
    last = last_action(turn) or {}
    if last.get("kind") in DRAFT_KINDS:
        edit = EditDraft(kind="edit_draft", instruction=intent.what_is_wrong)
        await edit_email.edit(turn, edit)
        return
    redo = await redone(turn, original_request(turn), intent.what_is_wrong)
    if redo is None:
        turn.say("You're right. Tell me the day and time it should be, and I'll fix it.")
        return
    move = await as_move(turn, redo)
    turn.say("You're right, that was wrong. Here is the fix.")
    await change_event.update(turn, move)
