import time
from collections.abc import Callable
from datetime import UTC, datetime
from types import ModuleType
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.models import Model

from homer_core.services.jobs.choice import option_id
from homer_core.services.jobs.recipients import (
    Candidate,
    Person,
    ago,
    is_person,
    mailed,
    matching,
)

Frames = list[tuple[str, dict[str, Any]]]
PostChat = Callable[[dict[str, Any]], Frames]
NOW = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)
DAY_MS = 86_400_000
SEND = {"kind": "send_email", "to": "hamza", "body_instructions": "ask when he is free"}


def of(frames: Frames, name: str) -> list[dict[str, Any]]:
    return [data for event, data in frames if event == name]


def said(frames: Frames) -> str:
    return "".join(data["text"] for data in of(frames, "token"))


def calls(frames: Frames) -> list[str]:
    return [call["name"] for call in of(frames, "tool_call")]


def stamp(days_ago: int, now_ms: int) -> dict[str, Any]:
    return {"internal_date": str(now_ms - days_ago * DAY_MS)}


def message(sender: str, days_ago: int, now_ms: int, **extra: Any) -> dict[str, Any]:
    return {"from": sender, "labels": ["INBOX"], "metadata": stamp(days_ago, now_ms), **extra}


@pytest.mark.parametrize(
    ("name", "email"),
    [
        ("", "invitation-do-not-reply@trello.example"),
        ("Google Drive", "drive-shares-dm-noreply@google.example"),
        ("", "updates@academia-mail.example"),
        ("", "no-reply@shop.example"),
        ("", "noreply@shop.example"),
        ("", "notifications@forum.example"),
        ("", "newsletter@paper.example"),
        ("", "mailer-daemon@mail.example"),
        ("", "calendar-notification@google.example"),
        ("Hamza (via Google Drive)", "share@drive.example"),
        ("PDF By hamza azeem", "files@pdf.example"),
    ],
)
def test_robot_senders_are_not_people(name: str, email: str) -> None:
    assert not is_person(Person(name, email))


@pytest.mark.parametrize(
    ("name", "email"),
    [("Hamza Azeem", "hamza.azeem@example.test"), ("Abby Byrne", "abby@example.test")],
)
def test_people_stay(name: str, email: str) -> None:
    assert is_person(Person(name, email))


def test_mailed_ranks_sent_newest_first_then_received_and_drops_lists_and_me() -> None:
    now_ms = int(NOW.timestamp() * 1000)
    sent = [
        message(
            "Me <me@example.test>", 9, now_ms, to="Old Pal <old@example.test>", labels=["SENT"]
        ),
        message(
            "Me <me@example.test>", 3, now_ms, to="New Pal <new@example.test>", labels=["SENT"]
        ),
    ]
    received = [
        message("Inbox Pal <inbox@example.test>", 2, now_ms),
        message("Me <me@example.test>", 1, now_ms, labels=["SENT"]),
        message("Shop <shop@example.test>", 0, now_ms, metadata={"list_unsubscribe": True}),
    ]
    found = mailed(sent, received, NOW)
    assert [(c.email, c.source) for c in found] == [
        ("new@example.test", "You emailed them 3 days ago"),
        ("old@example.test", "You emailed them on 5 Nov"),
        ("inbox@example.test", "Emailed you 2 days ago"),
    ]


def test_mailed_without_a_date_says_only_who_wrote() -> None:
    found = mailed([], [{"from": "Pal <pal@example.test>"}], NOW)
    assert found == [Candidate("Pal", "pal@example.test", "Emailed you")]


@pytest.mark.parametrize(
    ("moment", "text"),
    [
        (datetime(2026, 11, 14, 1, 0, tzinfo=UTC), "today"),
        (datetime(2026, 11, 13, 23, 0, tzinfo=UTC), "yesterday"),
        (datetime(2026, 11, 8, 9, 0, tzinfo=UTC), "6 days ago"),
        (datetime(2026, 11, 7, 9, 0, tzinfo=UTC), "on 7 Nov"),
        (datetime(2025, 12, 30, 9, 0, tzinfo=UTC), "on 30 Dec 2025"),
    ],
)
def test_ago(moment: datetime, text: str) -> None:
    assert ago(moment, NOW) == text


def test_matching_merges_one_address_keeping_the_first_source_and_a_name() -> None:
    people = [
        Candidate("", "hamza.pal@example.test", "You emailed them"),
        Candidate("Pal Hamza", "hamza.pal@example.test", "Emailed you"),
        Candidate("Hamza Two", "two@example.test", "Emailed you"),
    ]
    assert matching(people, "hamza") == [
        Candidate("Pal Hamza", "hamza.pal@example.test", "You emailed them"),
        Candidate("Hamza Two", "two@example.test", "Emailed you"),
    ]


@pytest.fixture
def asked() -> list[str]:
    return []


@pytest.fixture
def intents() -> list[list[dict[str, Any]]]:
    return [[SEND]]


@pytest.fixture
def model(
    jobs: Callable[..., Model], intents: list[list[dict[str, Any]]], asked: list[str]
) -> Model:
    return jobs(
        intents, email={"subject": "Free?", "body": "When are you free this week?"}, asked=asked
    )


@pytest.fixture
def mailbox(fake_google: ModuleType) -> ModuleType:
    """A mailbox where "hamza" matches two contacts, someone the user wrote to, three people who
    wrote, and a pile of robots, as in a real account."""
    now_ms = int(time.time() * 1000)
    fake_google.CONTACTS.extend(
        [
            {"name": "Hamza Contact", "email": "hamza.c@example.test"},
            {"name": "Hamza Azeem", "email": "hamza.a@example.test"},
        ]
    )
    fake_google.MESSAGES.update(
        {
            "h1": message(
                "Tester <tester@example.test>",
                3,
                now_ms,
                id="h1",
                thread_id="th1",
                to="Hamza Sent <hamza.s@example.test>",
                labels=["SENT"],
            ),
            "h8": message("Hamza Later <hamza.l@example.test>", 4, now_ms),
            "h9": message("Hamza Last <hamza.z@example.test>", 6, now_ms),
            "h2": message(
                "Hamza Inbox <hamza.i@example.test>", 2, now_ms, id="h2", thread_id="th2"
            ),
            "h3": message("Hamza at Trello <invitation-do-not-reply@trello.example>", 1, now_ms),
            "h4": message(
                "Hamza (via Google Drive) <drive-shares-dm-noreply@g.example>", 1, now_ms
            ),
            "h5": message("Hamza <updates@academia-mail.example>", 1, now_ms),
            "h6": message("PDF By hamza azeem <files@pdf.example>", 1, now_ms),
            "h7": {
                **message("Hamza Deals <deals@shop.example>", 1, now_ms),
                "metadata": {"list_unsubscribe": True},
            },
        }
    )
    for key in ("h3", "h4", "h5", "h6", "h7", "h8", "h9"):
        fake_google.MESSAGES[key] |= {"id": key, "thread_id": key}
    return fake_google


def test_ambiguous_name_streams_a_choice_card(
    logged_in: TestClient, post_chat: PostChat, mailbox: ModuleType
) -> None:
    frames = post_chat({"message": "send hamza a mail asking when he's free"})
    assert said(frames) == "Which Hamza do you mean?"
    assert calls(frames) == ["contacts_search", "mail_search", "mail_search"]
    [card] = of(frames, "choice")
    assert set(card) == {"question_id", "prompt", "options", "allow_other", "answered"}
    assert card["prompt"] == "Which Hamza do you mean?" and card["allow_other"] is True
    assert [(option["label"], option["detail"]) for option in card["options"]] == [
        ("Hamza Contact", "hamza.c@example.test · Contact"),
        ("Hamza Azeem", "hamza.a@example.test · Contact"),
        ("Hamza Sent", "hamza.s@example.test · You emailed them 3 days ago"),
        ("Hamza Inbox", "hamza.i@example.test · Emailed you 2 days ago"),
        ("Hamza Later", "hamza.l@example.test · Emailed you 4 days ago"),
    ]
    assert [option["id"] for option in card["options"]] == [
        option_id(f"hamza.{key}@example.test") for key in "casil"
    ]
    assert of(frames, "approval_required") == [] and mailbox.drafted == []


def test_click_continues_the_job_without_an_intent_call(
    logged_in: TestClient, post_chat: PostChat, mailbox: ModuleType, asked: list[str]
) -> None:
    first = post_chat({"message": "send hamza a mail asking when he's free"})
    conversation = of(first, "meta")[0]["conversation_id"]
    card = of(first, "choice")[0]
    picked = card["options"][2]
    frames = post_chat(
        {
            "conversation_id": conversation,
            "message": picked["label"],
            "choice": {"question_id": card["question_id"], "option_id": picked["id"]},
        }
    )
    assert len(asked) == 1
    assert calls(frames) == ["mail_draft"]
    assert mailbox.drafted[0]["to"] == "hamza.s@example.test"
    assert of(frames, "approval_required")[0]["payload"]["to_name"] == "Hamza Sent"
    messages = logged_in.get(f"/api/conversations/{conversation}/messages").json()
    assert [m["choice"] is not None for m in messages] == [False, True, False, False]
    assert messages[1]["content"] == "Which Hamza do you mean?"
    assert messages[1]["choice"]["answered"] == picked["id"]
    assert messages[1]["choice"]["options"] == card["options"]


def test_a_second_click_on_an_answered_card_goes_through_the_intent_call(
    logged_in: TestClient, post_chat: PostChat, mailbox: ModuleType, asked: list[str]
) -> None:
    first = post_chat({"message": "send hamza a mail asking when he's free"})
    conversation = of(first, "meta")[0]["conversation_id"]
    card = of(first, "choice")[0]
    for option in card["options"][:2]:
        hint = {"question_id": card["question_id"], "option_id": option["id"]}
        post_chat({"conversation_id": conversation, "message": option["label"], "choice": hint})
    assert len(asked) == 2
    assert [draft["to"] for draft in mailbox.drafted] == ["hamza.c@example.test"]


def test_an_unknown_option_goes_through_the_intent_call(
    logged_in: TestClient, post_chat: PostChat, mailbox: ModuleType, asked: list[str]
) -> None:
    first = post_chat({"message": "send hamza a mail asking when he's free"})
    conversation = of(first, "meta")[0]["conversation_id"]
    hint = {"question_id": of(first, "choice")[0]["question_id"], "option_id": "nope"}
    post_chat({"conversation_id": conversation, "message": "Hamza", "choice": hint})
    assert len(asked) == 2 and mailbox.drafted == []


def test_a_typed_answer_sees_every_option_in_the_history(
    logged_in: TestClient, post_chat: PostChat, mailbox: ModuleType, asked: list[str]
) -> None:
    first = post_chat({"message": "send hamza a mail asking when he's free"})
    conversation = of(first, "meta")[0]["conversation_id"]
    post_chat({"conversation_id": conversation, "message": "the one I emailed"})
    assert "Hamza Sent (hamza.s@example.test)" in asked[1]
