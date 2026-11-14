"""One intent call decides every message: memory corrections, questions about a waiting draft,
follow-ups, sums, goodbyes and vague requests on the real stack, three runs each."""

import re
from collections.abc import Iterator
from datetime import timedelta

import httpx
import pytest

from .conftest import require_ollama
from .real_stack import Stack, local_today, real_stack
from .test_core_jobs import RUNS, Reply, Talk, connect, next_weekday, record, timed_chat

pytestmark = pytest.mark.e2e

NADIA = "nadia.karimi@example.test"
AGENDA = "https://example.test/agenda-7"
ROSA = "rosa.berg@example.test"
ASKS_WHO = re.compile(r"\bwho\b|\bname\b|\baddress\b", re.IGNORECASE)


@pytest.fixture(scope="module")
def router_stack(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Stack]:
    require_ollama()
    with real_stack(tmp_path_factory.mktemp("homer-intents")) as running:
        yield running


@pytest.fixture
def client(router_stack: Stack) -> Iterator[httpx.Client]:
    with connect(router_stack) as http_client:
        yield http_client


@pytest.fixture
def talk(client: httpx.Client, request: pytest.FixtureRequest) -> Talk:
    def send(message: str, conversation: int | None = None) -> Reply:
        body: dict[str, object] = {"message": message}
        if conversation is not None:
            body["conversation_id"] = conversation
        reply = timed_chat(client, body)
        reply.finished()
        record(request.node.originalname, reply)
        return reply

    return send


def facts_about(client: httpx.Client, name: str) -> list[str]:
    texts = [fact["text"] for fact in client.get("/api/facts").json()]
    return [text for text in texts if name.lower() in text.lower()]


def forget_all(client: httpx.Client) -> None:
    for fact in client.get("/api/facts").json():
        client.delete(f"/api/facts/{fact['id']}")


@pytest.mark.parametrize("run", RUNS)
def test_a_correction_replaces_the_fact_and_recall_answers(
    client: httpx.Client, talk: Talk, run: int
) -> None:
    forget_all(client)
    saved = talk("note: Omar Haddad, my landlord, only takes calls after 4pm")
    chat = saved.conversation
    fixed = talk("actually he prefers mornings, before 11", chat)
    omar = facts_about(client, "omar")
    assert len(omar) == 1 and "morning" in omar[0].lower(), (fixed.said, omar)
    assert "4pm" not in omar[0], omar
    asked = talk("so when can omar take calls?", chat)
    assert re.search(r"morning|11", asked.said, re.I), asked.said
    assert "4pm" not in asked.said and "web_search" not in asked.tools, asked.said


@pytest.mark.parametrize("run", RUNS)
def test_forget_removes_every_fact_about_the_person(
    client: httpx.Client, talk: Talk, run: int
) -> None:
    forget_all(client)
    chat = talk("remember that Omar's flight lands on Friday at 6pm").conversation
    talk("also remember Omar is allergic to peanuts", chat)
    assert len(facts_about(client, "omar")) == 2
    gone = talk("forget everything about omar", chat)
    assert facts_about(client, "omar") == [], gone.said
    asked = talk("what do you know about omar now?", chat)
    assert "nothing saved" in asked.said.lower(), asked.said


def drafted(talk: Talk) -> Reply:
    reply = talk(f"email {NADIA}: the agenda is at {AGENDA}, ask her to review it before monday")
    assert reply.actions == ["mail_send"], (reply.tools, reply.said)
    return reply


@pytest.mark.parametrize("run", RUNS)
def test_where_is_the_link_reads_the_waiting_draft(talk: Talk, run: int) -> None:
    first = drafted(talk)
    reply = talk("wheres the link", first.conversation)
    assert AGENDA in reply.said, reply.said
    assert "nothing saved" not in reply.said.lower(), reply.said


@pytest.mark.parametrize("run", RUNS)
def test_never_mind_cancel_it_discards_the_draft(router_stack: Stack, talk: Talk, run: int) -> None:
    first = drafted(talk)
    approval_id = first.of("approval_required")[0]["approval_id"]
    sent = router_stack.sent_count()
    reply = talk("ok never mind, cancel it", first.conversation)
    assert reply.said == f"Approval #{approval_id} (mail_send): rejected.", reply.said
    assert "cal_list" not in reply.tools and router_stack.sent_count() == sent


@pytest.mark.parametrize("run", RUNS)
def test_a_status_question_in_another_chat_tells_the_truth(talk: Talk, run: int) -> None:
    first = talk(f"email {ROSA}: the revised proposal goes to her by tuesday")
    assert first.actions == ["mail_send"], (first.tools, first.said)
    reply = talk("has the Rosa reply gone out, are you sure?")
    assert reply.said.startswith("Not yet. The draft to " + ROSA), reply.said


@pytest.mark.parametrize("run", RUNS)
def test_and_the_day_after_follows_the_previous_date(talk: Talk, run: int) -> None:
    first = talk("what's on my calendar tomorrow?")
    after = talk("and the day after?", first.conversation)
    day = (local_today() + timedelta(days=2)).isoformat()
    calls = after.of("tool_call")
    assert calls and calls[0]["args"]["start"].startswith(day), (calls, after.said)


@pytest.mark.parametrize("run", RUNS)
def test_actually_i_meant_friday_moves_the_proposed_event(talk: Talk, run: int) -> None:
    thursday, friday = next_weekday(3), next_weekday(4)
    first = talk("book a 30 minute call with Elena Marchetti on Thursday at 3pm")
    assert first.actions == ["cal_create"], (first.tools, first.said)
    assert first.of("approval_required")[0]["payload"]["start"].startswith(thursday.isoformat())
    fixed = talk("actually I meant Friday", first.conversation)
    cards = fixed.of("approval_required")
    assert [card["action"] for card in cards] == ["cal_create"], (fixed.tools, fixed.said)
    start = cards[0]["payload"]["start"]
    assert start.startswith(f"{friday.isoformat()}T15:00"), start


@pytest.mark.parametrize("run", RUNS)
def test_a_percentage_is_computed(talk: Talk, run: int) -> None:
    reply = talk("15% of 240")
    assert reply.said == "15% of 240 = 36" and reply.tools == [], reply.said


@pytest.mark.parametrize("run", RUNS)
def test_ok_bye_is_just_chat(talk: Talk, run: int) -> None:
    reply = talk("ok bye")
    assert reply.said.strip() and reply.tools == [] and reply.actions == [], reply.said


@pytest.mark.parametrize("run", RUNS)
def test_a_vague_email_request_asks_first(router_stack: Stack, talk: Talk, run: int) -> None:
    drafts = router_stack.counts()["drafts"]
    reply = talk("email her about it")
    assert reply.actions == [] and ASKS_WHO.search(reply.said), (reply.tools, reply.said)
    assert router_stack.counts()["drafts"] == drafts
