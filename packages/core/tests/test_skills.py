from datetime import UTC, datetime, timedelta
from types import ModuleType, SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from achilles_core.db.models import EmailCache, FollowUp, Reminder
from achilles_core.mcp.manager import McpManager
from achilles_core.services import briefs, calendar, followups
from achilles_core.services.rules import get_rules
from achilles_core.services.scheduler import CURSOR_KEY, Scheduler
from achilles_core.services.store import read_setting, write_setting
from achilles_core.services.users import first_user


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
        "model_tier": "degraded",
    }
    assert logged_in.put("/api/settings", json=body, headers=origin).json() == body
    assert logged_in.get("/api/settings").json() == body
    bad = logged_in.put("/api/settings", json={**body, "business_hours": "9-5"}, headers=origin)
    assert bad.status_code == 422


def test_model_options_and_smoke(logged_in: TestClient, origin: dict[str, str]) -> None:
    options = logged_in.get("/api/settings/models").json()
    assert options["effective_tier"] in ("supported", "degraded")
    assert {tier["tier"] for tier in options["tiers"]} == {"supported", "degraded"}
    assert all(tier["tag"] for tier in options["tiers"])

    result = logged_in.post("/api/settings/smoke", headers=origin).json()
    assert result["ok"] is True
    assert result["text"] == "Hello from the test model."
    assert result["latency_ms"] >= 0


def test_morning_brief_lands_on_today(logged_in: TestClient, origin: dict[str, str]) -> None:
    brief = logged_in.post("/api/today/brief", headers=origin).json()
    assert brief["kind"] == "morning"
    assert "Good morning" in brief["content"]
    today = logged_in.get("/api/today").json()
    assert today["brief"]["content"] == brief["content"]
    assert today["unread"] == 2


def test_brief_emails_self_only_when_the_address_matches_the_account(
    logged_in: TestClient, fake_google: ModuleType, origin: dict[str, str]
) -> None:
    rules = logged_in.get("/api/settings").json()
    matching = {**rules, "email_to_self": True, "self_email": fake_google.ACCOUNT_EMAIL.upper()}
    logged_in.put("/api/settings", json=matching, headers=origin)
    assert logged_in.get("/api/health").json()["self_email"] == "ok"
    logged_in.post("/api/today/brief", headers=origin)
    assert fake_google.executed == [{"action": "mail_send", "payload": {"draft_id": "d1"}}]
    assert fake_google.drafted[-1]["to"] == fake_google.ACCOUNT_EMAIL

    other = {**rules, "email_to_self": True, "self_email": "someone.else@example.test"}
    logged_in.put("/api/settings", json=other, headers=origin)
    assert logged_in.get("/api/health").json()["self_email"] == "mismatch"
    drafts_before = len(fake_google.drafted)
    logged_in.post("/api/today/digest", headers=origin)
    assert len(fake_google.executed) == 1
    assert len(fake_google.drafted) == drafts_before


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


async def test_stale_cursor_backfills_from_a_search(
    app: FastAPI, settings, logged_in: TestClient, fake_google: ModuleType, live_mcp: McpManager
) -> None:
    scheduler = Scheduler(settings, app.state.engine, SimpleNamespace(manager=live_mcp))
    with Session(app.state.engine) as session:
        user = first_user(session)
        write_setting(session, user.id, CURSOR_KEY, "stale")
    await scheduler.poll_mail()
    with Session(app.state.engine) as session:
        user = first_user(session)
        assert read_setting(session, user.id, CURSOR_KEY) == "101"
        cached = list(session.exec(select(EmailCache).where(EmailCache.user_id == user.id)))
    assert {row.message_id for row in cached} == {"m1", "m2", "m3", "m4"}
    assert len(fake_google.labeled) == 4


async def test_daily_jobs_get_the_rest_of_the_day_as_grace(
    app: FastAPI, settings, logged_in: TestClient
) -> None:
    scheduler = Scheduler(
        settings.model_copy(update={"scheduler_enabled": True}),
        app.state.engine,
        app.state.runtime,
    )
    scheduler.start()
    try:
        jobs = {job.id: job for job in scheduler.inner.get_jobs()}
        assert jobs["morning_brief"].misfire_grace_time == 16 * 3600 + 30 * 60
        assert jobs["eod_digest"].misfire_grace_time == 6 * 3600
        assert jobs["poll_mail"].misfire_grace_time == 3600
        assert all(job.coalesce for job in jobs.values())
    finally:
        scheduler.stop()


async def test_scheduler_backup_writes_an_archive(
    app: FastAPI, settings, logged_in: TestClient
) -> None:
    scheduler = Scheduler(settings, app.state.engine, app.state.runtime)
    await scheduler.backup()
    assert list((settings.achilles_home / "backups").glob("achilles-*.tar.gz"))


def test_brief_text_includes_sources(app: FastAPI, logged_in: TestClient) -> None:
    with Session(app.state.engine) as session:
        user = first_user(session)
        text = briefs.morning_text(session, user, datetime(2026, 10, 17, 8, tzinfo=UTC))
    assert "Good morning" in text
    assert "approval" in text
