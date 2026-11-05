"""QA round 1 on the real stack: follow-ups, moving and cancelling events, relative and numeric
dates, remembered facts, free/busy questions and dated web searches."""

import statistics
from collections.abc import Iterator
from datetime import date, timedelta
from typing import Any

import httpx
import pytest

from homer_core.agent.dates import weekday_date

from .conftest import require_ollama
from .real_stack import Stack, local_offset, local_today, real_stack
from .test_core_jobs import DUCKDUCKGO, RUNS, Reply, Talk, connect, record, timed_chat

pytestmark = pytest.mark.e2e


def day(offset: int) -> date:
    return local_today() + timedelta(days=offset)


def next_week_offset(weekday: int) -> int:
    return 7 - local_today().weekday() + weekday


def event(
    event_id: str, title: str, offset: int, utc_start: str, utc_end: str, *attendees: str
) -> dict[str, Any]:
    return {
        "id": event_id,
        "weekday": local_offset(offset),
        "start": utc_start,
        "end": utc_end,
        "summary": title,
        "location": "",
        "description": "",
        "attendees": list(attendees),
    }


ROSA = "rosa.lindgren@example.test"
EXTRA = (
    event("evt_r1", "Workshop prep for Meridian Roast", 1, "04:30", "05:30", ROSA),
    event("evt_r2", "Design review: packaging drafts", 2, "09:00", "09:45"),
    event("evt_r3", "Lunch with Sam, mentor", 4, "08:00", "09:00", "sam.reyes@example.test"),
    event("evt_r4", "Pitch rehearsal: Harbor & Pine packaging", 6, "05:00", "06:30"),
    event("evt_r5", "Admin block: invoices and bookkeeping", next_week_offset(0), "04:00", "06:00"),
    event("evt_r6", "Portfolio review", next_week_offset(2), "06:00", "07:00", ROSA),
)


@pytest.fixture(scope="module")
def stack(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Stack]:
    require_ollama()
    with real_stack(tmp_path_factory.mktemp("homer-r1-home"), extra_events=EXTRA) as running:
        yield running


@pytest.fixture
def client(stack: Stack) -> Iterator[httpx.Client]:
    with connect(stack) as http_client:
        yield http_client


@pytest.fixture
def talk(client: httpx.Client, request: pytest.FixtureRequest) -> Talk:
    def send(message: str, conversation: int | None = None) -> Reply:
        body: dict[str, Any] = {"message": message}
        if conversation is not None:
            body["conversation_id"] = conversation
        reply = timed_chat(client, body)
        record(request.node.originalname, reply)
        reply.finished()
        return reply

    return send


def changes(reply: Reply) -> dict[str, Any]:
    assert reply.actions == ["cal_update"], (reply.tools, reply.said)
    return reply.of("approval_required")[0]["payload"]["changes"]


@pytest.mark.parametrize("run", RUNS)
def test_follow_ups_keep_the_context(talk: Talk, run: int) -> None:
    first = talk("what's on my calendar tomorrow?")
    assert "Workshop prep" in first.said, first.said
    after = talk("and the day after?", first.conversation)
    assert "Design review" in after.said and "Workshop prep" not in after.said, after.said
    rosa = talk("what about Rosa, anything with her?", after.conversation)
    assert "Workshop prep" in rosa.said and "Design review" not in rosa.said, rosa.said


@pytest.mark.parametrize("run", RUNS)
def test_person_this_week(talk: Talk, run: int) -> None:
    if day(1).weekday() == 0:
        pytest.skip("tomorrow is next week")
    reply = talk("anything this week with Rosa?")
    assert "Workshop prep" in reply.said, reply.said


@pytest.mark.parametrize("run", RUNS)
def test_move_keeps_the_date(talk: Talk, run: int) -> None:
    reply = talk("move my design review to 4pm")
    on = day(2).isoformat()
    assert changes(reply) == {
        "start": f"{on}T16:00:00+05:00",
        "end": f"{on}T16:45:00+05:00",
    }, reply.said
    assert "Design review" in reply.of("approval_required")[0]["preview"]


@pytest.mark.parametrize("run", RUNS)
def test_reschedule_to_a_time(talk: Talk, run: int) -> None:
    reply = talk("reschedule the pitch rehearsal to 2pm")
    on = day(6).isoformat()
    assert changes(reply)["start"] == f"{on}T14:00:00+05:00", reply.said


@pytest.mark.parametrize("run", RUNS)
def test_cancel_needs_approval(stack: Stack, client: httpx.Client, talk: Talk, run: int) -> None:
    events = stack.counts()["events"]
    reply = talk("cancel the lunch with Sam")
    assert reply.actions == ["cal_delete"], (reply.tools, reply.said)
    assert reply.of("approval_required")[0]["payload"] == {"event_id": "evt_r3"}
    assert "cancelled" not in reply.said.lower() and stack.counts()["events"] == events
    if run == RUNS[-1]:
        approval = reply.of("approval_required")[0]["approval_id"]
        done = client.post(f"/api/approvals/{approval}/approve").json()
        assert done["status"] == "done" and stack.counts()["events"] == events - 1


@pytest.mark.parametrize("run", RUNS)
def test_next_wednesday(talk: Talk, run: int) -> None:
    reply = talk("schedule coffee with Maya next wed 11am")
    assert reply.actions == ["cal_create"], (reply.tools, reply.said)
    wanted = weekday_date("next wed", local_today())
    assert wanted is not None
    start = reply.of("approval_required")[0]["payload"]["start"]
    assert start == f"{wanted.isoformat()}T11:00:00+05:00", start


@pytest.mark.parametrize("run", RUNS)
def test_correction_replaces_the_card(client: httpx.Client, talk: Talk, run: int) -> None:
    first = talk("add a call with Maya wednesday 3pm")
    assert first.actions == ["cal_create"], (first.tools, first.said)
    fixed = talk("no, I meant Friday", first.conversation)
    assert fixed.actions == ["cal_create"], (fixed.tools, fixed.said)
    start = date.fromisoformat(fixed.of("approval_required")[0]["payload"]["start"][:10])
    assert start.weekday() == 4 and start - local_today() < timedelta(days=14), start
    pending = [approval["id"] for approval in client.get("/api/approvals").json()]
    assert pending == [fixed.of("approval_required")[0]["approval_id"]]


@pytest.mark.parametrize("run", RUNS)
def test_numeric_date_is_day_first(talk: Talk, run: int) -> None:
    on = day(2)
    reply = talk(f"calendar for {on.day}/{on.month}")
    assert "Design review" in reply.said, reply.said


def test_how_busy_is_next_week(talk: Talk) -> None:
    reply = talk("how busy is next week")
    assert "Admin block" in reply.said and "Portfolio review" in reply.said, reply.said


def test_am_i_free_answers_first(talk: Talk) -> None:
    reply = talk("am I free tomorrow afternoon?")
    assert reply.said.startswith("No, you are busy."), reply.said
    assert "Studio visit" in reply.said, reply.said


def test_remember_recall_forget(client: httpx.Client, talk: Talk) -> None:
    stored = talk("My dog is Biscuit, remember that")
    assert any("Biscuit" in f["text"] for f in client.get("/api/facts").json()), stored.said
    asked = talk("What's my dog's name?")
    assert "Biscuit" in asked.said and "web_search" not in asked.tools, asked.said
    talk("forget that", asked.conversation)
    assert not any("Biscuit" in f["text"] for f in client.get("/api/facts").json())


@pytest.fixture(scope="module")
def web_stack(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Stack]:
    require_ollama()
    try:
        httpx.get(DUCKDUCKGO, timeout=5.0).raise_for_status()
    except httpx.HTTPError as error:
        pytest.skip(f"DuckDuckGo not reachable: {error}")
    with real_stack(tmp_path_factory.mktemp("homer-r1-web"), web_search=True) as running:
        yield running


SEARCHES = (
    "whats the weather in Lahore today",
    "latest news on Nvidia",
    "who won the premier league match yesterday",
    "current price of bitcoin",
    "who won the last f1 race",
)


def test_searches_are_dated_and_fast(web_stack: Stack) -> None:
    yesterday = day(-1)
    seconds = []
    with connect(web_stack) as client:
        for question in SEARCHES:
            reply = timed_chat(client, {"message": question})
            record("test_searches_are_dated_and_fast", reply)
            reply.finished()
            assert reply.tools[0] == "web_search", (reply.tools, reply.said)
            assert "Sources:" in reply.said, reply.said
            seconds.append(reply.seconds)
            if "yesterday" in question:
                query = reply.of("tool_call")[0]["args"]["query"]
                assert f"{yesterday.day} {yesterday:%B}" in query, query
    print("search seconds", [round(s, 1) for s in seconds])
    assert statistics.median(seconds) < 20, seconds
