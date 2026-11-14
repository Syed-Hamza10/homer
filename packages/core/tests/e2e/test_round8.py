"""QA round 8 phrasings on the real stack with the live model, three runs each: knowledge
questions while the search engine is blocking this machine, event cards in the user's zone,
a choice card for an ambiguous invitee, and drafts that state no fact nobody gave."""

from collections.abc import Iterator
from datetime import date, timedelta

import httpx
import pytest

from homer_core.services.jobs.send_email import invented

from .conftest import require_ollama
from .real_stack import Stack, local_offset, local_today, real_stack
from .test_core_jobs import RUNS, Reply, Talk, connect, next_weekday, record, timed_chat
from .test_round7 import card, deliver, message_of

pytestmark = pytest.mark.e2e

LIMITED = "limiting searches"
ROSA = "Rosa Lindgren <rosa.lindgren@meridian-roast.example.test>"
ROSA_BODY = (
    "Hi Jordan,\n\nThanks for the proposal, we like the direction. Could you send a revised "
    "version that splits phase 1 into two parts?\n\nRosa"
)


def memo_day() -> date:
    """A Thursday at least a week ahead, clear of the seeded week."""
    return next_weekday(3) + timedelta(days=7)


MEMO_DAY = memo_day()
CLIENT_CALL = {
    "id": "evt_r8_busy",
    "start": "08:00",
    "end": "10:00",
    "summary": "Client call",
    "location": "",
    "description": "",
    "attendees": [],
}


@pytest.fixture(scope="module")
def round_stack(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Stack]:
    require_ollama()
    busy = {**CLIENT_CALL, "weekday": local_offset((MEMO_DAY - local_today()).days)}
    home = tmp_path_factory.mktemp("homer-round8")
    with real_stack(home, True, (busy,), search_error="search_blocked") as running:
        deliver(running, ROSA, "Brand refresh proposal", ROSA_BODY)
        yield running


@pytest.fixture
def client(round_stack: Stack) -> Iterator[httpx.Client]:
    with connect(round_stack) as http_client:
        yield http_client


@pytest.fixture
def post(client: httpx.Client, request: pytest.FixtureRequest) -> Talk:
    def send(message: str, conversation: int | None = None, **extra: object) -> Reply:
        body: dict[str, object] = {"message": message, **extra}
        if conversation is not None:
            body["conversation_id"] = conversation
        reply = timed_chat(client, body)
        reply.finished()
        record(f"r8:{request.node.originalname}", reply)
        return reply

    return send


@pytest.mark.parametrize("run", RUNS)
def test_a_knowledge_question_is_answered_while_search_is_blocked(post: Talk, run: int) -> None:
    reply = post("what is the tallest mountain in africa, dear?")
    assert "kilimanjaro" in reply.said.lower(), (reply.tools, reply.said)
    assert LIMITED not in reply.said, reply.said


@pytest.mark.parametrize("run", RUNS)
def test_an_asked_search_that_is_blocked_falls_back_with_a_caveat(post: Talk, run: int) -> None:
    reply = post("who wrote pride and prejudice? search it online please")
    assert reply.tools == ["web_search"], (reply.tools, reply.said)
    assert reply.said.startswith("I couldn't check the web just now"), reply.said
    assert "austen" in reply.said.lower(), reply.said


@pytest.mark.parametrize("run", RUNS)
def test_live_weather_still_says_it_cannot_look(post: Talk, run: int) -> None:
    reply = post("what is the weather in multan today")
    assert LIMITED in reply.said, (reply.tools, reply.said)
    assert "from what I know" not in reply.said, reply.said


@pytest.mark.parametrize("run", RUNS)
def test_a_window_booking_shows_local_time_everywhere(post: Talk, run: int) -> None:
    day = f"{MEMO_DAY.day} {MEMO_DAY:%b}".lower()
    first = post(
        f"block 2 hours for drafting the Orion memo on thursday {day}, any time between 1pm and 5pm"
    )
    proposed = first.of("approval_required")[-1]
    assert card(first)["start"] == f"{MEMO_DAY.isoformat()}T15:00:00+05:00", proposed
    assert "15:00-17:00 (PKT)" in proposed["preview"], proposed["preview"]
    assert "15:00-17:00 PKT" in first.said and "UTC" not in first.said, first.said
    why = post("why that time?", first.conversation)
    assert why.actions == [] and "15:00-17:00 PKT" in why.said, (why.said, why.actions)


@pytest.mark.parametrize("run", RUNS)
def test_an_ambiguous_invitee_gets_a_choice_card_then_the_invite(post: Talk, run: int) -> None:
    first = post("set up a call with Sara tomorrow 3pm")
    assert first.actions == [], (first.said, first.actions)
    [question] = first.of("choice")
    labels = [option["label"] for option in question["options"]]
    assert {"Sara Whitfield", "Sara Mbeki"} <= set(labels), labels
    picked = next(option for option in question["options"] if option["label"] == "Sara Mbeki")
    choice = {"question_id": question["question_id"], "option_id": picked["id"]}
    reply = post(picked["label"], first.conversation, choice=choice)
    assert reply.actions == ["cal_create"], (reply.tools, reply.said)
    tomorrow = (local_today() + timedelta(days=1)).isoformat()
    assert card(reply)["attendees"] == ["sara.mbeki@example.test"], card(reply)
    assert card(reply)["start"] == f"{tomorrow}T15:00:00+05:00", card(reply)


@pytest.mark.parametrize("run", RUNS)
def test_a_reply_states_no_date_or_event_nobody_gave(post: Talk, run: int) -> None:
    message = "reply to Rosa's latest email: tell her the revised proposal goes out on wednesday"
    reply = post(message)
    body = message_of(str(card(reply)["body"]))
    assert invented(body, f"{message} {ROSA_BODY}") == [], body
    assert "wednesday" in body.lower(), body
