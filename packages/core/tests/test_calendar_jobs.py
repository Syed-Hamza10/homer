import json
from datetime import date, datetime, timedelta
from types import ModuleType
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastmcp.client import Client
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models import Model
from sqlmodel import Session, select

from homer_core.config import Settings
from homer_core.db.models import Approval, Message
from homer_core.mcp.manager import McpManager

from .conftest import ORIGIN, JobModel, PostChat, load_fake_server
from .test_jobs import calls, of, said

KARACHI = "Asia/Karachi"
ZONE = ZoneInfo(KARACHI)


def today() -> date:
    return datetime.now(ZONE).date()


def day(offset: int) -> date:
    return today() + timedelta(days=offset)


def entry(
    event_id: str, title: str, offset: int, opens: str, closes: str, *attendees: str
) -> dict[str, Any]:
    on = day(offset).isoformat()
    return {
        "id": event_id,
        "title": title,
        "start": f"{on}T{opens}:00+05:00",
        "end": f"{on}T{closes}:00+05:00",
        "attendees": list(attendees),
    }


WORKSHOP = entry("w1", "Workshop prep for Meridian Roast", 1, "09:30", "10:30", "rosa@example.test")
REVIEW = entry("r1", "Design review: packaging drafts", 1, "14:00", "14:45")
LUNCH = entry("l1", "Lunch with Sam, mentor", 4, "13:00", "14:00", "sam@example.test")
SECOND_LUNCH = entry("l2", "Lunch with Sam", 9, "13:00", "14:00")


def short(offset: int) -> str:
    return f"{day(offset):%a %d %b}"


@pytest.fixture
def settings(settings: Settings) -> Settings:
    return settings.model_copy(update={"timezone": KARACHI})


@pytest.fixture
def fake_search() -> ModuleType:
    return load_fake_server("search")


@pytest.fixture
def mcp(fake_google: ModuleType, fake_search: ModuleType) -> McpManager:
    fake_google.EVENTS[:] = [WORKSHOP, REVIEW, LUNCH]
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
def seen() -> list[list[ModelMessage]]:
    return []


@pytest.fixture
def model(
    jobs: JobModel, intents: list[list[dict[str, Any]]], text: str, seen: list[list[ModelMessage]]
) -> Model:
    return jobs(intents, text=text, seen=seen)


def read(**fields: Any) -> dict[str, Any]:
    return {"kind": "read_calendar", **fields}


class TestReadCalendar:
    @pytest.mark.parametrize("intents", [[[read(range="this_week", person="Rosa")]]])
    def test_person_filter_matches_attendees(self, post_chat: PostChat) -> None:
        lines = said(post_chat({"message": "anything this week with Rosa?"})).splitlines()
        assert lines[0].endswith("with Rosa (1 event):")
        assert lines[1:] == [f"- {short(1)} 09:30-10:30 Workshop prep for Meridian Roast"]

    @pytest.mark.parametrize("intents", [[[read(range="tomorrow", title_contains="DESIGN")]]])
    def test_title_filter_ignores_case(self, post_chat: PostChat) -> None:
        lines = said(post_chat({"message": "when is the design review"})).splitlines()
        assert lines[1:] == ["- 14:00-14:45 Design review: packaging drafts"]

    @pytest.mark.parametrize(
        "intents", [[[read(range="tomorrow", start="12:00", end="17:00", asks_if="free")]]]
    )
    def test_free_question_answers_no_first(
        self, post_chat: PostChat, fake_google: ModuleType
    ) -> None:
        fake_google.EVENTS[:] = [WORKSHOP, REVIEW]
        reply = said(post_chat({"message": "am I free tomorrow afternoon?"}))
        assert reply.startswith("No, you are busy. Tomorrow, ")
        assert reply.endswith(", 12:00-17:00:\n- 14:00-14:45 Design review: packaging drafts")

    @pytest.mark.parametrize("intents", [[[read(range="tomorrow", start="11:00", asks_if="busy")]]])
    def test_busy_question_at_a_time_answers_no_when_free(self, post_chat: PostChat) -> None:
        reply = said(post_chat({"message": "am i busy tomorrow at 11?"}))
        assert reply.startswith("No, you are free. Tomorrow, ")
        assert reply.endswith("11:00-11:30: nothing on your calendar.")

    @pytest.mark.parametrize("intents", [[[read(range="next_week")]]])
    def test_next_week_lists_monday_to_sunday_with_a_count(self, post_chat: PostChat) -> None:
        frames = post_chat({"message": "how busy is next week"})
        monday = today() - timedelta(days=today().weekday()) + timedelta(days=7)
        assert of(frames, "tool_call")[0]["args"]["start"] == f"{monday.isoformat()}T00:00:00+05:00"
        assert said(frames).startswith(f"Next week, {monday:%A %d %B} to ")
        assert "(3 events):" in said(frames)

    @pytest.mark.parametrize(
        "intents", [[[read(range="tomorrow")], [read(range="date", date=day(2).isoformat())]]]
    )
    def test_each_turn_stores_its_resolved_dates(self, post_chat: PostChat, app: FastAPI) -> None:
        first = post_chat({"message": "what's on tomorrow"})
        conversation = first[0][1]["conversation_id"]
        post_chat({"message": "and the day after?", "conversation_id": conversation})
        with Session(app.state.engine) as session:
            rows = session.exec(select(Message).where(Message.role == "assistant")).all()
            stored = [json.loads(row.context_json or "[]") for row in rows]
        assert stored[0] == [
            {
                "kind": "read_calendar",
                "range": "tomorrow",
                "date": day(1).isoformat(),
                "end_date": day(1).isoformat(),
            }
        ]
        assert stored[1][0]["date"] == day(2).isoformat()


def update(**fields: Any) -> dict[str, Any]:
    return {"kind": "update_event", **fields}


class TestChangeEvent:
    @pytest.mark.parametrize("intents", [[[update(match="design review", new_start="4pm")]]])
    def test_move_keeps_the_date_and_length(self, post_chat: PostChat) -> None:
        frames = post_chat({"message": "move my design review to 4pm"})
        approval = of(frames, "approval_required")[0]
        assert approval["action"] == "cal_update"
        assert approval["payload"] == {
            "event_id": "r1",
            "changes": {
                "start": f"{day(1).isoformat()}T16:00:00+05:00",
                "end": f"{day(1).isoformat()}T16:45:00+05:00",
            },
        }
        preview = (
            f"Move 'Design review: packaging drafts' from {short(1)} 14:00-14:45 "
            f"to {short(1)} 16:00-16:45"
        )
        assert approval["preview"] == preview
        assert said(frames) == (
            f"Ready to move 'Design review: packaging drafts' from {short(1)} 14:00-14:45 to "
            f"{short(1)} 16:00-16:45. Press Approve to apply it, or Reject."
        )
        assert calls(frames) == ["cal_list", "cal_update"]

    @pytest.mark.parametrize("intents", [[[update(match="pitch", new_date=day(3).isoformat())]]])
    def test_nothing_matching_says_so(self, post_chat: PostChat) -> None:
        frames = post_chat({"message": "reschedule the pitch rehearsal to monday"})
        assert said(frames) == (
            "I found no event matching 'pitch' between last week and next month."
        )
        assert of(frames, "approval_required") == []

    @pytest.mark.parametrize("intents", [[[update(match="workshop", new_date=day(3).isoformat())]]])
    def test_new_date_keeps_the_time(self, post_chat: PostChat) -> None:
        changes = of(post_chat({"message": "move the workshop"}), "approval_required")[0][
            "payload"
        ]["changes"]
        assert changes["start"] == f"{day(3).isoformat()}T09:30:00+05:00"

    @pytest.mark.parametrize(
        "intents", [[[{"kind": "cancel_event", "match": "the lunch with Sam"}]]]
    )
    def test_several_matches_are_listed(self, post_chat: PostChat, fake_google: ModuleType) -> None:
        fake_google.EVENTS.append(SECOND_LUNCH)
        frames = post_chat({"message": "cancel the lunch with Sam"})
        assert of(frames, "approval_required") == []
        assert said(frames) == (
            "Several events match 'the lunch with Sam':\n"
            f"- {short(4)} 13:00-14:00 Lunch with Sam, mentor\n"
            f"- {short(9)} 13:00-14:00 Lunch with Sam\nWhich one do you mean?"
        )

    @pytest.mark.parametrize("intents", [[[{"kind": "cancel_event", "match": "lunch with Sam"}]]])
    def test_cancel_asks_for_approval_then_deletes(
        self, post_chat: PostChat, logged_in: TestClient, fake_google: ModuleType
    ) -> None:
        frames = post_chat({"message": "cancel the lunch with Sam"})
        approval = of(frames, "approval_required")[0]
        assert approval["action"] == "cal_delete" and approval["payload"] == {"event_id": "l1"}
        assert said(frames).startswith(f"Ready to delete 'Lunch with Sam, mentor' on {short(4)}")
        assert fake_google.executed == []
        done = logged_in.post(f"/api/approvals/{approval['approval_id']}/approve", headers=ORIGIN)
        assert done.json()["status"] == "done"
        assert fake_google.executed[0]["action"] == "cal_delete"

    @pytest.mark.parametrize("intents", [[[update(match="design review")]]])
    def test_nothing_to_change_asks(self, post_chat: PostChat) -> None:
        assert said(post_chat({"message": "move the design review"})).startswith("What should")


def booking(on: date) -> dict[str, Any]:
    return {
        "kind": "create_event",
        "title": "Call with Rosa",
        "date": on.isoformat(),
        "start": "3pm",
    }


class TestCorrection:
    @pytest.mark.parametrize("intents", [[[booking(day(5))], [booking(day(7))]]])
    def test_correction_supersedes_the_pending_card(
        self, post_chat: PostChat, logged_in: TestClient, app: FastAPI
    ) -> None:
        first = post_chat({"message": "add a call with Rosa at 3pm"})
        old = of(first, "approval_required")[0]["approval_id"]
        second = post_chat(
            {
                "message": "no, I meant the other day",
                "conversation_id": first[0][1]["conversation_id"],
            }
        )
        fresh = of(second, "approval_required")[0]["approval_id"]
        pending = [a["id"] for a in logged_in.get("/api/approvals").json()]
        assert pending == [fresh]
        with Session(app.state.engine) as session:
            stored = session.get(Approval, old)
            assert stored is not None and stored.status == "superseded"

    @pytest.mark.parametrize("intents", [[[booking(day(5))], [booking(day(7))]]])
    def test_a_new_request_keeps_the_earlier_card(
        self, post_chat: PostChat, logged_in: TestClient
    ) -> None:
        first = post_chat({"message": "add a call with Rosa at 3pm"})
        post_chat(
            {"message": "and another call later", "conversation_id": first[0][1]["conversation_id"]}
        )
        assert len(logged_in.get("/api/approvals").json()) == 2


class TestMemory:
    @pytest.mark.parametrize(
        ("intents", "text"),
        [
            (
                [
                    [{"kind": "remember", "fact": "The user's dog is called Biscuit."}],
                    [{"kind": "chat"}],
                ],
                "Your dog is called Biscuit.",
            )
        ],
    )
    def test_remembered_fact_reaches_the_chat_prompt(
        self, post_chat: PostChat, logged_in: TestClient, seen: list[list[ModelMessage]]
    ) -> None:
        stored = post_chat({"message": "My dog is Biscuit, remember that"})
        assert said(stored) == "Saved to memory: Your dog is Biscuit."
        facts = logged_in.get("/api/facts").json()
        assert [(f["text"], f["source"]) for f in facts] == [("Your dog is Biscuit.", "user")]
        answer = post_chat({"message": "what's my dog's name?"})
        assert said(answer) == "Your dog is called Biscuit." and calls(answer) == []
        instructions = str(getattr(seen[-1][-1], "instructions", ""))
        assert "- Your dog is Biscuit." in instructions

    @pytest.mark.parametrize(
        "intents",
        [
            [
                [{"kind": "remember", "fact": "The user likes tea."}],
                [{"kind": "remember", "fact": "The user's dog is Biscuit."}],
                [{"kind": "forget"}],
            ]
        ],
    )
    def test_forget_that_deletes_the_newest(
        self, post_chat: PostChat, logged_in: TestClient
    ) -> None:
        post_chat({"message": "I like tea, remember"})
        post_chat({"message": "my dog is Biscuit, remember"})
        assert said(post_chat({"message": "forget that"})) == "Forgot: Your dog is Biscuit."
        facts = logged_in.get("/api/facts").json()
        assert [fact["text"] for fact in facts] == ["You like tea."]
        gone = logged_in.delete(f"/api/facts/{facts[0]['id']}", headers=ORIGIN)
        assert gone.status_code == 204
        assert logged_in.get("/api/facts").json() == []
        missing = logged_in.delete(f"/api/facts/{facts[0]['id']}", headers=ORIGIN)
        assert missing.status_code == 404

    @pytest.mark.parametrize("text", ["I don't know your dog's name."])
    def test_personal_question_never_searches_the_web(self, post_chat: PostChat) -> None:
        assert calls(post_chat({"message": "what was my dog's name again?"})) == []


def next_on(weekday: int) -> int:
    """Days from today to the next given weekday, at least one."""
    return (weekday - today().weekday() - 1) % 7 + 1


MONDAY, TUESDAY = next_on(0), next_on(1)
ELENA_CALL = entry(
    "c1", "call with Elena Marchetti", MONDAY, "12:00", "12:45", "elena@example.test"
)
STUDIO = entry("s1", "Studio visit with Elena Marchetti", 2, "10:00", "11:00")
ADMIN = entry("a1", "Admin block: invoices", MONDAY, "09:00", "11:00")


def at(offset: int, clock: str) -> str:
    return f"{day(offset).isoformat()}T{clock}:00+05:00"


def booked(**fields: Any) -> dict[str, Any]:
    return {"kind": "create_event", "title": "call with Elena Marchetti", **fields}


class TestMove:
    @pytest.mark.parametrize(
        "intents",
        [
            [
                [booked(date=day(MONDAY).isoformat(), start="12:00", duration_minutes=45)],
                [booked(date=day(TUESDAY).isoformat(), window_start="09:00", window_end="12:00")],
            ]
        ],
    )
    def test_moving_a_proposed_event_replaces_its_card_and_keeps_its_length(
        self, post_chat: PostChat, logged_in: TestClient
    ) -> None:
        first = post_chat({"message": "schedule a call with Elena Monday at noon, 45 minutes"})
        chat = first[0][1]["conversation_id"]
        frames = post_chat(
            {"message": "actually move it to Tuesday morning, same length", "conversation_id": chat}
        )
        card = of(frames, "approval_required")[0]
        assert card["action"] == "cal_create"
        assert (card["payload"]["start"], card["payload"]["end"]) == (
            at(TUESDAY, "09:00"),
            at(TUESDAY, "09:45"),
        )
        assert said(frames).startswith("Moved it: 'call with Elena Marchetti' on ")
        assert [a["id"] for a in logged_in.get("/api/approvals").json()] == [card["approval_id"]]

    @pytest.mark.parametrize(
        "intents",
        [
            [
                [
                    update(
                        match="Monday call with Elena",
                        new_date=day(TUESDAY).isoformat(),
                        new_start="9am",
                    )
                ]
            ],
            [
                [
                    update(
                        match="call with Elena",
                        date=day(TUESDAY).isoformat(),
                        new_date=day(TUESDAY).isoformat(),
                        new_start="9am",
                    )
                ]
            ],
        ],
    )
    def test_the_old_day_and_person_find_it_and_the_new_day_never_filters(
        self, post_chat: PostChat, fake_google: ModuleType
    ) -> None:
        fake_google.EVENTS[:] = [WORKSHOP, ELENA_CALL]
        frames = post_chat({"message": "move my Monday call with Elena to Tuesday 9am"})
        assert of(frames, "approval_required")[0]["payload"] == {
            "event_id": "c1",
            "changes": {"start": at(TUESDAY, "09:00"), "end": at(TUESDAY, "09:45")},
        }

    @pytest.mark.parametrize("intents", [[[update(match="the call with Elena", new_start="4pm")]]])
    def test_a_partial_title_still_finds_the_one_event(
        self, post_chat: PostChat, fake_google: ModuleType
    ) -> None:
        fake_google.EVENTS[:] = [WORKSHOP, STUDIO]
        payload = of(post_chat({"message": "push the call with Elena to 4pm"}), "approval_required")
        assert payload[0]["payload"]["event_id"] == "s1"

    @pytest.mark.parametrize(
        "intents",
        [
            [
                [booked(date=day(MONDAY).isoformat(), start="12:00", end="12:45")],
                [{"kind": "chat"}],
                [update(match="the call we just booked", new_start="4pm")],
            ]
        ],
    )
    def test_it_means_the_event_booked_turns_ago(
        self, post_chat: PostChat, logged_in: TestClient, fake_google: ModuleType
    ) -> None:
        first = post_chat({"message": "book a call with Elena monday 12 to 12:45"})
        chat = first[0][1]["conversation_id"]
        card = of(first, "approval_required")[0]["approval_id"]
        logged_in.post(f"/api/approvals/{card}/approve", headers=ORIGIN)
        post_chat({"message": "thanks", "conversation_id": chat})
        frames = post_chat(
            {"message": "move the call we just booked to 4pm", "conversation_id": chat}
        )
        moved = of(frames, "approval_required")[0]
        assert moved["action"] == "cal_update"
        assert moved["payload"]["event_id"] == "evt_new1"
        assert moved["payload"]["changes"] == {
            "start": at(MONDAY, "16:00"),
            "end": at(MONDAY, "16:45"),
        }

    @pytest.mark.parametrize(
        "intents", [[[{"kind": "cancel_event", "match": "admin block monday"}]]]
    )
    def test_drop_the_admin_block_monday(
        self, post_chat: PostChat, fake_google: ModuleType
    ) -> None:
        fake_google.EVENTS[:] = [ADMIN, WORKSHOP]
        frames = post_chat({"message": "dont need the admin block monday anymore, drop it"})
        assert of(frames, "approval_required")[0]["payload"] == {"event_id": "a1"}

    @pytest.mark.parametrize(
        "intents",
        [
            [
                [booked(date=day(3).isoformat(), start="11:00", end="12:00")],
                [booked(date=day(3).isoformat(), start="2pm")],
            ]
        ],
    )
    def test_a_time_only_correction_keeps_the_length(self, post_chat: PostChat) -> None:
        chat = post_chat({"message": "book a 1 hour review at 11am"})[0][1]["conversation_id"]
        frames = post_chat({"message": "make it 2pm instead", "conversation_id": chat})
        payload = of(frames, "approval_required")[0]["payload"]
        assert payload["end"].startswith(f"{day(3).isoformat()}T15:00")


class TestNextMeeting:
    @pytest.mark.parametrize("intents", [[[read(range="today")]]])
    def test_names_only_the_next_one(self, post_chat: PostChat) -> None:
        assert said(post_chat({"message": "when's my next meeting?"})) == (
            f"Your next one is Workshop prep for Meridian Roast, {day(1):%A %d %B} 09:30-10:30."
        )
