import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from homer_core.agent.dates import WEEKDAY_WORDS
from homer_core.agent.intents import CancelEvent, UpdateEvent
from homer_core.db.models import Approval
from homer_core.services.approvals import (
    SUPERSEDED,
    NotPending,
    create,
    create_from_tool_result,
    is_approval_object,
    transition_from_pending,
)
from homer_core.services.jobs.read_calendar import bounds
from homer_core.services.jobs.recipients import listed
from homer_core.services.jobs.turn import JobError, Turn

SEARCH_DAYS = 30
BACK_DAYS = 7
EVENT_ACTIONS = frozenset({"cal_create", "cal_update"})
FILLER = frozenset(
    {"the", "my", "a", "an", "our", "this", "that", "with", "w/", "event", "meeting", "on", "at"}
    | {"to", "for", "and", "of", "in", "from", "next", "today", "tomorrow"}
)
REFERENCE = frozenset(
    {"it", "one", "just", "booked", "we", "i", "made", "created", "added", "scheduled"}
    | {"proposed", "call", "appointment", "earlier", "new", "same"}
)


@dataclass(frozen=True)
class Target:
    """The event to change, and the approval it came from while that is still pending."""

    event: dict[str, Any]
    card: Approval | None = None


def words(match: str) -> list[str]:
    cleaned = match.lower().replace("'s", " ").replace(",", " ")
    return [word for word in cleaned.split() if word not in FILLER]


def weekdays(wanted: list[str]) -> set[int]:
    return {WEEKDAY_WORDS[word] for word in wanted if word in WEEKDAY_WORDS}


def described(wanted: list[str]) -> list[str]:
    return [word for word in wanted if word not in WEEKDAY_WORDS]


def text_of(event: dict[str, Any]) -> str:
    return " ".join([str(event.get("title", "")), *map(str, event.get("attendees", []))]).lower()


def matches(event: dict[str, Any], wanted: list[str]) -> bool:
    text = text_of(event)
    return all(word in text for word in wanted)


def score(event: dict[str, Any], wanted: list[str]) -> int:
    text = text_of(event)
    return sum(word in text for word in wanted)


def span(event: dict[str, Any], zone: ZoneInfo) -> str:
    opens, closes = bounds(event, zone)
    return f"{opens:%a %d %b} {opens:%H:%M}-{closes:%H:%M}"


def refers(match: str, event: dict[str, Any]) -> bool:
    """True when the user's words point at the event from context: "it", "the call we just
    booked", or words all found in its title or attendees."""
    wanted = [word for word in described(words(match)) if word not in REFERENCE]
    return not wanted or matches(event, wanted)


def zoned(event: dict[str, Any], zone: ZoneInfo) -> dict[str, Any]:
    """A proposed event's times without an offset are local, as they were sent with the zone."""
    fixed = dict(event)
    for key in ("start", "end"):
        value = datetime.fromisoformat(str(event[key]))
        fixed[key] = (value if value.tzinfo else value.replace(tzinfo=zone)).isoformat()
    return fixed


def context_event(approval: Approval) -> dict[str, Any] | None:
    """The event an earlier approval proposed or changed, as it stands now."""
    result = json.loads(approval.result_json) if approval.result_json else None
    if approval.status == "done" and isinstance(result, dict) and result.get("id"):
        return result
    if approval.status != "pending":
        return None
    payload = json.loads(approval.payload_json)
    if approval.action == "cal_create":
        return payload
    return {"id": payload.get("event_id"), "lookup": True}


async def from_context(turn: Turn, match: str) -> Target | None:
    """The newest event this chat booked, proposed or moved, when the words point at it."""
    for item in reversed(turn.earlier):
        approval = turn.session.get(Approval, item.get("approval_id") or 0)
        if approval is None or approval.user_id != turn.user.id:
            continue
        if approval.action not in EVENT_ACTIONS:
            continue
        event = context_event(approval)
        if event is not None and event.get("lookup"):
            event = await by_id(turn, str(event["id"]))
        if event is None:
            continue
        if not refers(match, event):
            return None
        zone = ZoneInfo(turn.user.timezone)
        return Target(zoned(event, zone), approval if approval.status == "pending" else None)
    return None


async def around(turn: Turn) -> list[dict[str, Any]]:
    """Events from a week back to a month ahead."""
    zone = ZoneInfo(turn.user.timezone)
    today = turn.now.date()
    first, last = today - timedelta(days=BACK_DAYS), today + timedelta(days=SEARCH_DAYS)
    args = {
        "start": datetime.combine(first, time.min, zone).isoformat(),
        "end": datetime.combine(last, time.min, zone).isoformat(),
    }
    return listed(await turn.call("google", "cal_list", args), "events")


async def by_id(turn: Turn, event_id: str) -> dict[str, Any] | None:
    return next((event for event in await around(turn) if event.get("id") == event_id), None)


def candidates(events: list[dict[str, Any]], wanted: list[str]) -> list[dict[str, Any]]:
    """Events with every word, else those sharing the most words with the match."""
    exact = [event for event in events if matches(event, wanted)]
    if exact or not wanted:
        return exact
    best = max((score(event, wanted) for event in events), default=0)
    return [event for event in events if best and score(event, wanted) == best]


def upcoming_first(found: list[dict[str, Any]], turn: Turn) -> list[dict[str, Any]]:
    zone = ZoneInfo(turn.user.timezone)
    ahead = [event for event in found if bounds(event, zone)[1] >= turn.now]
    return ahead if len(ahead) == 1 else found


async def find(turn: Turn, match: str, on: str | None) -> dict[str, Any]:
    """The one event the user means, by title and attendees from a week back to a month ahead.
    A weekday in the match or the day it is on now narrows the search; asks when there are
    none or several."""
    zone = ZoneInfo(turn.user.timezone)
    events = await around(turn)
    wanted = words(match)
    days = weekdays(wanted)
    if days:
        events = [event for event in events if bounds(event, zone)[0].weekday() in days]
    found = candidates(events, described(wanted))
    if on:
        found = [e for e in found if bounds(e, zone)[0].date().isoformat() == on] or found
    found = upcoming_first(found, turn)
    if not found:
        raise JobError(f"I found no event matching '{match}' between last week and next month.")
    if len(found) > 1:
        options = "\n".join(f"- {span(e, zone)} {e.get('title', '')}" for e in found)
        raise JobError(f"Several events match '{match}':\n{options}\nWhich one do you mean?")
    return found[0]


async def target(turn: Turn, match: str, on: str | None, new_date: str | None) -> Target:
    """The event from this chat's context when the words point at it, else a calendar search.
    The new date never narrows the search."""
    known = await from_context(turn, match)
    if known is not None:
        return known
    return Target(await find(turn, match, None if on == new_date else on))


def moved(event: dict[str, Any], intent: UpdateEvent, zone: ZoneInfo) -> tuple[datetime, datetime]:
    """New start and end: a new time keeps the date, a new date keeps the time, and the length
    stays unless a new end or length is given."""
    opens, closes = bounds(event, zone)
    if intent.new_start is None and intent.new_end is not None:
        intent = intent.model_copy(update={"new_start": intent.new_end, "new_end": None})
    day = date.fromisoformat(intent.new_date) if intent.new_date else opens.date()
    clock = time.fromisoformat(intent.new_start) if intent.new_start else opens.time()
    start = datetime.combine(day, clock, zone)
    if intent.new_end and (intent.new_start is None or intent.new_end > intent.new_start):
        return start, datetime.combine(day, time.fromisoformat(intent.new_end), zone)
    if intent.duration_minutes:
        return start, start + timedelta(minutes=intent.duration_minutes)
    return start, start + (closes - opens)


def supersede(turn: Turn, card: Approval) -> None:
    try:
        transition_from_pending(turn.session, card, SUPERSEDED)
    except NotPending:
        return


def request(turn: Turn, result: Any, preview: str) -> None:
    if not is_approval_object(result):
        raise JobError(f"I could not prepare the change: {result}")
    approval = create(
        turn.session, turn.user.id, "google", result["action"], result["payload"], preview
    )
    turn.requested(approval)
    turn.note(approval_id=approval.id, event_id=result["payload"].get("event_id"))


async def repropose(turn: Turn, card: Approval, intent: UpdateEvent) -> None:
    """An event still waiting for Create is moved by replacing its card."""
    zone = ZoneInfo(turn.user.timezone)
    payload = zoned(json.loads(card.payload_json), zone)
    start, end = moved(payload, intent, zone)
    title = intent.new_title or str(payload.get("title", ""))
    args = {
        "title": title,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "attendees": payload.get("attendees", []),
        "description": payload.get("description", ""),
        "location": payload.get("location", ""),
        "timezone": turn.user.timezone,
    }
    result = await turn.call("google", "cal_create", args)
    if not is_approval_object(result):
        raise JobError(f"I could not prepare the event: {result}")
    fresh = create_from_tool_result(turn.session, turn.user.id, "google", result)
    supersede(turn, card)
    turn.requested(fresh)
    turn.note(approval_id=fresh.id)
    turn.say(
        f"Moved it: '{title}' on {start:%a %d %b} {start:%H:%M}-{end:%H:%M} is ready. "
        "Edit it or press Create."
    )


async def update(turn: Turn, intent: UpdateEvent) -> None:
    changes = (intent.new_date, intent.new_start, intent.new_end, intent.new_title)
    if not any(changes) and not intent.duration_minutes:
        raise JobError("What should change? Give me a new day, time or title.")
    found = await target(turn, intent.match, intent.date, intent.new_date)
    if found.card is not None and found.card.action == "cal_create":
        await repropose(turn, found.card, intent)
        return
    zone = ZoneInfo(turn.user.timezone)
    event = found.event
    title = str(event.get("title", ""))
    start, end = moved(event, intent, zone)
    args: dict[str, Any] = {"event_id": event["id"], "timezone": turn.user.timezone}

    after = f"{start:%a %d %b} {start:%H:%M}-{end:%H:%M}"
    if (start, end) != bounds(event, zone):
        args |= {"start": start.isoformat(), "end": end.isoformat()}
    if intent.new_title:
        args["title"] = intent.new_title
    renamed = f" and rename it '{intent.new_title}'" if intent.new_title else ""
    preview = f"Move '{title}' from {span(event, zone)} to {after}{renamed}"
    request(turn, await turn.call("google", "cal_update", args), preview)
    if found.card is not None:
        supersede(turn, found.card)
    turn.say(f"Ready to {preview[0].lower()}{preview[1:]}. Press Approve to apply it, or Reject.")


async def cancel(turn: Turn, intent: CancelEvent) -> None:
    zone = ZoneInfo(turn.user.timezone)
    found = await target(turn, intent.match, intent.date, None)
    event = found.event
    if found.card is not None and found.card.action == "cal_create":
        supersede(turn, found.card)
        turn.say(f"Dropped the proposed event '{event.get('title', '')}'. Nothing was booked.")
        return
    preview = f"Delete '{event.get('title', '')}' on {span(event, zone)}"
    request(turn, await turn.call("google", "cal_delete", {"event_id": event["id"]}), preview)
    turn.say(f"Ready to {preview[0].lower()}{preview[1:]}. Press Approve to delete it, or Reject.")
