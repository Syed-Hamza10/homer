from collections.abc import Callable
from types import ModuleType
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic_ai.models import Model
from sqlmodel import Session

from achilles_core.agent.router import Command, normalise, parse_command
from achilles_core.agent.toolsets import TOOLSETS
from achilles_core.services import approvals

Frames = list[tuple[str, dict[str, Any]]]
PostChat = Callable[[dict[str, Any]], Frames]
Scripted = Callable[..., Model]


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
    ("answer", "expected"),
    [
        ("search", "search"),
        ("Mail.", "mail"),
        ("`mail+calendar`", "mail+calendar"),
        ("I'd say: calendar", "calendar"),
        ("System\n", "system"),
        ("banana", "mail+calendar"),
        ("", "mail+calendar"),
    ],
)
def test_normalise(answer: str, expected: str) -> None:
    assert normalise(answer) == expected


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


class TestRemindCommand:
    @pytest.fixture
    def seen_tools(self) -> list[list[str]]:
        return []

    @pytest.fixture
    def model(self, scripted: Scripted, seen_tools: list[list[str]]) -> Model:
        steps = [
            [("remind", {"text": "call the dentist", "when_iso": "2026-10-17T09:00:00"})],
            "Reminder set for tomorrow at 09:00.",
        ]
        return scripted("unused", steps, seen_tools)

    def test_remind_uses_system_toolset_and_saves_a_row(
        self, logged_in: TestClient, post_chat: PostChat, seen_tools: list[list[str]]
    ) -> None:
        frames = post_chat({"message": "/remind call the dentist tomorrow 9am"})
        assert tokens(frames) == "Reminder set for tomorrow at 09:00."
        assert set(seen_tools[0]) == set(TOOLSETS["system"])
        reminders = logged_in.get("/api/reminders").json()
        assert [(r["text"], r["status"]) for r in reminders] == [("call the dentist", "pending")]
        assert reminders[0]["due_at"].startswith("2026-10-17T08:00:00")
