from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from homer_core.agent.intents import ReadCalendar
from homer_core.services.jobs.recipients import listed
from homer_core.services.jobs.turn import Turn

SHORT_LIST = 8
PHRASE_PROMPT = """Answer the user's question about their calendar from this list of events only.
Never mention an event that is not in the list. Be brief.
{period}:
{events}"""


def days_of(intent: ReadCalendar, today: date) -> tuple[date, date, str]:
    """First day, the day after the last, and how to name the period."""
    match intent.range:
        case "tomorrow":
            first = today + timedelta(days=1)
            return first, first + timedelta(days=1), f"Tomorrow, {first:%A %d %B}"
        case "this_week":
            monday = today - timedelta(days=today.weekday())
            return monday, monday + timedelta(days=7), f"This week, from {monday:%A %d %B}"
        case "date" | "range" if intent.date:
            first = date.fromisoformat(intent.date)
            last = date.fromisoformat(intent.end_date) if intent.end_date else first
            last = max(last, first)
            name = f"{first:%A %d %B}" + (f" to {last:%A %d %B}" if last > first else "")
            return first, last + timedelta(days=1), name
    return today, today + timedelta(days=1), f"Today, {today:%A %d %B}"


def local(value: str, zone: ZoneInfo) -> datetime:
    """Google sends an offset; a time without one is UTC."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return (parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)).astimezone(zone)


def line(event: dict[str, Any], zone: ZoneInfo, with_day: bool) -> str:
    start, end = str(event.get("start", "")), str(event.get("end", ""))
    title = event.get("title") or "(no title)"
    where = f" ({event['location']})" if event.get("location") else ""
    if "T" not in start:
        day = f"{date.fromisoformat(start):%a %d %b} " if with_day else ""
        return f"- {day}all day: {title}{where}"
    opens, closes = local(start, zone), local(end, zone)
    day = f"{opens:%a %d %b} " if with_day else ""
    return f"- {day}{opens:%H:%M}-{closes:%H:%M} {title}{where}"


async def run(turn: Turn, intent: ReadCalendar) -> None:
    zone = ZoneInfo(turn.user.timezone)
    first, after, period = days_of(intent, turn.now.date())
    args = {
        "start": datetime.combine(first, time.min, zone).isoformat(),
        "end": datetime.combine(after, time.min, zone).isoformat(),
    }
    events = listed(await turn.call("google", "cal_list", args), "events")
    if not events:
        turn.say(f"{period}: nothing on your calendar.")
        return
    lines = "\n".join(line(e, zone, after - first > timedelta(days=1)) for e in events)
    if len(events) <= SHORT_LIST:
        turn.say(f"{period}:\n{lines}")
        return
    await turn.stream(turn.message, PHRASE_PROMPT.format(period=period, events=lines))
