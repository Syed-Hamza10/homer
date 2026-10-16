import re
from datetime import datetime
from importlib.metadata import version
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import dateparser
from fastmcp import FastMCP

VERSION = version("achilles-mcp-system")
WEEKDAYS = "monday|tuesday|wednesday|thursday|friday|saturday|sunday"
NEXT_WEEKDAY = re.compile(rf"\bnext\s+(?=(?:{WEEKDAYS})\b)", re.IGNORECASE)

mcp = FastMCP("achilles-system", version=VERSION)


def zone_or_none(timezone: str) -> ZoneInfo | None:
    try:
        return ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError):
        return None


@mcp.tool
def health() -> dict[str, Any]:
    """Reports whether the system server is up and which version it runs."""
    return {"ok": True, "version": VERSION}


@mcp.tool
def now(timezone: str) -> dict[str, Any]:
    """Returns the current time in the given IANA timezone as ISO 8601 plus the weekday name."""
    zone = zone_or_none(timezone)
    if zone is None:
        return {"error": "unknown_timezone"}
    current = datetime.now(zone)
    return {"iso": current.isoformat(timespec="seconds"), "weekday": current.strftime("%A")}


@mcp.tool
def parse_datetime(text: str, timezone: str, now: str | None = None) -> dict[str, Any]:
    """Turns text such as "tomorrow at 9am" into an ISO 8601 instant in the given timezone,
    preferring future dates. Returns an error when the text holds no date."""
    zone = zone_or_none(timezone)
    if zone is None:
        return {"error": "unknown_timezone"}
    base = datetime.fromisoformat(now) if now else datetime.now(zone)
    if base.tzinfo is None:
        base = base.replace(tzinfo=zone)
    settings = {
        "PREFER_DATES_FROM": "future",
        "RETURN_AS_TIMEZONE_AWARE": True,
        "TIMEZONE": timezone,
        "RELATIVE_BASE": base,
    }
    parsed = dateparser.parse(NEXT_WEEKDAY.sub("", text), languages=["en"], settings=settings)
    if parsed is None:
        return {"error": "unparseable"}
    return {"iso": parsed.astimezone(zone).isoformat(timespec="seconds")}


def main() -> None:
    mcp.run(show_banner=False)


if __name__ == "__main__":
    main()
