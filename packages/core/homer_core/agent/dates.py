import re
from datetime import date, datetime, timedelta
from typing import Literal

DateFormat = Literal["DD/MM", "MM/DD"]
TABLE_DAYS = 14
STALE_DAYS = 30
US_ZONES = frozenset(
    {
        "America/New_York",
        "America/Chicago",
        "America/Denver",
        "America/Phoenix",
        "America/Los_Angeles",
        "America/Anchorage",
        "America/Juneau",
        "America/Boise",
        "America/Detroit",
        "America/Adak",
        "America/Nome",
        "America/Sitka",
        "America/Yakutat",
        "America/Metlakatla",
        "America/Menominee",
        "Pacific/Honolulu",
        "US/Eastern",
        "US/Central",
        "US/Mountain",
        "US/Pacific",
        "US/Alaska",
        "US/Hawaii",
        "US/Arizona",
    }
)
US_ZONE_PREFIXES = ("America/Indiana/", "America/Kentucky/", "America/North_Dakota/")
WEEKDAY_WORDS = {
    "monday": 0,
    "mon": 0,
    "tuesday": 1,
    "tues": 1,
    "tue": 1,
    "wednesday": 2,
    "weds": 2,
    "wed": 2,
    "thursday": 3,
    "thurs": 3,
    "thur": 3,
    "thu": 3,
    "friday": 4,
    "fri": 4,
    "saturday": 5,
    "sunday": 6,
}
WEEKDAY = re.compile(r"\b(" + "|".join(WEEKDAY_WORDS) + r")\b", re.IGNORECASE)
NEXT_WEEKDAY = re.compile(r"\bnext\s+(" + "|".join(WEEKDAY_WORDS) + r")\b", re.IGNORECASE)
NEXT_WEEK = re.compile(r"\bnext week\b", re.IGNORECASE)
NUMERIC = re.compile(
    r"(?<![\d:/.])(?:(\d{1,2})/(\d{1,2})(?:/(\d{4}|\d{2}))?|(\d{1,2})\.(\d{1,2})\.(\d{4}|\d{2}))"
    r"(?![\d:/.])(?!\s*(?:hours?|hrs?)\b)",
    re.IGNORECASE,
)
DAY_AFTER = re.compile(r"\b(?:the )?(?:day|one) after\b(?!\s+tomorrow)|\bthe next day\b", re.I)
MONTH_WORDS = r"jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec"
CLOCK_TIME = re.compile(
    r"(?<![\d/.:])(?P<h12>\d{1,2})(?:[:.](?P<m12>\d{2}))?\s*(?P<half>[ap])\.?m\b\.?"
    r"|(?<![\d/.:])(?P<h24>\d{1,2}):(?P<m24>\d{2})(?![\d/:])"
    r"|\b(?:at|to|till|until|by)\s+(?P<bare>\d{1,2})(?![\d:/.]|\s*(?:st|nd|rd|th|%|"
    + MONTH_WORDS
    + r"|min|mins|minutes?|h|hrs?|hours?|days?|weeks?|people|percent)\b)",
    re.IGNORECASE,
)
AFTERNOON_HOURS = 7
AMOUNT = r"(?P<amount>\d+(?:\.\d+)?|an?|one|two|three|half an?|a half)"
UNIT = r"(?P<unit>hours?|hrs?|h|minutes?|mins?|m)"
RELATIVE = (
    re.compile(
        rf"\b(?:in|after)\s+(?:about\s+)?{AMOUNT}\s*{UNIT}\b(?!\s+(?:long|meeting|call|slot))",
        re.IGNORECASE,
    ),
    re.compile(rf"\b{AMOUNT}\s*{UNIT}\s+from now\b", re.IGNORECASE),
)
WORD_AMOUNTS = {"a": 1.0, "an": 1.0, "one": 1.0, "two": 2.0, "three": 3.0}
WEEKEND = 5
ROUND_MINUTES = 5


def default_format(timezone: str) -> DateFormat:
    us = timezone in US_ZONES or timezone.startswith(US_ZONE_PREFIXES)
    return "MM/DD" if us else "DD/MM"


def describe(day: date) -> str:
    return f"{day:%A} {day.isoformat()}"


def monday_of(day: date) -> date:
    return day - timedelta(days=day.weekday())


def this_week(today: date) -> tuple[date, date]:
    """Monday to Sunday of the week holding today; on a Saturday or Sunday the rest of the
    weekend and the coming week, which is what "this week" means then."""
    monday = monday_of(today)
    if today.weekday() >= WEEKEND:
        return today, monday + timedelta(days=13)
    return monday, monday + timedelta(days=6)


def date_table(now: datetime) -> str:
    """Fourteen days with weekday names and the named week spans, for the model to copy from."""
    today = now.date()
    monday = monday_of(today)
    saturday = monday + timedelta(days=5)
    lines = [f"today: {describe(today)}", f"tomorrow: {describe(today + timedelta(days=1))}"]
    lines += [describe(today + timedelta(days=n)) for n in range(2, TABLE_DAYS)]
    lines.append(f"this week: {monday.isoformat()} to {(monday + timedelta(days=6)).isoformat()}")
    lines.append(
        f"next week: {(monday + timedelta(days=7)).isoformat()} to "
        f"{(monday + timedelta(days=13)).isoformat()}"
    )
    sunday = saturday + timedelta(days=1)
    lines.append(f"this weekend: {saturday.isoformat()} to {sunday.isoformat()}")
    return "\n".join(lines)


def numeric_date(message: str, today: date, form: DateFormat) -> date | None:
    """The one numeric date in the message ('12/11', '12.11.2026'), read in the user's order."""
    found = NUMERIC.findall(message)
    if len(found) != 1:
        return None
    first, second, year = [a or b for a, b in zip(found[0][:3], found[0][3:], strict=True)]
    day, month = (int(first), int(second)) if form == "DD/MM" else (int(second), int(first))
    full_year = (2000 + int(year) if len(year) == 2 else int(year)) if year else today.year
    try:
        result = date(full_year, month, day)
    except ValueError:
        return None
    if not year and result < today - timedelta(days=STALE_DAYS):
        result = result.replace(year=today.year + 1)
    return result


def weekday_date(message: str, today: date) -> date | None:
    """The date of the one weekday the message names: the next one on or after today."""
    named = {WEEKDAY_WORDS[word.lower()] for word in WEEKDAY.findall(message)}
    if len(named) != 1:
        return None
    weekday = named.pop()
    if NEXT_WEEK.search(message):
        return monday_of(today) + timedelta(days=7 + weekday)
    ahead = (weekday - today.weekday()) % 7
    if ahead == 0 and NEXT_WEEKDAY.search(message):
        ahead = 7
    return today + timedelta(days=ahead)


def numeric_hint(message: str, today: date, form: DateFormat) -> str:
    found = numeric_date(message, today, form)
    if found is None:
        return ""
    raw = NUMERIC.search(message)
    return f"\nIn this message {raw.group(0) if raw else ''} means {describe(found)}."


def stated_times(message: str) -> list[str]:
    """The clock times the message names, as HH:MM: '2pm', '14:30', 'at 11', 'to 3'. A bare
    hour from 1 to 7 is afternoon; the day of a date ('16 nov') is never a time."""
    found = []
    for match in CLOCK_TIME.finditer(message):
        if match["bare"]:
            hour, minute = int(match["bare"]), 0
            hour += 12 if 1 <= hour <= AFTERNOON_HOURS else 0
        elif match["h24"]:
            hour, minute = int(match["h24"]), int(match["m24"])
        else:
            hour, minute = int(match["h12"]) % 12, int(match["m12"] or 0)
            hour += 12 if match["half"].lower() == "p" else 0
        if hour <= 23 and minute <= 59:
            found.append(f"{hour:02d}:{minute:02d}")
    return list(dict.fromkeys(found))


def relative_minutes(message: str) -> int | None:
    """Minutes from now the message names: "in 1 hour" 60, "20 minutes from now" 20, "in half
    an hour" 30; None when it names none."""
    found = next((m for pattern in RELATIVE if (m := pattern.search(message))), None)
    if found is None:
        return None
    amount = found["amount"].lower()
    value = 0.5 if amount.startswith(("half", "a half")) else WORD_AMOUNTS.get(amount)
    value = float(amount) if value is None else value
    hours = found["unit"].lower().startswith("h")
    return round(value * (60 if hours else 1))


def now_line(now: datetime) -> str:
    """ "Now: Saturday 14 Nov 2026, 16:23 PKT", the one clock every prompt states."""
    return f"Now: {now:%A %d %b %Y, %H:%M} {now:%Z}".rstrip()


def from_now(now: datetime, minutes: int) -> datetime:
    """Now plus the minutes, rounded up to the next five minutes."""
    moment = (now + timedelta(minutes=minutes)).replace(second=0, microsecond=0)
    return moment + timedelta(minutes=-moment.minute % ROUND_MINUTES)
