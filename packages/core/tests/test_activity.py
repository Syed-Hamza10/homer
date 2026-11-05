import json
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session

from homer_core.db.models import Approval, Fact
from homer_core.services.activity import account_items

BASE = datetime(2026, 11, 5, 9, 0, tzinfo=UTC)


def add_approval(
    app: FastAPI,
    action: str,
    payload: dict[str, Any],
    status: str,
    minutes: int,
    preview: str = "",
    conversation_id: int | None = None,
) -> int:
    with Session(app.state.engine) as session:
        approval = Approval(
            user_id=1,
            server="google",
            action=action,
            payload_json=json.dumps(payload),
            payload_hash="x",
            preview=preview,
            status=status,
            created_at=BASE + timedelta(minutes=minutes - 1),
            decided_at=None if status == "pending" else BASE + timedelta(minutes=minutes),
            conversation_id=conversation_id,
        )
        session.add(approval)
        session.commit()
        session.refresh(approval)
        return approval.id


def add_fact(app: FastAPI, text: str, minutes: int) -> None:
    with Session(app.state.engine) as session:
        session.add(Fact(user_id=1, text=text, created_at=BASE + timedelta(minutes=minutes)))
        session.commit()


def seed(app: FastAPI) -> None:
    mail = {"to": "Rosa Lindqvist <rosa@example.com>", "subject": "Re: Revised proposal"}
    add_approval(app, "mail_send", mail, "done", 10, conversation_id=7)
    add_approval(
        app,
        "cal_update",
        {"event_id": "e1", "start": "2026-11-10T09:00:00+00:00"},
        "done",
        20,
        preview="Move 'Call with Elena' from Mon 09 Nov 10:00-10:30 to Tue 10 Nov 09:00-09:30",
    )
    add_fact(app, "Dana prefers calls after 3pm", 30)
    add_approval(app, "mail_send", {"to": "tomas@example.com", "subject": "Hi"}, "rejected", 40)
    add_approval(
        app, "cal_create", {"title": "Lunch", "start": "2026-11-11T12:00:00"}, "pending", 50
    )


def texts(page: dict[str, Any]) -> list[str]:
    return [item["text"] for item in page["items"]]


def test_timeline_is_plain_language_newest_first(logged_in: TestClient, app: FastAPI) -> None:
    seed(app)
    page = logged_in.get("/api/activity").json()
    assert texts(page) == [
        "Proposed 'Lunch' Wed 12:00, waiting for approval",
        "Rejected draft to tomas@example.com",
        "Remembered: Dana prefers calls after 3pm",
        "Moved 'Call with Elena' to Tue 09:00",
        "Sent email to Rosa Lindqvist",
    ]
    assert page["next"] is None
    by_text = {item["text"]: item for item in page["items"]}
    sent = by_text["Sent email to Rosa Lindqvist"]
    assert (sent["kind"], sent["detail"], sent["link"]) == (
        "email",
        "Re: Revised proposal",
        "/?conversation=7",
    )
    assert by_text["Moved 'Call with Elena' to Tue 09:00"]["link"] == "/calendar?event=e1"
    assert by_text["Proposed 'Lunch' Wed 12:00, waiting for approval"]["link"].startswith(
        "/approvals"
    )


def test_filters(logged_in: TestClient, app: FastAPI) -> None:
    seed(app)
    email = logged_in.get("/api/activity?kind=email").json()
    assert {item["kind"] for item in email["items"]} == {"email"}
    assert len(email["items"]) == 2
    memory = logged_in.get("/api/activity?kind=memory").json()
    assert texts(memory) == ["Remembered: Dana prefers calls after 3pm"]
    calendar = logged_in.get("/api/activity?kind=calendar").json()
    assert len(calendar["items"]) == 2
    assert logged_in.get("/api/activity?kind=nope").status_code == 422


def test_paging_with_before_cursor(logged_in: TestClient, app: FastAPI) -> None:
    seed(app)
    first = logged_in.get("/api/activity?limit=2").json()
    assert len(first["items"]) == 2
    assert first["next"] is not None
    second = logged_in.get("/api/activity", params={"limit": 2, "before": first["next"]}).json()
    third = logged_in.get("/api/activity", params={"limit": 2, "before": second["next"]}).json()
    assert third["next"] is None
    seen = texts(first) + texts(second) + texts(third)
    assert seen == texts(logged_in.get("/api/activity").json())


def test_empty_timeline_and_login_required(
    client: TestClient, logged_in: TestClient, app: FastAPI
) -> None:
    assert logged_in.get("/api/activity").json() == {"items": [], "next": None}
    logged_in.cookies.clear()
    assert client.get("/api/activity").status_code == 401


def test_google_connection_shows_in_all_only() -> None:
    before = BASE + timedelta(days=1)
    assert [item.text for item in account_items(BASE, before)] == ["Google connected"]
    assert account_items(BASE, BASE) == []
    assert account_items(None, before) == []
