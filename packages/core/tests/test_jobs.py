import json
import time
from collections.abc import Callable
from types import ModuleType
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastmcp import FastMCP
from fastmcp.client import Client
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.models import Model
from sqlmodel import Session
from structlog.testing import capture_logs

from homer_core.agent.claims import HONEST, review
from homer_core.config import Settings
from homer_core.db.models import Approval
from homer_core.mcp.manager import McpManager
from homer_core.services.jobs import send_email
from homer_core.services.jobs.send_email import request_send
from homer_core.services.jobs.turn import RECONNECT

from .conftest import ORIGIN, TEXT, load_fake_server

Frames = list[tuple[str, dict[str, Any]]]
PostChat = Callable[[dict[str, Any]], Frames]
JobModel = Callable[..., Model]
KARACHI = "Asia/Karachi"
READY = "Draft to {who} is ready. Edit it or press Send."
PAID = "The invoice was paid in full this morning."
PAID_BODY = f"Hi,\n\n{PAID}\n\nBest,\nTester"


def of(frames: Frames, name: str) -> list[dict[str, Any]]:
    return [data for event, data in frames if event == name]


def said(frames: Frames) -> str:
    return "".join(data["text"] for data in of(frames, "token"))


def calls(frames: Frames) -> list[str]:
    return [call["name"] for call in of(frames, "tool_call")]


def email(to: str, **extra: Any) -> dict[str, Any]:
    return {"kind": "send_email", "to": to, "body_instructions": "the invoice is paid", **extra}


def event(**fields: Any) -> dict[str, Any]:
    return {"kind": "create_event", "title": "Planning", "date": "2026-11-10", **fields}


@pytest.fixture
def settings(settings: Settings) -> Settings:
    return settings.model_copy(update={"timezone": KARACHI})


@pytest.fixture
def fake_search() -> ModuleType:
    return load_fake_server("search")


@pytest.fixture
def mcp(fake_google: ModuleType, fake_search: ModuleType) -> McpManager:
    fakes = {"google": fake_google, "search": fake_search}
    return McpManager(
        {
            name: MCPToolset(Client(module.server), id=name, tool_error_behavior="failed")
            for name, module in fakes.items()
        }
    )


@pytest.fixture
def intents() -> list[list[dict[str, Any]]]:
    return []


@pytest.fixture
def text() -> str:
    return "Hello from the test model."


@pytest.fixture
def written() -> list[dict[str, str]]:
    return [{"subject": "Invoice", "body": PAID}]


@pytest.fixture
def model(
    jobs: JobModel, intents: list[list[dict[str, Any]]], text: str, written: list[dict[str, str]]
) -> Model:
    return jobs(intents, text=text, email=written)


class TestSendEmail:
    @pytest.mark.parametrize("intents", [[[email("bob@example.test")]]])
    def test_address_makes_a_draft_and_an_editable_approval(
        self, logged_in: TestClient, post_chat: PostChat, fake_google: ModuleType
    ) -> None:
        frames = post_chat({"message": "Email bob@example.test that the invoice is paid"})
        assert said(frames) == READY.format(who="bob@example.test")
        assert calls(frames) == ["contacts_search", "mail_search", "mail_draft"]
        assert fake_google.drafted == [
            {
                "to": "bob@example.test",
                "subject": "Invoice",
                "body": PAID_BODY,
                "thread_id": None,
            }
        ]
        requested = of(frames, "approval_required")[0]
        assert requested["action"] == "mail_send"
        assert requested["payload"] == {
            "draft_id": "d1",
            "to": "bob@example.test",
            "subject": "Invoice",
            "body": PAID_BODY,
            "thread_id": "",
        }
        assert requested["preview"].startswith("Send email to bob@example.test\nSubject: Invoice")
        assert fake_google.executed == []

    @pytest.mark.parametrize("intents", [[[email("Ada")]]])
    def test_unique_name_resolves_through_contacts(
        self, logged_in: TestClient, post_chat: PostChat
    ) -> None:
        frames = post_chat({"message": "Email Ada that the invoice is paid"})
        assert said(frames) == READY.format(who="Ada Example")
        assert calls(frames) == ["contacts_search", "mail_draft"]
        assert of(frames, "approval_required")[0]["payload"]["to"] == "ada@example.test"

    @pytest.mark.parametrize("intents", [[[email("Sara")]]])
    def test_ambiguous_name_asks_which_one(
        self, logged_in: TestClient, post_chat: PostChat, fake_google: ModuleType
    ) -> None:
        frames = post_chat({"message": "Email Sara that the invoice is paid"})
        assert said(frames) == (
            "Which Sara do you mean: Sara Whitfield (sara.whitfield@example.test) or "
            "Sara Mbeki (sara.mbeki@example.test)?"
        )
        assert of(frames, "approval_required") == [] and fake_google.drafted == []

    @pytest.mark.parametrize("intents", [[[email("Sara Mbeki")]]])
    def test_full_name_picks_the_exact_contact(
        self, logged_in: TestClient, post_chat: PostChat
    ) -> None:
        frames = post_chat({"message": "Email Sara Mbeki"})
        assert of(frames, "approval_required")[0]["payload"]["to"] == "sara.mbeki@example.test"

    @pytest.mark.parametrize("intents", [[[email("Zed")]]])
    def test_unknown_name_asks_for_the_address(
        self, logged_in: TestClient, post_chat: PostChat
    ) -> None:
        frames = post_chat({"message": "Email Zed"})
        assert calls(frames) == ["contacts_search", "mail_search"]
        assert said(frames) == "I could not find an email address for Zed. What is their address?"

    @pytest.mark.parametrize("intents", [[[email("Bob", reply_to_latest_from="Bob")]]])
    def test_recent_sender_is_found_and_replied_to_in_thread(
        self, logged_in: TestClient, post_chat: PostChat, fake_google: ModuleType
    ) -> None:
        frames = post_chat({"message": "Reply to Bob's latest email"})
        assert said(frames) == READY.format(who="bob@example.test")
        assert fake_google.drafted[0]["thread_id"] == "t2"
        assert fake_google.drafted[0]["subject"] == "Re: Lunch?"

    @pytest.mark.parametrize("intents", [[[email("Zed"), event(start="15:00", attendees=["Ada"])]]])
    def test_compound_keeps_the_complete_part_and_asks_about_the_rest(
        self, logged_in: TestClient, post_chat: PostChat
    ) -> None:
        frames = post_chat({"message": "Email Zed and meet Ada at 3pm"})
        assert [a["action"] for a in of(frames, "approval_required")] == ["cal_create"]
        assert said(frames).startswith("I could not find an email address for Zed.")
        assert "Event 'Planning' on Tue 10 Nov 15:00-15:30 is ready." in said(frames)


class TestCreateEvent:
    @pytest.mark.parametrize(
        "intents", [[[event(start="15:00", end="16:00", attendees=["Ada", "Zed"])]]]
    )
    def test_explicit_time_in_the_users_timezone(
        self, logged_in: TestClient, post_chat: PostChat
    ) -> None:
        frames = post_chat({"message": "Add a meeting with Ada on 10 Nov at 3pm"})
        payload = of(frames, "approval_required")[0]["payload"]
        assert (payload["start"], payload["end"]) == ("2026-11-10T15:00:00", "2026-11-10T16:00:00")
        assert payload["attendees"] == ["ada@example.test"]
        call = next(c for c in of(frames, "tool_call") if c["name"] == "cal_create")
        assert call["args"]["timezone"] == KARACHI
        assert said(frames) == (
            "Event 'Planning' on Tue 10 Nov 15:00-16:00 is ready. Edit it or press Create.\n\n"
            "I left Zed off the invite. I could not find an email address for Zed. "
            "What is their address?"
        )

    @pytest.mark.parametrize(
        "intents", [[[event(window_start="9am", window_end="11:00", duration_minutes=45)]]]
    )
    def test_window_picks_the_first_free_slot_in_karachi(
        self, logged_in: TestClient, post_chat: PostChat, fake_google: ModuleType
    ) -> None:
        frames = post_chat({"message": "Find 45 minutes between 9 and 11 on Tuesday"})
        assert fake_google.slot_requests == [
            {"start": "2026-11-10T09:00:00", "end": "2026-11-10T11:00:00", "timezone": KARACHI}
        ]
        payload = of(frames, "approval_required")[0]["payload"]
        assert (payload["start"], payload["end"]) == ("2026-11-10T10:00:00", "2026-11-10T10:45:00")

    @pytest.mark.parametrize(
        "intents", [[[event(window_start="09:00", window_end="10:00", duration_minutes=60)]]]
    )
    def test_full_window_says_so(self, logged_in: TestClient, post_chat: PostChat) -> None:
        frames = post_chat({"message": "an hour between 9 and 10"})
        assert said(frames) == "No free 60-minute slot on 2026-11-10 between 09:00 and 10:00."

    @pytest.mark.parametrize("intents", [[[event(title="Meeting with Ada", start="10:00")]]])
    def test_person_in_the_title_is_invited_when_attendees_are_missing(
        self, logged_in: TestClient, post_chat: PostChat
    ) -> None:
        frames = post_chat({"message": "Add a meeting with Ada at 10"})
        assert of(frames, "approval_required")[0]["payload"]["attendees"] == ["ada@example.test"]


class TestReadCalendar:
    @pytest.mark.parametrize("intents", [[[{"kind": "read_calendar", "range": "tomorrow"}]]])
    def test_short_list_is_rendered_in_local_time_without_the_model(
        self, logged_in: TestClient, post_chat: PostChat
    ) -> None:
        frames = post_chat({"message": "What's on tomorrow?"})
        lines = said(frames).splitlines()
        assert lines[0].startswith("Tomorrow, ")
        assert lines[1:] == ["- 14:00-14:15 Team standup", "- 19:00-20:00 Dentist"]
        call = of(frames, "tool_call")[0]["args"]
        assert call["start"].endswith("T00:00:00+05:00")


class TestReadEmail:
    @pytest.mark.parametrize(
        ("intents", "text"),
        [([[{"kind": "read_email", "sender": "Ada", "question": "what did she ask?"}]], "Pay it.")],
    )
    def test_answers_from_the_fetched_messages(
        self, logged_in: TestClient, post_chat: PostChat
    ) -> None:
        frames = post_chat({"message": "Did Ada email me? What did she ask?"})
        assert of(frames, "tool_call")[0]["args"] == {"query": "from:Ada", "max_results": 5}
        assert said(frames) == "Pay it."

    @pytest.mark.parametrize(
        "intents", [[[{"kind": "read_email", "sender": "Zed", "question": "anything?"}]]]
    )
    def test_nothing_found_is_said_without_the_model(
        self, logged_in: TestClient, post_chat: PostChat
    ) -> None:
        assert said(post_chat({"message": "Anything from Zed?"})) == "I found no email from Zed."


class TestWebSearch:
    @pytest.mark.parametrize(
        ("intents", "text"),
        [([[{"kind": "web_search", "query": "launch news"}]], "It launched.")],
    )
    def test_answers_from_the_snippets_and_ends_with_sources(
        self, logged_in: TestClient, post_chat: PostChat, fake_search: ModuleType
    ) -> None:
        frames = post_chat({"message": "What's the latest launch news?"})
        assert calls(frames)[0] == "web_search"
        assert said(frames) == (
            "It launched.\n\n**Sources**\n- [Launch news](https://news.example.test/a)\n"
            "- [More news](https://news.example.test/b)\n- [Old news](https://news.example.test/c)"
        )

    @pytest.mark.parametrize("intents", [[[{"kind": "web_search", "query": "news off"}]]])
    def test_search_off_says_so(self, logged_in: TestClient, post_chat: PostChat) -> None:
        assert said(post_chat({"message": "news?"})).startswith("Web search is turned off")

    @pytest.mark.parametrize("text", ["I don't know who won yesterday."])
    def test_chat_that_does_not_know_falls_back_to_search(
        self, logged_in: TestClient, post_chat: PostChat
    ) -> None:
        frames = post_chat({"message": "Who won yesterday?"})
        assert calls(frames)[0] == "web_search"
        assert said(frames).endswith("- [Old news](https://news.example.test/c)")


class TestClaimGuard:
    @pytest.mark.parametrize("text", ["Done! I've sent the email to Ada."])
    def test_unbacked_claim_is_replaced(self, logged_in: TestClient, post_chat: PostChat) -> None:
        with capture_logs() as logs:
            frames = post_chat({"message": "hello"})
        assert of(frames, "replace") == [{"text": HONEST}]
        messages = logged_in.get("/api/conversations").json()
        stored = logged_in.get(f"/api/conversations/{messages[0]['id']}/messages").json()
        assert stored[-1]["content"] == HONEST
        assert any(entry["event"] == "unbacked_action_claim" for entry in logs)


class TestEdit:
    @pytest.mark.parametrize("intents", [[[email("bob@example.test")], [event(start="15:00")]]])
    def test_edits_supersede_and_keep_the_same_draft(
        self,
        logged_in: TestClient,
        post_chat: PostChat,
        origin: dict[str, str],
        fake_google: ModuleType,
    ) -> None:
        mail = of(post_chat({"message": "email bob"}), "approval_required")[0]
        before = logged_in.get("/api/approvals").json()[0]
        change = {"to": "carol@example.test", "subject": "Paid", "body": "All paid."}
        response = logged_in.post(
            f"/api/approvals/{mail['approval_id']}/edit", json=change, headers=origin
        )
        assert response.status_code == 200, response.text
        fresh = response.json()
        assert fresh["id"] != mail["approval_id"] and fresh["status"] == "pending"
        assert fresh["payload"] == {**change, "draft_id": "d1", "thread_id": ""}
        assert fake_google.updated == [{**change, "draft_id": "d1"}]
        pending = logged_in.get("/api/approvals").json()
        assert [a["id"] for a in pending] == [fresh["id"]]
        assert before["payload"] != fresh["payload"]
        again = logged_in.post(
            f"/api/approvals/{mail['approval_id']}/edit", json=change, headers=origin
        )
        assert again.status_code == 409

        meeting = of(post_chat({"message": "meet at 3"}), "approval_required")[0]
        change_event = {
            "title": "Planning v2",
            "date": "2026-11-11",
            "start": "4pm",
            "end": "16:30",
            "attendees": ["ada@example.test"],
        }
        moved = logged_in.post(
            f"/api/approvals/{meeting['approval_id']}/edit", json=change_event, headers=origin
        ).json()
        assert moved["payload"]["start"] == "2026-11-11T16:00:00"
        assert moved["payload"]["title"] == "Planning v2"
        wrong = logged_in.post(f"/api/approvals/{moved['id']}/edit", json=change, headers=origin)
        assert wrong.status_code == 422

    def test_edit_hash_changes(
        self, logged_in: TestClient, app: FastAPI, origin: dict[str, str]
    ) -> None:
        with Session(app.state.engine) as session:
            old = request_send(session, 1, "d9", "a@example.test", "S", "B", "")
            old_id, old_hash = old.id, old.payload_hash
        change = {"to": "a@example.test", "subject": "S", "body": "B2"}
        fresh = logged_in.post(f"/api/approvals/{old_id}/edit", json=change, headers=origin).json()
        with Session(app.state.engine) as session:
            stored_old = session.get(Approval, old_id)
            stored_new = session.get(Approval, fresh["id"])
            assert stored_old is not None and stored_new is not None
            assert stored_old.status == "superseded"
            assert stored_new.payload_hash != old_hash
            assert json.loads(stored_new.payload_json)["body"] == "B2"


def refused(
    query: str = "",
    max_results: int = 0,
    to: str = "",
    subject: str = "",
    body: str = "",
    thread_id: str | None = None,
    start: str = "",
    end: str = "",
    duration_minutes: int = 0,
    working_hours: str = "",
    timezone: str | None = None,
    title: str = "",
    attendees: list[str] | None = None,
    description: str = "",
    location: str = "",
) -> dict[str, Any]:
    return {"error": "google_reconnect_required"}


def expired_google() -> FastMCP:
    server = FastMCP("expired-google")
    names = ("contacts_search", "mail_search", "mail_draft", "cal_list", "cal_find_free_slots")
    for name in (*names, "cal_create"):
        server.tool(refused, name=name)
    return server


class TestReconnect:
    @pytest.fixture
    def mcp(self) -> McpManager:
        toolset = MCPToolset(Client(expired_google()), id="google", tool_error_behavior="failed")
        return McpManager({"google": toolset})

    @pytest.mark.parametrize(
        "intents",
        [
            [[email("bob@example.test")]],
            [[event(start="10:00")]],
            [[{"kind": "read_calendar", "range": "tomorrow"}]],
            [[{"kind": "read_email", "sender": "Ada", "question": "anything?"}]],
            [
                [
                    {"kind": "read_calendar", "range": "today"},
                    {"kind": "read_email", "sender": "Ada", "question": "anything?"},
                ]
            ],
        ],
    )
    def test_every_job_asks_to_reconnect_once(self, post_chat: PostChat) -> None:
        frames = post_chat({"message": "Do the thing"})
        assert said(frames) == RECONNECT
        assert of(frames, "google_reconnect") == [{"url": "/settings"}]
        assert len(calls(frames)) == 1


class TestDraftQuality:
    @pytest.mark.parametrize(
        ("intents", "written"),
        [
            (
                [[email("Ada")]],
                [
                    {"subject": "the invoice is paid", "body": "the invoice is paid"},
                    {"subject": "Invoice paid", "body": f"Dear [Name],\n\n{PAID}\n\nBest,\n[Name]"},
                ],
            )
        ],
    )
    def test_echo_is_rewritten_and_placeholders_are_dropped(
        self, logged_in: TestClient, post_chat: PostChat, fake_google: ModuleType
    ) -> None:
        post_chat({"message": "email Ada the invoice is paid"})
        assert fake_google.drafted[0]["subject"] == "Invoice paid"
        assert fake_google.drafted[0]["body"] == f"Hi Ada,\n\n{PAID}\n\nBest,\nTester"

    @pytest.mark.parametrize(
        ("intents", "written"),
        [([[email("bob@example.test")]], [{"subject": "Note", "body": "Paid, see [link]."}])],
    )
    def test_a_second_bad_draft_is_cleaned_and_signed_with_the_signature(
        self, logged_in: TestClient, post_chat: PostChat, fake_google: ModuleType
    ) -> None:
        settings = logged_in.get("/api/settings").json()
        logged_in.put("/api/settings", json={**settings, "signature": "Cheers, Jo"}, headers=ORIGIN)
        post_chat({"message": "email bob paid"})
        assert fake_google.drafted[0]["body"] == "Hi,\n\nPaid, see.\n\nCheers, Jo"


class TestChatEdit:
    @pytest.mark.parametrize(
        ("intents", "written"),
        [
            (
                [[email("Ada")]],
                [
                    {"subject": "Invoice", "body": PAID},
                    {"subject": "Paid", "body": "Paid in full this morning."},
                ],
            )
        ],
    )
    def test_make_it_shorter_updates_the_same_draft_and_the_card(
        self, logged_in: TestClient, post_chat: PostChat, fake_google: ModuleType
    ) -> None:
        first = post_chat({"message": "email Ada the invoice is paid"})
        chat = first[0][1]["conversation_id"]
        old = of(first, "approval_required")[0]
        frames = post_chat({"message": "make it shorter", "conversation_id": chat})
        assert said(frames) == "Updated the draft. Edit it or press Send."
        fresh = of(frames, "approval_required")[0]
        assert fresh["approval_id"] != old["approval_id"]
        assert fresh["payload"]["draft_id"] == old["payload"]["draft_id"]
        assert fresh["payload"]["body"] == "Hi Ada,\n\nPaid in full this morning.\n\nBest,\nTester"
        assert fake_google.updated[0]["body"] == fresh["payload"]["body"]
        pending = logged_in.get("/api/approvals").json()
        assert [a["id"] for a in pending] == [fresh["approval_id"]]

    @pytest.mark.parametrize("intents", [[[email("bob@example.test")]]])
    def test_subject_change_is_literal_and_needs_no_model(
        self, logged_in: TestClient, post_chat: PostChat, fake_google: ModuleType
    ) -> None:
        chat = post_chat({"message": "email bob"})[0][1]["conversation_id"]
        frames = post_chat(
            {"message": "change subject to Lunch is on me!", "conversation_id": chat}
        )
        payload = of(frames, "approval_required")[0]["payload"]
        assert payload["subject"] == "Lunch is on me!" and payload["body"] == PAID_BODY
        assert frames[-1][1]["input_tokens"] == 0

    def test_edit_words_without_a_draft_go_to_the_intent_call(
        self, logged_in: TestClient, post_chat: PostChat
    ) -> None:
        frames = post_chat({"message": "make it shorter"})
        assert of(frames, "approval_required") == [] and said(frames) == TEXT


class TestSendStatus:
    @pytest.mark.parametrize("intents", [[[email("bob@example.test")]]])
    def test_answers_from_the_approvals(
        self, logged_in: TestClient, post_chat: PostChat, origin: dict[str, str]
    ) -> None:
        first = post_chat({"message": "email bob"})
        chat = first[0][1]["conversation_id"]
        status = post_chat({"message": "did you send it?", "conversation_id": chat})
        assert said(status) == (
            "Not yet. The draft to bob@example.test is waiting for you to press Send."
        )
        approval_id = of(first, "approval_required")[0]["approval_id"]
        logged_in.post(f"/api/approvals/{approval_id}/approve", headers=origin)
        sent = said(post_chat({"message": "did you send my email to Bob?"}))
        assert sent.startswith("Yes, sent to bob@example.test at ")
        assert said(post_chat({"message": "did you send it?"})) == (
            "No. Nothing has been sent from this chat."
        )
        assert said(post_chat({"message": "did you send it to Zed?"})) == (
            "No. I have not sent anything to zed."
        )

    @pytest.mark.parametrize(
        ("intents", "text"), [([[email("bob@example.test")]], "Sending it now. Done.")]
    )
    def test_claim_with_a_draft_waiting_tells_the_truth(
        self, logged_in: TestClient, post_chat: PostChat, fake_google: ModuleType
    ) -> None:
        chat = post_chat({"message": "email bob"})[0][1]["conversation_id"]
        frames = post_chat({"message": "hm, ship that thing over", "conversation_id": chat})
        assert of(frames, "replace") == [
            {
                "text": "I have not sent it. The draft to bob@example.test is waiting for you "
                "to press Send."
            }
        ]
        assert fake_google.executed == []


@pytest.mark.parametrize(
    ("text", "claims"),
    [
        ('Sending email to bob@example.test with subject "Budget". Done.', True),
        ('Subject changed to "Lunch is on me!". Ready to send.', True),
        ('Added "I\'m free Friday" to the draft. Press Send when ready.', True),
        ("I've updated the draft to be shorter.", True),
        ("Rosa sent you two emails about the proposal.", False),
        ("Your name is Omar.", False),
    ],
)
def test_claim_guard_catches_send_and_edit_claims(text: str, claims: bool) -> None:
    assert (review(text, acted=False) == HONEST) is claims


class TestVoice:
    @pytest.mark.parametrize("intents", [[[email("Rosa")]]])
    def test_a_pronoun_in_a_fresh_chat_asks_who_and_what(
        self, post_chat: PostChat, fake_google: ModuleType
    ) -> None:
        frames = post_chat({"message": "email her about it"})
        assert said(frames) == "Who should I email, and what about?"
        assert fake_google.drafted == []

    @pytest.mark.parametrize(
        "intents", [[[event(title="Call with Ada")], [email("Ada", body_instructions="moved")]]]
    )
    def test_a_pronoun_from_context_names_who_and_what(self, post_chat: PostChat) -> None:
        chat = post_chat({"message": "book a call with Ada"})[0][1]["conversation_id"]
        frames = post_chat({"message": "email her about it", "conversation_id": chat})
        assert said(frames) == "Draft to Ada about invoice is ready. Edit it or press Send."

    @pytest.mark.parametrize(
        ("intents", "written"),
        [
            (
                [
                    [
                        email(
                            "Ada",
                            body_instructions="tell her I can do a call Thursday if she wants",
                        )
                    ]
                ],
                [{"subject": "Call", "body": "I can do a call on Thursday if she wants to talk."}],
            )
        ],
    )
    def test_relayed_instructions_become_first_person(
        self, post_chat: PostChat, fake_google: ModuleType
    ) -> None:
        post_chat({"message": "email Ada, tell her I can do a call Thursday if she wants"})
        body = fake_google.drafted[0]["body"]
        assert "I can do a call on Thursday if that works for you." in body
        assert " she " not in body

    @pytest.mark.parametrize(
        "intents", [[[{"kind": "send_email", "to": "Ada", "body_instructions": "read it"}]]]
    )
    def test_respond_to_replies_in_the_thread_on_that_topic(
        self, post_chat: PostChat, fake_google: ModuleType
    ) -> None:
        post_chat({"message": "respond to Ada about the proposal, say I read it"})
        draft = fake_google.drafted[0]
        assert (draft["subject"], draft["thread_id"]) == ("Re: Proposal follow-up", "t3")

    @pytest.mark.parametrize("intents", [[[email("accounts@harbor&pine.com")]]])
    def test_an_address_the_model_made_up_is_looked_up_instead(
        self, post_chat: PostChat, fake_google: ModuleType
    ) -> None:
        fake_google.MESSAGES["m5"] = {
            "id": "m5",
            "thread_id": "t5",
            "from": '"Accounts, Harbor & Pine" <accounts@harborpine.example.test>',
            "subject": "Invoice DW-1",
            "labels": ["INBOX"],
            "body": "<untrusted>Invoice attached.</untrusted>",
        }
        post_chat({"message": "email accounts at harbor & pine that the invoice is paid"})
        assert fake_google.drafted[0]["to"] == "accounts@harborpine.example.test"
        assert fake_google.drafted[0]["body"].startswith("Hi Accounts,")

    @pytest.mark.parametrize("intents", [[[email("ada@example.test")]]])
    def test_a_typed_address_gets_the_known_name(
        self, post_chat: PostChat, fake_google: ModuleType
    ) -> None:
        post_chat({"message": "email ada@example.test that the invoice is paid"})
        assert fake_google.drafted[0]["body"].startswith("Hi Ada,\n\n")

    @pytest.mark.parametrize(
        ("intents", "written"),
        [
            (
                [[email("Ada")]],
                [
                    {"subject": "Invoice", "body": PAID},
                    {"subject": "Invoice", "body": " ".join(["Warm thanks again,"] * 8)},
                    {"subject": "Invoice", "body": "Good news, the invoice was paid this morning."},
                ],
            )
        ],
    )
    def test_warmer_keeps_the_length(self, post_chat: PostChat) -> None:
        chat = post_chat({"message": "email Ada the invoice is paid"})[0][1]["conversation_id"]
        frames = post_chat({"message": "make it warmer", "conversation_id": chat})
        body = of(frames, "approval_required")[0]["payload"]["body"]
        assert "Good news, the invoice was paid this morning." in body

    @pytest.mark.parametrize("intents", [[[email("bob@example.test")]]])
    def test_fire_it_off_sends_the_waiting_draft(
        self, post_chat: PostChat, fake_google: ModuleType
    ) -> None:
        chat = post_chat({"message": "email bob"})[0][1]["conversation_id"]
        frames = post_chat({"message": "ok fire it off", "conversation_id": chat})
        assert said(frames).endswith("(mail_send): done.")
        assert fake_google.executed[0]["action"] == "mail_send"

    @pytest.mark.parametrize(
        "text", ["Based on the provided text, your dog is called Biscuit and loves long walks."]
    )
    def test_scaffolding_is_scrubbed(self, post_chat: PostChat) -> None:
        frames = post_chat({"message": "tell me about my dog"})
        assert of(frames, "replace")[-1]["text"] == (
            "Your dog is called Biscuit and loves long walks."
        )

    @pytest.mark.parametrize("text", ["The email to bob@example.test has been sent."])
    def test_a_send_claim_in_any_answer_is_replaced(self, post_chat: PostChat) -> None:
        frames = post_chat({"message": "what did ada say about the invoice?"})
        assert of(frames, "replace")[-1]["text"] == HONEST


class TestDaySummary:
    def sent_today(self, fake_google: ModuleType) -> None:
        stamp = str(int(time.time() * 1000))
        fake_google.MESSAGES["m9"] = {
            "id": "m9",
            "thread_id": "t9",
            "from": "tester@example.test",
            "to": "Ada Example <ada@example.test>",
            "subject": "Budget",
            "labels": ["SENT"],
            "metadata": {"internal_date": stamp},
            "body": "<untrusted>Here it is.</untrusted>",
        }

    @pytest.mark.parametrize("text", ["You haven't sent any email today."])
    def test_is_grounded_in_sent_mail_and_open_items(
        self, post_chat: PostChat, fake_google: ModuleType, app: FastAPI
    ) -> None:
        self.sent_today(fake_google)
        fake_google.MESSAGES["m4"]["metadata"] = {"internal_date": "1700000000000"}
        with Session(app.state.engine) as session:
            request_send(session, 1, "d7", "sam@example.test", "Lunch", "Hi", "")
        frames = post_chat({"message": "what did I get done today and what's still open?"})
        assert calls(frames) == ["mail_profile", "mail_search", "mail_search"]
        shown = of(frames, "replace")[-1]["text"]
        assert 'Sent to Ada Example: "Budget" at ' in shown
        assert 'Draft to sam@example.test "Lunch" waits for Send' in shown
        assert 'ada@example.test is waiting on your reply: "Invoice 42"' in shown
        assert "Proposal follow-up" not in shown

    def test_nothing_needs_no_model(self, post_chat: PostChat, fake_google: ModuleType) -> None:
        fake_google.MESSAGES.clear()
        frames = post_chat({"message": "what did I send today?"})
        assert said(frames) == "Nothing sent or booked today, and nothing is waiting on you."
        assert frames[-1][1]["input_tokens"] == 0


def test_a_pronoun_first_message_asks_without_the_model(post_chat: PostChat) -> None:
    frames = post_chat({"message": "email her about it"})
    assert said(frames) == "Who should I email, and what about?"
    assert frames[-1][1]["input_tokens"] == 0


QA_BODIES = [
    (
        "The deck is now ready for your review. If you have any feedback, please ping me "
        "directly. Let me know if that works for you.",
        "The deck is now ready for your review. If you have any feedback, please ping me directly.",
    ),
    (
        "I will be about 10 minutes late to our lunch on Friday. If that works for you, I'll "
        "see you there shortly.",
        "I will be about 10 minutes late to our lunch on Friday. I'll see you there shortly.",
    ),
    (
        "The backup finished fine last night. If that works for you, let me know.",
        "The backup finished fine last night.",
    ),
    (
        "Could you send over the logo files by Thursday? If that works for you, please let me "
        "know. Thanks!",
        "Could you send over the logo files by Thursday? Thanks!",
    ),
    (
        "Can we move our call to next week? Please let me know what day suits you best.",
        "Can we move our call to next week? Please let me know what day suits you best.",
    ),
    ("Let me know if that works for you.", "Let me know if that works for you."),
]


@pytest.mark.parametrize(("body", "expected"), QA_BODIES)
def test_filler_closers_are_trimmed(body: str, expected: str) -> None:
    assert send_email.without_filler(body) == expected


def test_repeated_sign_offs_are_all_split_off() -> None:
    body = "Hi Bo,\n\nPaid.\n\nBest,\nSam\n\nKind regards,\nSam"
    assert send_email.split(body) == ("Hi Bo,", "Paid.", "Best,\nSam")


class TestSignOff:
    @pytest.fixture
    def settings(self, settings: Settings) -> Settings:
        return settings.model_copy(update={"user_name": "there"})

    @pytest.fixture(autouse=True)
    def fresh_cache(self) -> None:
        send_email.PROFILE_NAMES.clear()

    @pytest.mark.parametrize(
        ("intents", "written"),
        [
            (
                [[email("Ada")], [email("Ada")]],
                [{"subject": "Paid", "body": f"{PAID} Let me know if that works for you."}],
            )
        ],
    )
    def test_the_gmail_name_signs_and_is_looked_up_once(
        self, post_chat: PostChat, fake_google: ModuleType
    ) -> None:
        post_chat({"message": "email Ada the invoice is paid"})
        fake_google.ACCOUNT_NAME = "Someone Else"
        post_chat({"message": "email Ada the invoice is paid"})
        bodies = [draft["body"] for draft in fake_google.drafted]
        assert bodies == [f"Hi Ada,\n\n{PAID}\n\nBest,\nSam"] * 2

    @pytest.mark.parametrize(
        ("intents", "written"),
        [([[email("Ada")]], [{"subject": "Paid", "body": f"{PAID}\n\nBest,\nJordan"}])],
    )
    def test_no_name_anywhere_still_signs_off_once(
        self, post_chat: PostChat, fake_google: ModuleType
    ) -> None:
        fake_google.ACCOUNT_NAME = ""
        post_chat({"message": "email Ada the invoice is paid"})
        assert fake_google.drafted[0]["body"] == f"Hi Ada,\n\n{PAID}\n\nBest,"

    @pytest.mark.parametrize(
        ("intents", "written"),
        [([[email("Ada")]], [{"subject": "Paid", "body": PAID}])],
    )
    def test_a_plain_signature_gets_best(
        self, logged_in: TestClient, post_chat: PostChat, fake_google: ModuleType
    ) -> None:
        settings = logged_in.get("/api/settings").json()
        logged_in.put("/api/settings", json={**settings, "signature": "Jo"}, headers=ORIGIN)
        post_chat({"message": "email Ada the invoice is paid"})
        assert fake_google.drafted[0]["body"] == f"Hi Ada,\n\n{PAID}\n\nBest,\nJo"
