"""Stand-in for homer-mcp-system: fixed time answers."""

from datetime import datetime
from zoneinfo import ZoneInfo

from fastmcp import FastMCP

server = FastMCP("homer-mcp-system")


@server.tool
def health() -> dict[str, object]:
    """Reports whether the server is up."""
    return {"ok": True, "version": "fake"}


@server.tool
def now(timezone: str = "UTC") -> str:
    """Returns the current time in the given timezone as ISO 8601."""
    return datetime.now(ZoneInfo(timezone)).isoformat(timespec="seconds")


@server.tool
def parse_datetime(text: str, timezone: str = "UTC") -> str | None:
    """Turns natural-language time into ISO 8601. Always answers tomorrow 09:00 here."""
    return "2026-10-17T09:00:00"


if __name__ == "__main__":
    server.run()
