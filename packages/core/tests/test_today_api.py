from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from homer_core.mcp.manager import McpManager
from homer_core.services.calendar import local_day_bounds
from homer_core.services.day import part_of_day

TIMEZONE = "Europe/London"


@pytest.fixture
def mcp(sim_mcp: McpManager) -> McpManager:
    return sim_mcp


def earlier_today(now: datetime) -> tuple[datetime, datetime]:
    start, _ = local_day_bounds(now, TIMEZONE)
    opens = max(start, now - timedelta(hours=2))
    return opens, opens + timedelta(minutes=30)


def test_card_shows_an_event_made_earlier_today_live(sim: FastAPI, logged_in: TestClient) -> None:
    now = datetime.now(UTC)
    opens, closes = earlier_today(now)
    sim.state.sim.calendar.insert(
        {
            "summary": "Made a minute ago",
            "start": {"dateTime": opens.isoformat()},
            "end": {"dateTime": closes.isoformat()},
        },
        now,
    )
    today = logged_in.get("/api/today").json()
    card = today["card"]
    assert card["live"] is True and card["as_of"] is None
    assert "Made a minute ago" in [meeting["title"] for meeting in card["meetings"]]
    inbox = sim.state.sim.mailbox.label_counts("INBOX")
    assert card["unread"] == inbox["threadsUnread"]
    assert card["needs_you"] >= len(card["emails"])
    assert card["greeting"] == f"Good {part_of_day(now, TIMEZONE)}, Tester."
    assert today["background_refresh"] is False
    assert today["showing"] in ("morning", "digest")


def test_brief_uses_the_same_live_numbers(
    sim: FastAPI, logged_in: TestClient, origin: dict[str, str]
) -> None:
    brief = logged_in.post("/api/today/brief", headers=origin).json()
    card = logged_in.get("/api/today").json()["card"]
    assert f"{card['unread']} unread email" in brief["content"]
    assert "cache" not in brief["content"] and "@" not in brief["content"]
    assert brief["generated_at"]
