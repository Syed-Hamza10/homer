from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from types import ModuleType, SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastmcp.client import Client
from pydantic_ai.mcp import MCPToolset
from sqlmodel import Session, select

from achilles_core.db.models import EmailCache, FollowUp, Reminder
from achilles_core.mcp.manager import McpManager
from achilles_core.services import briefs, calendar, followups
from achilles_core.services.rules import get_rules
from achilles_core.services.scheduler import Scheduler
from achilles_core.services.users import first_user


@pytest.fixture
async def live_mcp(fake_google: ModuleType) -> AsyncIterator[McpManager]:
    manager = McpManager(
        {
            "google": MCPToolset(
                Client(fake_google.server), id="google", tool_error_behavior="failed"
            )
        }
    )
    await manager.start()
    yield manager
    await manager.stop()


def test_refresh_and_triage_labels(
    fake_google: ModuleType, logged_in: TestClient, origin: dict[str, str]
) -> None:
    response = logged_in.post("/api/inbox/refresh", headers=origin)
    assert response.status_code == 200
    assert response.json() == {"messages": 4, "labeled": 4, "failed": 0}

    by_id = {item["message_id"]: item for item in logged_in.get("/api/inbox").json()}
    assert by_id["m1"]["category"] == "Invoices"
    assert by_id["m3"]["category"] == "Clients"
    assert by_id["m1"]["unread"] is True
    assert {entry["message_id"]: entry["add"] for entry in fake_google.labeled} == {
        "m1": ["Invoices"],
        "m2": ["To review"],
        "m3": ["Clients"],
        "m4": ["Clients"],
    }


def test_calendar_and_slots(logged_in: TestClient, origin: dict[str, str]) -> None:
    events = logged_in.get("/api/calendar").json()
    assert {event["event_id"] for event in events} == {"e1", "e2"}
    slots = logged_in.post(
        "/api/calendar/find-slot", json={"duration_minutes": 45}, headers=origin
    ).json()
    assert slots == [{"start": "2026-10-17T10:00:00", "end": "2026-10-17T11:00:00"}]


def test_settings_round_trip(logged_in: TestClient, origin: dict[str, str]) -> None:
    body = {
        "signature": "Jordan",
        "tone": "warm and direct",
        "business_hours": "08:30-16:30",
        "follow_up_days": 5,
        "priority_contacts": ["maya@example.test"],
        "email_to_self": True,
        "self_email": "tester@example.test",
    }
    assert logged_in.put("/api/settings", json=body, headers=origin).json() == body
    assert logged_in.get("/api/settings").json() == body
    bad = logged_in.put("/api/settings", json={**body, "business_hours": "9-5"}, headers=origin)
    assert bad.status_code == 422


def test_morning_brief_lands_on_today(logged_in: TestClient, origin: dict[str, str]) -> None:
    brief = logged_in.post("/api/today/brief", headers=origin).json()
    assert brief["kind"] == "morning"
    assert "Good morning" in brief["content"]
    today = logged_in.get("/api/today").json()
    assert today["brief"]["content"] == brief["content"]
    assert today["unread"] == 2


def test_draft_reply(
    logged_in: TestClient, fake_google: ModuleType, origin: dict[str, str]
) -> None:
    result = logged_in.post("/api/inbox/m1/draft", headers=origin).json()
    assert result["to"] == "ada@example.test"
    assert result["subject"] == "Re: Invoice 42"
    assert result["body"] == "Hello from the test model."
    assert fake_google.drafted[-1] == {
        "to": "ada@example.test",
        "subject": "Re: Invoice 42",
        "body": "Hello from the test model.",
        "thread_id": "t1",
    }


async def test_followup_drafts_after_due(
    logged_in: TestClient,
    app: FastAPI,
    fake_google: ModuleType,
    origin: dict[str, str],
    live_mcp: McpManager,
) -> None:
    logged_in.post("/api/inbox/refresh", headers=origin)
    created = logged_in.post("/api/inbox/m3/follow-up", json={"days": 3}, headers=origin).json()
    assert created["status"] == "open"
    assert created["subject"] == "Proposal follow-up"

    with Session(app.state.engine) as session:
        user = first_user(session)
        rules = get_rules(session, user.id)
        followup = session.get(FollowUp, created["id"])
        result = await followups.check_followups(
            session, user, live_mcp, rules, followup.due_at + timedelta(hours=1)
        )
        assert result["drafted"] == 1
        session.refresh(followup)
        assert followup.status == "drafted"
        assert followup.draft_id == "d1"
    assert fake_google.drafted[-1]["to"] == "ada@example.test"
    assert fake_google.drafted[-1]["thread_id"] == "t3"


async def test_followup_closes_when_reply_arrives(
    logged_in: TestClient,
    app: FastAPI,
    fake_google: ModuleType,
    origin: dict[str, str],
    live_mcp: McpManager,
) -> None:
    logged_in.post("/api/inbox/refresh", headers=origin)
    created = logged_in.post("/api/inbox/m1/follow-up", json={"days": 1}, headers=origin).json()
    with Session(app.state.engine) as session:
        user = first_user(session)
        rules = get_rules(session, user.id)
        followup = session.get(FollowUp, created["id"])
        result = await followups.check_followups(
            session, user, live_mcp, rules, followup.due_at + timedelta(hours=1)
        )
        assert result["closed"] == 1
        session.refresh(followup)
        assert followup.status == "closed"
    assert fake_google.drafted == []


async def test_scheduler_jobs_refresh_caches(
    app: FastAPI, settings, logged_in: TestClient, live_mcp: McpManager
) -> None:
    runtime = SimpleNamespace(manager=live_mcp)
    scheduler = Scheduler(settings, app.state.engine, runtime)
    await scheduler.poll_mail()
    await scheduler.poll_mail()
    await scheduler.poll_calendar()

    with Session(app.state.engine) as session:
        user = first_user(session)
        messages = list(session.exec(select(EmailCache).where(EmailCache.user_id == user.id)))
        assert len(messages) == 4
        start = datetime(2026, 10, 17, tzinfo=UTC)
        events = calendar.list_events(session, user, start, start + timedelta(days=2))
        assert len(events) == 2
        reminder = Reminder(
            user_id=user.id, text="pay rent", due_at=datetime.now(UTC) - timedelta(minutes=1)
        )
        session.add(reminder)
        session.commit()
        session.refresh(reminder)
        reminder_id = reminder.id
    await scheduler.check_reminders()
    with Session(app.state.engine) as session:
        assert session.get(Reminder, reminder_id).status == "due"


def test_brief_text_includes_sources(app: FastAPI, logged_in: TestClient) -> None:
    with Session(app.state.engine) as session:
        user = first_user(session)
        text = briefs.morning_text(session, user, datetime(2026, 10, 17, 8, tzinfo=UTC))
    assert "Good morning" in text
    assert "approval" in text
