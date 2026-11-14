from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from homer_core.mcp.manager import McpManager

LONDON = ZoneInfo("Europe/London")


@pytest.fixture
def mcp(sim_mcp: McpManager) -> McpManager:
    return sim_mcp


def week() -> tuple[datetime, datetime]:
    now = datetime.now(UTC)
    monday = (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return monday, monday + timedelta(days=7)


def week_params() -> dict[str, str]:
    monday, sunday = week()
    return {"start": monday.isoformat(), "end": sunday.isoformat()}


def sim_events(sim: FastAPI) -> int:
    return sim.state.sim.counts()["events"]


def local(value: datetime) -> str:
    return value.astimezone(LONDON).strftime("%Y-%m-%dT%H:%M")


def test_events_in_range_come_from_google_with_details(logged_in: TestClient) -> None:
    found = logged_in.get("/api/calendar/events", params=week_params()).json()
    assert found["source"] == "google"
    assert len(found["events"]) == 6
    by_id = {event["id"]: event for event in found["events"]}
    assert by_id["evt_002"]["video_link"] == "https://meet.example.test/abc-defg-hij"
    assert by_id["evt_003"]["people"][0]["response"] == "accepted"
    assert by_id["evt_001"]["all_day"] is False
    detail = logged_in.get("/api/calendar/events/evt_005").json()
    assert detail["title"] == "Review quarterly deck"
    assert detail["attendees"] == ["elena.marchetti@example.test"]


def test_range_must_be_aware_and_bounded(logged_in: TestClient) -> None:
    monday, _ = week()
    naive = {"start": "2026-11-02T00:00:00", "end": "2026-11-03T00:00:00"}
    assert logged_in.get("/api/calendar/events", params=naive).status_code == 400
    long = {"start": monday.isoformat(), "end": (monday + timedelta(days=90)).isoformat()}
    assert logged_in.get("/api/calendar/events", params=long).status_code == 400


def test_range_falls_back_to_the_cache_when_google_fails(
    logged_in: TestClient, origin: dict[str, str], tmp_path: Path
) -> None:
    logged_in.post("/api/calendar/refresh", headers=origin)
    (tmp_path / "google" / "credentials" / "google_token.json").unlink()
    now = datetime.now(UTC)
    params = {"start": now.isoformat(), "end": (now + timedelta(days=14)).isoformat()}
    found = logged_in.get("/api/calendar/events", params=params).json()
    assert found["source"] == "cache"


def test_create_asks_for_approval_in_the_users_timezone(
    logged_in: TestClient, origin: dict[str, str], sim: FastAPI
) -> None:
    before = sim_events(sim)
    body = {
        "title": "Design review",
        "start": "2026-11-20T10:00",
        "end": "2026-11-20T10:45",
        "attendees": ["maya.lindqvist@example.test"],
        "description": "Walk through the mockups.",
    }
    approval = logged_in.post("/api/calendar/events", json=body, headers=origin).json()
    assert approval["action"] == "cal_create" and approval["status"] == "pending"
    assert approval["payload"]["start"] == "2026-11-20T10:00:00+00:00"
    assert "maya.lindqvist@example.test" in approval["preview"]
    assert sim_events(sim) == before
    logged_in.post(f"/api/approvals/{approval['id']}/approve", headers=origin)
    assert sim_events(sim) == before + 1


def test_create_validates_times_and_addresses(
    logged_in: TestClient, origin: dict[str, str]
) -> None:
    backwards = {"title": "X", "start": "2026-11-20T11:00", "end": "2026-11-20T10:00"}
    assert logged_in.post("/api/calendar/events", json=backwards, headers=origin).status_code == 422
    bad = {"title": "X", "start": "2026-11-20T10:00", "end": "2026-11-20T11:00", "attendees": ["x"]}
    assert logged_in.post("/api/calendar/events", json=bad, headers=origin).status_code == 422


def test_move_asks_for_approval_with_before_and_after(
    logged_in: TestClient, origin: dict[str, str], sim: FastAPI
) -> None:
    current = logged_in.get("/api/calendar/events/evt_003").json()
    opens = datetime.fromisoformat(current["start"])
    later = opens + timedelta(hours=2)
    body = {"start": local(later), "end": local(later + timedelta(hours=1))}
    approval = logged_in.patch("/api/calendar/events/evt_003", json=body, headers=origin).json()
    assert approval["action"] == "cal_update"
    before = opens.astimezone(LONDON)
    after = later.astimezone(LONDON)
    assert approval["preview"].startswith(
        f"Move 'Call with Samuel Okafor' from {before:%a %d %b %H:%M}-"
    )
    assert f"to {after:%a %d %b %H:%M}-" in approval["preview"]
    assert set(approval["payload"]["changes"]) == {"start", "end"}
    assert sim.state.sim.calendar.get("evt_003")["start"]["dateTime"] == current["start"]
    logged_in.post(f"/api/approvals/{approval['id']}/approve", headers=origin)
    moved = logged_in.get("/api/calendar/events/evt_003").json()
    assert datetime.fromisoformat(moved["start"]) == later


def test_edit_sends_only_changed_fields(logged_in: TestClient, origin: dict[str, str]) -> None:
    current = logged_in.get("/api/calendar/events/evt_006").json()
    same = {
        "title": current["title"],
        "start": local(datetime.fromisoformat(current["start"])),
        "end": local(datetime.fromisoformat(current["end"])),
        "attendees": current["attendees"],
    }
    response = logged_in.patch("/api/calendar/events/evt_006", json=same, headers=origin)
    assert response.status_code == 422
    renamed = {**same, "title": "Lunch with Tomas and Maya"}
    approval = logged_in.patch("/api/calendar/events/evt_006", json=renamed, headers=origin).json()
    assert approval["payload"]["changes"] == {"title": "Lunch with Tomas and Maya"}
    assert "Title: Lunch with Tomas -> Lunch with Tomas and Maya" in approval["preview"]


def test_cancel_asks_for_approval(
    logged_in: TestClient, origin: dict[str, str], sim: FastAPI
) -> None:
    before = sim_events(sim)
    approval = logged_in.post("/api/calendar/events/evt_005/cancel", headers=origin).json()
    assert approval["action"] == "cal_delete"
    assert approval["preview"].startswith("Delete 'Review quarterly deck' on ")
    assert approval["preview"].endswith(
        "with elena.marchetti@example.test\nAttendees will be notified."
    )
    assert approval["payload"]["send_updates"] == "all"
    assert sim_events(sim) == before
    logged_in.post(f"/api/approvals/{approval['id']}/approve", headers=origin)
    assert sim_events(sim) == before - 1


def test_find_a_time_with_attendees(logged_in: TestClient, origin: dict[str, str]) -> None:
    body = {
        "duration_minutes": 30,
        "days": 14,
        "attendees": ["samuel.okafor@example.test"],
        "limit": 6,
    }
    slots = logged_in.post("/api/calendar/find-slot", json=body, headers=origin).json()
    assert 1 <= len(slots) <= 6
    for slot in slots:
        start = datetime.fromisoformat(slot["start"])
        assert start.utcoffset() == LONDON.utcoffset(start.replace(tzinfo=None))
        assert start.weekday() < 5


def test_google_emails_attendees_on_create_move_and_cancel(
    logged_in: TestClient, origin: dict[str, str], sim: FastAPI
) -> None:
    def approve(approval: dict[str, Any]) -> dict[str, Any]:
        logged_in.post(f"/api/approvals/{approval['id']}/approve", headers=origin)
        return sim.state.sim.calendar_writes[-1]

    body = {
        "title": "Design review",
        "start": "2026-11-20T10:00",
        "end": "2026-11-20T10:45",
        "attendees": ["maya.lindqvist@example.test"],
    }
    created = logged_in.post("/api/calendar/events", json=body, headers=origin).json()
    assert created["preview"].endswith("Attendees will be notified.")
    insert = approve(created)
    assert insert["method"] == "insert" and insert["send_updates"] == "all"
    assert insert["body"]["start"] == {
        "dateTime": "2026-11-20T10:00:00+00:00",
        "timeZone": "Europe/London",
    }

    event_id = insert["event_id"]
    later = {"start": "2026-11-20T14:00", "end": "2026-11-20T14:45"}
    moved = logged_in.patch(f"/api/calendar/events/{event_id}", json=later, headers=origin).json()
    assert moved["preview"].endswith("Attendees will be notified.")
    patch = approve(moved)
    assert patch["method"] == "patch" and patch["send_updates"] == "all"
    assert patch["body"]["start"] == {
        "dateTime": "2026-11-20T14:00:00+00:00",
        "timeZone": "Europe/London",
    }
    assert patch["body"]["end"] == {
        "dateTime": "2026-11-20T14:45:00+00:00",
        "timeZone": "Europe/London",
    }
    assert "attendees" not in patch["body"]
    attendees = sim.state.sim.calendar.get(event_id)["attendees"]
    assert [a["email"] for a in attendees] == ["maya.lindqvist@example.test"]

    cancelled = logged_in.post(f"/api/calendar/events/{event_id}/cancel", headers=origin).json()
    assert cancelled["preview"].endswith("Attendees will be notified.")
    delete = approve(cancelled)
    assert delete["method"] == "delete" and delete["send_updates"] == "all"


def test_personal_events_send_no_invitations(
    logged_in: TestClient, origin: dict[str, str], sim: FastAPI
) -> None:
    def approve(approval: dict[str, Any]) -> dict[str, Any]:
        assert "notified" not in approval["preview"]
        logged_in.post(f"/api/approvals/{approval['id']}/approve", headers=origin)
        return sim.state.sim.calendar_writes[-1]

    body = {
        "title": "Focus time",
        "start": "2026-11-20T10:00",
        "end": "2026-11-20T11:00",
        "attendees": ["jordan.reyes@example.test"],
    }
    insert = approve(logged_in.post("/api/calendar/events", json=body, headers=origin).json())
    assert insert["send_updates"] == "none"
    event_id = insert["event_id"]
    later = {"start": "2026-11-20T15:00", "end": "2026-11-20T16:00"}
    moved = logged_in.patch(f"/api/calendar/events/{event_id}", json=later, headers=origin)
    assert approve(moved.json())["send_updates"] == "none"
    cancelled = logged_in.post(f"/api/calendar/events/{event_id}/cancel", headers=origin)
    assert approve(cancelled.json())["send_updates"] == "none"
