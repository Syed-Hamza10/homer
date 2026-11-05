"""Round 2 trust fixes on the real stack with the live model, three runs per scenario."""

import re
from collections.abc import Iterator
from datetime import date, timedelta

import httpx
import pytest

from homer_core.agent.voice import leaks

from .conftest import require_ollama
from .real_stack import Stack, local_offset, local_today, real_stack
from .test_core_jobs import RUNS, Reply, Talk, connect, record, timed_chat

pytestmark = pytest.mark.e2e

ASK_WHO = "Who should I email, and what about?"
ELENA = "elena.marchetti@example.test"


def ahead(weekday: int) -> date:
    day = local_today() + timedelta(days=1)
    while day.weekday() != weekday:
        day += timedelta(days=1)
    return day


MONDAY, TUESDAY, THURSDAY = ahead(0), ahead(1), ahead(3)
MONDAY_CALL = {
    "id": "evt_r2",
    "weekday": local_offset((MONDAY - local_today()).days),
    "start": "07:00",
    "end": "07:45",
    "summary": "Call with Elena Marchetti",
    "location": "",
    "description": "",
    "attendees": [ELENA],
}


@pytest.fixture(scope="module")
def trust_stack(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Stack]:
    require_ollama()
    with real_stack(tmp_path_factory.mktemp("homer-r2"), extra_events=(MONDAY_CALL,)) as running:
        yield running


@pytest.fixture
def client(trust_stack: Stack) -> Iterator[httpx.Client]:
    with connect(trust_stack) as http_client:
        yield http_client


@pytest.fixture
def talk(client: httpx.Client, request: pytest.FixtureRequest) -> Talk:
    def send(message: str, conversation: int | None = None) -> Reply:
        body: dict[str, object] = {"message": message}
        if conversation is not None:
            body["conversation_id"] = conversation
        reply = timed_chat(client, body)
        record(request.node.originalname, reply)
        return reply

    return send


def at(day: date, clock: str) -> str:
    return f"{day.isoformat()}T{clock}:00+05:00"


@pytest.mark.parametrize("run", RUNS)
def test_move_it_moves_the_proposed_card(client: httpx.Client, talk: Talk, run: int) -> None:
    booked = talk("schedule a call with Elena Marchetti sometime Monday afternoon, 45 minutes")
    assert booked.actions == ["cal_create"], (booked.tools, booked.said)
    moved = talk("actually move it to Tuesday morning, same length", booked.conversation)
    assert moved.actions == ["cal_create"], (moved.tools, moved.said)
    card = moved.of("approval_required")[0]
    assert card["payload"]["start"].startswith(f"{TUESDAY.isoformat()}T"), card
    assert card["payload"]["start"][11:16] == "09:00", card
    assert card["payload"]["end"][11:16] == "09:45", card
    assert [a["id"] for a in client.get("/api/approvals").json()] == [card["approval_id"]]


@pytest.mark.parametrize("run", RUNS)
def test_move_my_monday_call_with_elena(talk: Talk, run: int) -> None:
    reply = talk("move my Monday call with Elena to Tuesday 9am")
    assert reply.actions == ["cal_update"], (reply.tools, reply.said)
    payload = reply.of("approval_required")[0]["payload"]
    assert payload["event_id"] == "evt_r2", payload
    assert payload["changes"] == {"start": at(TUESDAY, "09:00"), "end": at(TUESDAY, "09:45")}


@pytest.mark.parametrize("run", RUNS)
def test_move_the_call_we_just_booked(client: httpx.Client, talk: Talk, run: int) -> None:
    booked = talk(f"book a call with Elena Marchetti on {THURSDAY:%A} at 11am for an hour")
    assert booked.actions == ["cal_create"], (booked.tools, booked.said)
    card = booked.of("approval_required")[0]["approval_id"]
    assert client.post(f"/api/approvals/{card}/approve").json()["status"] == "done"
    talk("thanks", booked.conversation)
    moved = talk("move the call we just booked to 3pm", booked.conversation)
    assert moved.actions == ["cal_update"], (moved.tools, moved.said)
    changes = moved.of("approval_required")[0]["payload"]["changes"]
    assert changes == {"start": at(THURSDAY, "15:00"), "end": at(THURSDAY, "16:00")}


@pytest.mark.parametrize("run", RUNS)
def test_day_summary_is_grounded(client: httpx.Client, talk: Talk, run: int) -> None:
    draft = talk("email priya.natarajan@example.test that the launch checklist is done")
    card = draft.of("approval_required")[0]
    assert client.post(f"/api/approvals/{card['approval_id']}/approve").json()["status"] == "done"
    reply = talk("what did I get done today and what's still open?")
    said = reply.said
    assert "mail_search" in reply.tools and reply.actions == [], reply.tools
    assert "priya" in said.lower(), said
    assert "no record" not in said.lower() and not leaks(said), said
    assert said.count("Done today") <= 1, said


@pytest.mark.parametrize("run", RUNS)
def test_answers_never_mention_provided_text(talk: Talk, run: int) -> None:
    for message in ["anything urgent in my inbox?", "what did Elena ask me for?"]:
        reply = talk(message)
        assert not leaks(reply.said), reply.said


@pytest.mark.parametrize("run", RUNS)
def test_vague_email_asks_and_context_names_both(talk: Talk, run: int) -> None:
    fresh = talk("email her about it")
    assert fresh.said == ASK_WHO and fresh.actions == [], fresh.said
    booked = talk("schedule a call with Elena Marchetti on Monday at 3pm")
    reply = talk("email her about it", booked.conversation)
    assert reply.actions == ["mail_send"], (reply.tools, reply.said)
    assert re.match(r"Draft to Elena about .+ is ready\.", reply.said), reply.said
    assert reply.of("approval_required")[0]["payload"]["to"] == ELENA


@pytest.mark.parametrize("run", RUNS)
def test_reply_keeps_the_thread_and_speaks_first_person(talk: Talk, run: int) -> None:
    reply = talk("reply to Maya, tell her I can do a call Thursday if she wants")
    assert reply.actions == ["mail_send"], (reply.tools, reply.said)
    payload = reply.of("approval_required")[0]["payload"]
    assert payload["subject"].startswith("Re: "), payload
    message = payload["body"].split("\n\n")[1]
    assert not re.search(r"\b(?:she|her)\b", message, re.IGNORECASE), message
    warmer = talk("make it warmer", reply.conversation)
    body = warmer.of("approval_required")[0]["payload"]["body"].split("\n\n")[1]
    assert abs(len(body.split()) - len(message.split())) <= 0.2 * len(message.split()) + 1, (
        message,
        body,
    )


@pytest.mark.parametrize("run", RUNS)
def test_fire_it_off_sends(trust_stack: Stack, talk: Talk, run: int) -> None:
    draft = talk("email ops@example.test that the vendor call is moved to 5pm")
    sent = trust_stack.sent_count()
    reply = talk("ok fire it off", draft.conversation)
    assert reply.said.endswith("(mail_send): done."), reply.said
    assert trust_stack.sent_count() == sent + 1


@pytest.mark.parametrize("run", RUNS)
def test_no_made_up_addresses_and_known_names(talk: Talk, run: int) -> None:
    reply = talk("email maya at northwind that the kickoff slots are Thursday 4pm")
    if reply.actions:
        assert reply.of("approval_required")[0]["payload"]["to"] == "maya.lindqvist@example.test"
    else:
        assert "address" in reply.said or "Which" in reply.said, reply.said
    typed = talk("email priya.natarajan@example.test that the budget is approved")
    assert typed.of("approval_required")[0]["payload"]["body"].startswith("Hi Priya,"), typed.said


@pytest.mark.parametrize("run", RUNS)
def test_calendar_questions(talk: Talk, run: int) -> None:
    thursday = talk("whats on thursday?")
    assert thursday.tools == ["cal_list"], (thursday.tools, thursday.said)
    assert f"{THURSDAY:%A %d %B}" in thursday.said, thursday.said
    nxt = talk("when's my next meeting?")
    assert nxt.said.startswith("Your next one is") and nxt.said.count("\n") == 0, nxt.said
    free = talk("am i free next tuesday afternoon?")
    assert f"{TUESDAY:%A %d %B}" in free.said and "to" not in free.said.split(",")[0], free.said
    slot = talk(f"find me 45 mins with Maya on {MONDAY:%A} between 2 and 5pm")
    assert slot.actions == ["cal_create"], (slot.tools, slot.said)
    event = slot.of("approval_required")[0]["payload"]
    assert event["start"].startswith(MONDAY.isoformat()) and event["start"][11:16] >= "14:00"
    assert event["end"][11:16] <= "17:00", event
