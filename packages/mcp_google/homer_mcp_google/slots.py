from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

Span = tuple[datetime, datetime]
WEEKEND = {5, 6}


def parse_time(value: str, timezone: str | None = None) -> datetime:
    """Parses ISO 8601; a time without an offset is read in `timezone`, or UTC when none."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo:
        return parsed
    try:
        return parsed.replace(tzinfo=ZoneInfo(timezone) if timezone else UTC)
    except ZoneInfoNotFoundError as error:
        raise ValueError(f"unknown timezone {timezone!r}") from error


def parse_working_hours(value: str) -> tuple[time, time]:
    opens, _, closes = value.partition("-")
    return time.fromisoformat(opens.strip()), time.fromisoformat(closes.strip())


def free_slots(
    start: datetime,
    end: datetime,
    busy: list[Span],
    duration: timedelta,
    working_hours: tuple[time, time],
    limit: int = 3,
) -> list[Span]:
    """Earliest gaps of at least `duration` inside working hours on weekdays, up to `limit`."""
    slots: list[Span] = []
    day = start.replace(hour=0, minute=0, second=0, microsecond=0)
    ordered = sorted(busy)
    while day < end and len(slots) < limit:
        if day.weekday() not in WEEKEND:
            window_start = max(
                start, day.replace(hour=working_hours[0].hour, minute=working_hours[0].minute)
            )
            window_end = min(
                end, day.replace(hour=working_hours[1].hour, minute=working_hours[1].minute)
            )
            slots.extend(_gaps(window_start, window_end, ordered, duration))
        day += timedelta(days=1)
    return slots[:limit]


def _gaps(
    window_start: datetime, window_end: datetime, busy: list[Span], duration: timedelta
) -> list[Span]:
    gaps: list[Span] = []
    cursor = window_start
    for busy_start, busy_end in busy:
        if busy_end <= cursor or busy_start >= window_end:
            continue
        if busy_start - cursor >= duration:
            gaps.append((cursor, cursor + duration))
        cursor = max(cursor, busy_end)
    if window_end - cursor >= duration:
        gaps.append((cursor, cursor + duration))
    return gaps
