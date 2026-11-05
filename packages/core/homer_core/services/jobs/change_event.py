from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from homer_core.agent.intents import CancelEvent, UpdateEvent
from homer_core.services.approvals import create, is_approval_object
from homer_core.services.jobs.read_calendar import bounds
from homer_core.services.jobs.recipients import listed
from homer_core.services.jobs.turn import JobError, Turn

SEARCH_DAYS = 30
FILLER = frozenset(
    {"the", "my", "a", "an", "our", "this", "that", "with", "w/", "event", "meeting", "on", "at"}
)


def words(match: str) -> list[str]:
    cleaned = match.lower().replace("'s", " ").replace(",", " ")
    return [word for word in cleaned.split() if word not in FILLER]


def matches(event: dict[str, Any], wanted: list[str]) -> bool:
    text = " ".join([str(event.get("title", "")), *map(str, event.get("attendees", []))]).lower()
    return all(word in text for word in wanted)


def span(event: dict[str, Any], zone: ZoneInfo) -> str:
    opens, closes = bounds(event, zone)
    return f"{opens:%a %d %b} {opens:%H:%M}-{closes:%H:%M}"


async def find(turn: Turn, match: str, on: str | None) -> dict[str, Any]:
    """The one upcoming event the user means; asks when there are none or several."""
    zone = ZoneInfo(turn.user.timezone)
    first = date.fromisoformat(on) if on else turn.now.date()
    last = first + timedelta(days=1 if on else SEARCH_DAYS)
    args = {
        "start": datetime.combine(first, time.min, zone).isoformat(),
        "end": datetime.combine(last, time.min, zone).isoformat(),
    }
    events = listed(await turn.call("google", "cal_list", args), "events")
    wanted = words(match)
    found = [event for event in events if matches(event, wanted)]
    if not found:
        within = f"on {first:%a %d %b}" if on else f"in the next {SEARCH_DAYS} days"
        raise JobError(f"I found no event matching '{match}' {within}.")
    if len(found) > 1:
        options = "\n".join(f"- {span(e, zone)} {e.get('title', '')}" for e in found)
        raise JobError(f"Several events match '{match}':\n{options}\nWhich one do you mean?")
    return found[0]


def moved(event: dict[str, Any], intent: UpdateEvent, zone: ZoneInfo) -> tuple[datetime, datetime]:
    """New start and end: a new time keeps the date, a new date keeps the time, and a missing
    end keeps the length."""
    opens, closes = bounds(event, zone)
    if intent.new_start is None and intent.new_end is not None:
        intent = intent.model_copy(update={"new_start": intent.new_end, "new_end": None})
    day = date.fromisoformat(intent.new_date) if intent.new_date else opens.date()
    clock = time.fromisoformat(intent.new_start) if intent.new_start else opens.time()
    start = datetime.combine(day, clock, zone)
    if intent.new_end and (intent.new_start is None or intent.new_end > intent.new_start):
        return start, datetime.combine(day, time.fromisoformat(intent.new_end), zone)
    return start, start + (closes - opens)


def request(turn: Turn, result: Any, preview: str) -> None:
    if not is_approval_object(result):
        raise JobError(f"I could not prepare the change: {result}")
    approval = create(
        turn.session, turn.user.id, "google", result["action"], result["payload"], preview
    )
    turn.requested(approval)
    turn.note(approval_id=approval.id, event_id=result["payload"].get("event_id"))


async def update(turn: Turn, intent: UpdateEvent) -> None:
    if not (intent.new_date or intent.new_start or intent.new_end or intent.new_title):
        raise JobError("What should change? Give me a new day, time or title.")
    zone = ZoneInfo(turn.user.timezone)
    event = await find(turn, intent.match, intent.date)
    title = str(event.get("title", ""))
    start, end = moved(event, intent, zone)
    args: dict[str, Any] = {"event_id": event["id"]}
    after = f"{start:%a %d %b} {start:%H:%M}-{end:%H:%M}"
    if (start, end) != bounds(event, zone):
        args |= {"start": start.isoformat(), "end": end.isoformat()}
    if intent.new_title:
        args["title"] = intent.new_title
    renamed = f" and rename it '{intent.new_title}'" if intent.new_title else ""
    preview = f"Move '{title}' from {span(event, zone)} to {after}{renamed}"
    request(turn, await turn.call("google", "cal_update", args), preview)
    turn.say(f"Ready to {preview[0].lower()}{preview[1:]}. Press Approve to apply it, or Reject.")


async def cancel(turn: Turn, intent: CancelEvent) -> None:
    zone = ZoneInfo(turn.user.timezone)
    event = await find(turn, intent.match, intent.date)
    preview = f"Delete '{event.get('title', '')}' on {span(event, zone)}"
    request(turn, await turn.call("google", "cal_delete", {"event_id": event["id"]}), preview)
    turn.say(f"Ready to {preview[0].lower()}{preview[1:]}. Press Approve to delete it, or Reject.")
