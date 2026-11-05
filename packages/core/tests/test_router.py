from collections.abc import Callable
from types import ModuleType
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic_ai.models import Model
from sqlmodel import Session

from homer_core.agent.router import Command, parse_command, parse_decision
from homer_core.services import approvals

Frames = list[tuple[str, dict[str, Any]]]
PostChat = Callable[[dict[str, Any]], Frames]
JobModel = Callable[..., Model]


def tokens(frames: Frames) -> str:
    return "".join(data["text"] for name, data in frames if name == "token")


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("/brief", Command("brief", "")),
        ("  /inbox  ", Command("inbox", "")),
        (
            "/remind call the dentist tomorrow 9am",
            Command("remind", "call the dentist tomorrow 9am"),
        ),
        ("/approve 3", Command("approve", "3")),
        ("/reject 12", Command("reject", "12")),
        ("/slot 45", Command("slot", "45")),
        ("/draft m1", Command("draft", "m1")),
        ("/followup t1 3", Command("followup", "t1 3")),
        ("/digest", Command("digest", "")),
        ("hello /brief", None),
        ("/briefing", None),
        ("/unknown", None),
    ],
)
def test_parse_command(message: str, expected: Command | None) -> None:
    assert parse_command(message) == expected


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("send it", "approve"),
        ("Send it now, please.", "approve"),
        ("yes", "approve"),
        ("Yes, send it", "approve"),
        ("approved", "approve"),
        ("go ahead!", "approve"),
        ("no", "reject"),
        ("cancel", "reject"),
        ("Discard it.", "reject"),
        ("don't send it", "reject"),
        ("send it to Maya instead", None),
        ("yes I am free on Tuesday", None),
        ("no idea what you mean", None),
    ],
)
def test_parse_decision(message: str, expected: str | None) -> None:
    assert parse_decision(message) == expected


@pytest.mark.parametrize(("message", "needle"), [("/brief", "Good morning"), ("/inbox", "cache")])
def test_skill_commands(post_chat: PostChat, message: str, needle: str) -> None:
    frames = post_chat({"message": message})
    assert [name for name, _ in frames] == ["meta", "token", "done"]
    assert needle in tokens(frames)


def test_approve_command(
    logged_in: TestClient, app: FastAPI, post_chat: PostChat, fake_google: ModuleType
) -> None:
    result = {
        "approval_required": True,
        "action": "mail_send",
        "payload": {"draft_id": "d1"},
        "preview": "Send draft d1",
    }
    with Session(app.state.engine) as session:
        approval_id = approvals.create_from_tool_result(session, 1, "google", result).id
    assert tokens(post_chat({"message": "/approve x"})) == "Usage: /approve <approval id>"
    assert tokens(post_chat({"message": "/approve 99"})) == "Approval 99 not found"
    assert tokens(post_chat({"message": f"/approve {approval_id}"})) == (
        f"Approval #{approval_id} (mail_send): done."
    )
    assert fake_google.executed == [{"action": "mail_send", "payload": {"draft_id": "d1"}}]
    assert "not pending" in tokens(post_chat({"message": f"/reject {approval_id}"}))


def create_send_approval(app: FastAPI, draft_id: str = "d1") -> int:
    result = {
        "approval_required": True,
        "action": "mail_send",
        "payload": {"draft_id": draft_id},
        "preview": f"Send draft {draft_id}",
    }
    with Session(app.state.engine) as session:
        approval_id = approvals.create_from_tool_result(session, 1, "google", result).id
    assert approval_id is not None
    return approval_id


class TestTypedDecisions:
    @pytest.fixture
    def model(self, jobs: JobModel) -> Model:
        return jobs([[{"kind": "remind", "text": "invented", "date": "2026-10-17"}]])

    def test_send_it_approves_the_only_pending_approval_without_the_model(
        self, app: FastAPI, post_chat: PostChat, fake_google: ModuleType
    ) -> None:
        approval_id = create_send_approval(app)
        frames = post_chat({"message": "send it"})
        assert tokens(frames) == f"Approval #{approval_id} (mail_send): done."
        assert fake_google.executed == [{"action": "mail_send", "payload": {"draft_id": "d1"}}]
        assert frames[-1][1]["input_tokens"] == 0

    def test_discard_rejects_and_deletes_the_draft(
        self, logged_in: TestClient, app: FastAPI, post_chat: PostChat, fake_google: ModuleType
    ) -> None:
        approval_id = create_send_approval(app, "d7")
        assert tokens(post_chat({"message": "Discard it"})) == (
            f"Approval #{approval_id} (mail_send): rejected."
        )
        assert fake_google.executed == []
        assert fake_google.deleted == ["d7"]

    def test_several_pending_asks_which(self, app: FastAPI, post_chat: PostChat) -> None:
        first, second = create_send_approval(app, "d1"), create_send_approval(app, "d2")
        said = tokens(post_chat({"message": "yes"}))
        assert said == (
            f"Several approvals are waiting: #{first} mail_send; #{second} mail_send. "
            "Say /approve N to pick one."
        )

    def test_nothing_pending(self, logged_in: TestClient, post_chat: PostChat) -> None:
        assert tokens(post_chat({"message": "send it"})) == "Nothing is waiting for your approval."


class TestRemindCommand:
    @pytest.fixture
    def model(self, jobs: JobModel) -> Model:
        intent = {"kind": "remind", "text": "call the dentist", "date": "2026-10-17", "time": "9am"}
        return jobs([[intent]])

    def test_remind_saves_a_row_in_the_users_timezone(
        self, logged_in: TestClient, post_chat: PostChat
    ) -> None:
        frames = post_chat({"message": "/remind call the dentist tomorrow 9am"})
        assert tokens(frames) == "Reminder set for Sat 17 Oct 09:00: call the dentist."
        reminders = logged_in.get("/api/reminders").json()
        assert [(r["text"], r["status"]) for r in reminders] == [("call the dentist", "pending")]
        assert reminders[0]["due_at"].startswith("2026-10-17T08:00:00")
