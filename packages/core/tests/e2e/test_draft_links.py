"""Questions about a waiting draft, event links and repeated requests on the real stack, three
runs each, from a live user's transcript."""

import re
from collections.abc import Iterator

import httpx
import pytest

from .conftest import require_ollama
from .real_stack import Stack, real_stack
from .test_core_jobs import RUNS, Reply, Talk, connect, record, timed_chat

pytestmark = pytest.mark.e2e

SAMUEL = "samuel.okafor@example.test"
BOOK_AND_EMAIL = (
    "book an event with samuel about Homer demo and LinkedIn post for this Saturday, 3pm. "
    "Then send him a brief American-style email that I put this in our calendar"
)
CREATE_FIRST = "The event gets its Google Calendar link once you press Create."
DANGLING = re.compile(r"(?:link|here|below)\s*:\s*(?:[.,;!?]|$)|\[\s*\]|\(\s*\)", re.I | re.M)


@pytest.fixture(scope="module")
def links_stack(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Stack]:
    require_ollama()
    with real_stack(tmp_path_factory.mktemp("homer-links")) as running:
        yield running


@pytest.fixture
def client(links_stack: Stack) -> Iterator[httpx.Client]:
    with connect(links_stack) as http_client:
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


def cards(reply: Reply) -> dict[str, dict[str, object]]:
    return {card["action"]: card for card in reply.of("approval_required")}


def booked(talk: Talk) -> Reply:
    reply = talk(BOOK_AND_EMAIL)
    made = cards(reply)
    assert set(made) == {"cal_create", "mail_send"}, (reply.tools, reply.said)
    assert made["mail_send"]["payload"]["to"] == SAMUEL, made
    return reply


def body_of(reply: Reply) -> str:
    return str(cards(reply)["mail_send"]["payload"]["body"])


@pytest.mark.parametrize("run", RUNS)
def test_questions_about_the_draft_are_answered_from_it(talk: Talk, run: int) -> None:
    first = booked(talk)
    chat = first.conversation
    where = talk("where's the link in this draft?", chat)
    assert where.said.startswith("No, the link isn't in it yet."), where.said
    assert CREATE_FIRST in where.said and where.actions == [], where.said
    yes_no = talk("are you adding the link of the event in the email yes or no?", chat)
    assert yes_no.said.startswith("No"), yes_no.said
    assert "waiting for you to press Send" not in yes_no.said, yes_no.said
    status = talk("did you send it?", chat)
    assert status.said.startswith("Not yet."), status.said


@pytest.mark.parametrize("run", RUNS)
def test_an_event_link_is_honest_then_real(client: httpx.Client, talk: Talk, run: int) -> None:
    first = booked(talk)
    chat = first.conversation
    assert not DANGLING.search(body_of(first)), body_of(first)
    pending = talk("add the link of the event in that email as well", chat)
    assert pending.said.startswith(CREATE_FIRST), pending.said
    body = body_of(pending)
    assert re.search(r"When: Saturday \d{1,2} \w{3}, 3:00–3:30 pm", body), body
    assert "http" not in body and not DANGLING.search(body), body
    event = cards(first)["cal_create"]["approval_id"]
    assert client.post(f"/api/approvals/{event}/approve").json()["status"] == "done"
    linked = talk("add the link of the event in that email as well", chat)
    body = body_of(linked)
    assert re.search(r"Calendar link: https://\S+", body), body
    assert body.count("Calendar link:") == 1, body


@pytest.mark.parametrize("run", RUNS)
def test_the_same_request_twice_gives_one_draft(client: httpx.Client, talk: Talk, run: int) -> None:
    first = booked(talk)
    again = talk(BOOK_AND_EMAIL, first.conversation)
    assert again.said == "I already drafted that one — it's above.", again.said
    assert again.actions == [], again.actions
