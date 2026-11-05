from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from homer_core.agent.dates import monday_of
from homer_core.agent.intents import NEXT_EVENT, ReadCalendar
from homer_core.services.jobs.recipients import listed
from homer_core.services.jobs.turn import Turn

LONG_LIST = 25
DEFAULT_DAYS = 7
INSTANT_MINUTES = 30
PHRASE_PROMPT = """Answer the person's question about their calendar, talking to them as "you",
from this list of events only. Never mention an event that is not in the list, "the list" or
"the user". Be brief.
{period}:
{events}"""


def day_name(day: date) -> str:
    return f"{day:%A %d %B}"


def span_name(first: date, last: date) -> str:
    return day_name(first) + (f" to {day_name(last)}" if last > first else "")


def days_of(intent: ReadCalendar, today: date) -> tuple[date, date, str]:
    """First day, the day after the last, and how to name the period."""
    monday = monday_of(today)
    match intent.range:
        case "tomorrow":
            first = today + timedelta(days=1)
            return first, first + timedelta(days=1), f"Tomorrow, {day_name(first)}"
        case "this_week":
            return monday, monday + timedelta(days=7), f"This week, from {day_name(monday)}"
        case "next_week":
            first, last = monday + timedelta(days=7), monday + timedelta(days=13)
            return first, last + timedelta(days=1), f"Next week, {span_name(first, last)}"
        case "this_weekend":
            first = max(monday + timedelta(days=5), today)
            last = monday + timedelta(days=6)
            return first, last + timedelta(days=1), f"This weekend, {span_name(first, last)}"
        case "next_n_days":
            last = today + timedelta(days=(intent.days or DEFAULT_DAYS) - 1)
            return today, last + timedelta(days=1), span_name(today, last)
        case "date" | "range" if intent.date:
            first = date.fromisoformat(intent.date)
            last = date.fromisoformat(intent.end_date) if intent.end_date else first
            last = max(last, first)
            return first, last + timedelta(days=1), span_name(first, last)
    return today, today + timedelta(days=1), f"Today, {day_name(today)}"


def local(value: str, zone: ZoneInfo) -> datetime:
    """Google sends an offset; a time without one is UTC."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return (parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)).astimezone(zone)


def bounds(event: dict[str, Any], zone: ZoneInfo) -> tuple[datetime, datetime]:
    start, end = str(event.get("start", "")), str(event.get("end", ""))
    if "T" not in start:
        opens = datetime.combine(date.fromisoformat(start), time.min, zone)
        closes = datetime.combine(date.fromisoformat(end or start), time.min, zone)
        return opens, max(closes, opens + timedelta(days=1))
    return local(start, zone), local(end, zone)


def line(event: dict[str, Any], zone: ZoneInfo, with_day: bool) -> str:
    start = str(event.get("start", ""))
    title = event.get("title") or "(no title)"
    where = f" ({event['location']})" if event.get("location") else ""
    if "T" not in start:
        day = f"{date.fromisoformat(start):%a %d %b} " if with_day else ""
        return f"- {day}all day: {title}{where}"
    opens, closes = bounds(event, zone)
    day = f"{opens:%a %d %b} " if with_day else ""
    return f"- {day}{opens:%H:%M}-{closes:%H:%M} {title}{where}"


def mentions(event: dict[str, Any], words: str) -> bool:
    """Every word appears in the title or an attendee address, ignoring case."""
    text = " ".join([str(event.get("title", "")), *map(str, event.get("attendees", []))]).lower()
    return all(word in text for word in words.lower().split())


def wanted(event: dict[str, Any], intent: ReadCalendar) -> bool:
    if intent.person and not mentions(event, intent.person.split()[0]):
        return False
    return not intent.title_contains or mentions(event, intent.title_contains)


def hours(intent: ReadCalendar) -> tuple[time, time] | None:
    if intent.start is None:
        return None
    opens = time.fromisoformat(intent.start)
    if intent.end is not None and intent.end > intent.start:
        return opens, time.fromisoformat(intent.end)
    later = (datetime.combine(date.min, opens) + timedelta(minutes=INSTANT_MINUTES)).time()
    return opens, later if later > opens else time.max


def in_hours(event: dict[str, Any], zone: ZoneInfo, window: tuple[time, time]) -> bool:
    opens, closes = bounds(event, zone)
    lower = datetime.combine(opens.date(), window[0], zone)
    upper = datetime.combine(opens.date(), window[1], zone)
    return opens < upper and closes > lower


def counted(events: int) -> str:
    return "1 event" if events == 1 else f"{events} events"


def heading(intent: ReadCalendar, period: str, window: tuple[time, time] | None) -> str:
    when = f"{period}, {window[0]:%H:%M}-{window[1]:%H:%M}" if window else period
    who = f" with {intent.person}" if intent.person else ""
    about = f" matching '{intent.title_contains}'" if intent.title_contains else ""
    return f"{when}{who}{about}"


def availability(intent: ReadCalendar, busy: bool) -> str:
    """Yes or no to the question as asked, then the state in words."""
    yes = busy if intent.asks_if == "busy" else not busy
    return f"{'Yes' if yes else 'No'}, you are {'busy' if busy else 'free'}."


def next_one(turn: Turn, events: list[dict[str, Any]], period: str, zone: ZoneInfo) -> str:
    """Only the next event that has not started yet."""
    ahead = [event for event in events if bounds(event, zone)[0] >= turn.now]
    if not ahead:
        return f"Nothing else on your calendar for {period[:1].lower()}{period[1:]}."
    event = min(ahead, key=lambda e: bounds(e, zone)[0])
    opens, closes = bounds(event, zone)
    day = "today" if opens.date() == turn.now.date() else f"{opens:%A %d %B}"
    where = f" ({event['location']})" if event.get("location") else ""
    title = event.get("title") or "(no title)"
    return f"Your next one is {title}{where}, {day} {opens:%H:%M}-{closes:%H:%M}."


async def run(turn: Turn, intent: ReadCalendar) -> None:
    zone = ZoneInfo(turn.user.timezone)
    first, after, period = days_of(intent, turn.now.date())
    turn.note(date=first.isoformat(), end_date=(after - timedelta(days=1)).isoformat())
    args = {
        "start": datetime.combine(first, time.min, zone).isoformat(),
        "end": datetime.combine(after, time.min, zone).isoformat(),
    }
    events = listed(await turn.call("google", "cal_list", args), "events")
    events = [event for event in events if wanted(event, intent)]
    window = hours(intent)
    if window is not None:
        events = [event for event in events if in_hours(event, zone, window)]
    if NEXT_EVENT.search(turn.message):
        turn.say(next_one(turn, events, period, zone))
        return
    title = heading(intent, period, window)
    lead = f"{availability(intent, bool(events))} " if intent.asks_if else ""
    if not events:
        turn.say(f"{lead}{title}: nothing on your calendar.")
        return
    several_days = after - first > timedelta(days=1)
    lines = "\n".join(line(event, zone, several_days) for event in events)
    if several_days:
        title = f"{title} ({counted(len(events))})"
    if len(events) <= LONG_LIST:
        turn.say(f"{lead}{title}:\n{lines}")
        return
    await turn.stream(turn.message, PHRASE_PROMPT.format(period=title, events=lines))
