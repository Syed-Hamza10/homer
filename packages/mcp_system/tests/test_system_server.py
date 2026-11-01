import os
import sys
from collections.abc import AsyncIterator
from datetime import datetime

import pytest
from fastmcp import Client
from fastmcp.client.transports import StdioTransport

KARACHI = "Asia/Karachi"
BASE = "2026-10-16T12:00:00+05:00"


@pytest.fixture
async def client() -> AsyncIterator[Client]:
    transport = StdioTransport(
        sys.executable, ["-m", "homer_mcp_system.server"], env=dict(os.environ)
    )
    async with Client(transport) as c:
        yield c


async def test_health(client: Client) -> None:
    result = await client.call_tool("health")
    assert result.data["ok"] is True
    assert isinstance(result.data["version"], str)


async def test_tools_are_listed(client: Client) -> None:
    names = {tool.name for tool in await client.list_tools()}
    assert names == {"health", "now", "parse_datetime"}


async def test_now_in_karachi(client: Client) -> None:
    result = await client.call_tool("now", {"timezone": KARACHI})
    current = datetime.fromisoformat(result.data["iso"])
    assert result.data["iso"].endswith("+05:00")
    assert result.data["weekday"] == current.strftime("%A")
    assert abs((datetime.now(current.tzinfo) - current).total_seconds()) < 5


async def test_now_unknown_timezone(client: Client) -> None:
    result = await client.call_tool("now", {"timezone": "Mars/Olympus"})
    assert result.data == {"error": "unknown_timezone"}


THURSDAY = "2026-10-15T12:00:00+05:00"


@pytest.mark.parametrize(
    ("text", "now", "expected"),
    [
        ("tomorrow at 9am", BASE, "2026-10-17T09:00:00+05:00"),
        ("next friday 3pm", BASE, "2026-10-23T15:00:00+05:00"),
        ("next friday 3pm", THURSDAY, "2026-10-23T15:00:00+05:00"),
        ("next thursday at 10:30", THURSDAY, "2026-10-22T10:30:00+05:00"),
        ("next wednesday", THURSDAY, "2026-10-28T00:00:00+05:00"),
        ("friday 3pm", THURSDAY, "2026-10-16T15:00:00+05:00"),
        ("in 2 hours", BASE, "2026-10-16T14:00:00+05:00"),
    ],
)
async def test_parse_datetime(client: Client, text: str, now: str, expected: str) -> None:
    args = {"text": text, "timezone": KARACHI, "now": now}
    result = await client.call_tool("parse_datetime", args)
    assert result.data == {"iso": expected}


async def test_parse_datetime_garbage(client: Client) -> None:
    args = {"text": "asdkjh qwe", "timezone": KARACHI, "now": BASE}
    result = await client.call_tool("parse_datetime", args)
    assert result.data == {"error": "unparseable"}


async def test_parse_datetime_without_now_uses_current_time(client: Client) -> None:
    result = await client.call_tool("parse_datetime", {"text": "in 1 hour", "timezone": KARACHI})
    parsed = datetime.fromisoformat(result.data["iso"])
    delta = (parsed - datetime.now(parsed.tzinfo)).total_seconds()
    assert 3500 < delta <= 3600
