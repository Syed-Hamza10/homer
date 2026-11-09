from datetime import date, datetime, timedelta
from types import ModuleType
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from fastmcp.client import Client
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models import Model

from homer_core.agent.router import asks_about_draft, asks_if_sent, wants_link
from homer_core.config import Settings
from homer_core.mcp.manager import McpManager
from homer_core.services.chat import named_earlier
from homer_core.services.jobs.draft_question import CREATE_FIRST, when_line
from homer_core.services.jobs.send_email import undangled

from .conftest import ORIGIN, JobModel, PostChat, load_fake_server
from .test_jobs import of, said

KARACHI = "Asia/Karachi"
HASSAN = "hassan@example.test"
LINK_ASK = "add the link of the event in that email as well"
BOOK_AND_EMAIL = (
    "book an event with hassan@example.test about the demo saturday 3pm, then send "
    "hassan@example.test a brief email that I put this in our calendar"
)


def saturday() -> date:
    today = datetime.now(ZoneInfo(KARACHI)).date()
    return today + timedelta(days=(5 - today.weekday()) % 7 or 7)


def booked_and_drafted() -> list[dict[str, Any]]:
    return [
        {
            "kind": "create_event",
            "title": "Homer demo",
            "date": saturday().isoformat(),
            "start": "3pm",
            "attendees": [HASSAN],
        },
        {"kind": "send_email", "to": HASSAN, "body_instructions": "I put the demo in our calendar"},
    ]


@pytest.fixture
def settings(settings: Settings) -> Settings:
    return settings.model_copy(update={"timezone": KARACHI})


@pytest.fixture
def mcp(fake_google: ModuleType) -> McpManager:
    fakes = {"google": fake_google, "search": load_fake_server("search")}
    return McpManager(
        {
            name: MCPToolset(Client(module.server), id=name, tool_error_behavior="failed")
            for name, module in fakes.items()
        }
    )


@pytest.fixture
def seen() -> list[list[ModelMessage]]:
    return []


@pytest.fixture
def model(jobs: JobModel, seen: list[list[ModelMessage]]) -> Model:
    return jobs([booked_and_drafted()], text="Yes, it says Saturday at 3pm.", seen=seen)


def cards(frames: list[tuple[str, dict[str, Any]]]) -> dict[str, dict[str, Any]]:
    return {card["action"]: card for card in of(frames, "approval_required")}


def start(post_chat: PostChat) -> tuple[int, dict[str, dict[str, Any]]]:
    frames = post_chat({"message": BOOK_AND_EMAIL})
    return frames[0][1]["conversation_id"], cards(frames)


class TestEventLink:
    def test_a_pending_event_gets_an_honest_answer_and_the_time_line(
        self, post_chat: PostChat
    ) -> None:
        chat, _ = start(post_chat)
        frames = post_chat({"message": LINK_ASK, "conversation_id": chat})
        assert said(frames).startswith(CREATE_FIRST)
        body = cards(frames)["mail_send"]["payload"]["body"]
        assert f"When: {saturday():%A} {saturday().day} {saturday():%b}, 3:00–3:30 pm PKT" in body
        assert "http" not in body

    def test_a_created_event_puts_its_real_link_in(
        self, post_chat: PostChat, logged_in: TestClient
    ) -> None:
        chat, made = start(post_chat)
        event = made["cal_create"]["approval_id"]
        assert logged_in.post(f"/api/approvals/{event}/approve", headers=ORIGIN).status_code == 200
        frames = post_chat({"message": LINK_ASK, "conversation_id": chat})
        body = cards(frames)["mail_send"]["payload"]["body"]
        assert "Calendar link: https://calendar.example.test/event?eid=evt_new" in body
        assert body.count("Calendar link:") == 1
        assert said(frames) == "Added the event link to the draft. Edit it or press Send."


class TestDraftQuestions:
    def test_where_is_the_link_is_answered_from_the_draft(self, post_chat: PostChat) -> None:
        chat, _ = start(post_chat)
        frames = post_chat({"message": "where's the link in this draft?", "conversation_id": chat})
        assert said(frames) == f"No, the link isn't in it yet. {CREATE_FIRST}"
        assert of(frames, "approval_required") == []

    def test_a_yes_or_no_question_reads_the_draft(
        self, post_chat: PostChat, seen: list[list[ModelMessage]]
    ) -> None:
        chat, made = start(post_chat)
        frames = post_chat(
            {"message": "does it mention saturday, yes or no?", "conversation_id": chat}
        )
        assert said(frames) == "Yes, it says Saturday at 3pm."
        prompt = str(getattr(seen[-1][-1], "instructions", ""))
        assert made["mail_send"]["payload"]["body"] in prompt
        assert "not created yet" in prompt

    def test_the_status_line_is_only_for_status_questions(self, post_chat: PostChat) -> None:
        chat, _ = start(post_chat)
        frames = post_chat({"message": "did you send it?", "conversation_id": chat})
        assert said(frames).startswith("Not yet. The draft to hassan@example.test")


class TestRepeats:
    def test_the_same_message_twice_gives_no_second_draft(self, post_chat: PostChat) -> None:
        chat, made = start(post_chat)
        frames = post_chat({"message": BOOK_AND_EMAIL, "conversation_id": chat})
        assert said(frames) == "I already drafted that one — it's above."
        assert of(frames, "approval_required") == []

    def test_a_repeat_after_a_card_was_decided_runs_again(
        self, post_chat: PostChat, logged_in: TestClient
    ) -> None:
        chat, made = start(post_chat)
        event = made["cal_create"]["approval_id"]
        logged_in.post(f"/api/approvals/{event}/approve", headers=ORIGIN)
        frames = post_chat({"message": BOOK_AND_EMAIL, "conversation_id": chat})
        assert said(frames) != "I already drafted that one — it's above."


def test_a_name_before_him_is_enough_to_email() -> None:
    message = "book an event with hassan about the demo saturday 3pm. Then send him a brief email"
    assert named_earlier(message)
    assert not named_earlier("email her about it")


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("are you adding the link of the event in the email yes or no?", (True, False, False)),
        ("where's the link in this draft?", (True, False, False)),
        (LINK_ASK, (False, True, False)),
        ("did you send it?", (False, False, True)),
        ("has it gone out?", (False, False, True)),
        ("did you add the link before you send it?", (True, False, False)),
        ("any email from Rosa?", (False, False, False)),
    ],
)
def test_draft_questions_links_and_status_are_told_apart(
    message: str, expected: tuple[bool, bool, bool]
) -> None:
    assert (asks_about_draft(message), wants_link(message), asks_if_sent(message)) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "I added it to our calendar. You can access it directly through this link:. "
            "Please have a look.",
            "I added it to our calendar. Please have a look.",
        ),
        ("The notes are here:\nSee you Saturday.", "See you Saturday."),
        ("Agenda attached []. See you then.", "See you then."),
        ("We meet at: the cafe on Elm.", "We meet at: the cafe on Elm."),
    ],
)
def test_dangling_placeholders_are_removed(text: str, expected: str) -> None:
    assert undangled(text) == expected


def test_the_time_line_reads_like_a_person_wrote_it() -> None:
    payload = {"start": "2026-11-14T11:30:00+05:00", "end": "2026-11-14T12:30:00+05:00"}
    assert when_line(payload, KARACHI) == "Saturday 14 Nov, 11:30 am–12:30 pm PKT"
