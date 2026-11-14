"""QA round 7 phrasings on the real stack with the live model, three runs each: terse
follow-ups that went to the wrong job, Homer explaining a right booking instead of redoing it,
a reminder on the calendar, short drafts with no padding, and the email and weather times."""

import base64
import re
from collections.abc import Iterator
from datetime import datetime, timedelta
from email.message import EmailMessage

import httpx
import pytest

from homer_core.agent.dates import from_now
from homer_core.agent.voice import SENTENCE
from homer_core.services.jobs.send_email import copied, padded
from homer_sim.state import KNOWN_TOKEN

from .conftest import require_ollama
from .real_stack import ZONE, Stack, real_stack
from .test_answers import DUCKDUCKGO
from .test_core_jobs import RUNS, Reply, Talk, connect, next_weekday, record, timed_chat

pytestmark = pytest.mark.e2e

OWEN = "Owen Hartley <owen.hartley@example.test>"
PHARMACIST = "please keep in mind my pharmacist is Mr Idris Chaudhry and he shuts at 7pm"
WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def deliver(stack: Stack, sender: str, subject: str, body: str) -> None:
    message = EmailMessage()
    message["From"] = sender
    message["To"] = "jordan.reyes@example.test"
    message["Subject"] = subject
    message.set_content(body)
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    response = httpx.post(
        f"{stack.sim_url}/gmail/v1/users/me/messages",
        json={"raw": raw, "labelIds": ["INBOX", "UNREAD"]},
        headers={"Authorization": f"Bearer {KNOWN_TOKEN}"},
    )
    response.raise_for_status()


@pytest.fixture(scope="module")
def round_stack(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Stack]:
    require_ollama()
    with real_stack(tmp_path_factory.mktemp("homer-round7"), True) as running:
        deliver(
            running,
            OWEN,
            "Budget call next week",
            "Hi Jordan,\n\nCould we have a 45-minute call next week to go through the Q1 "
            "budget? Tuesday or Wednesday afternoon suits me.\n\nThanks,\nOwen",
        )
        yield running


@pytest.fixture
def client(round_stack: Stack) -> Iterator[httpx.Client]:
    with connect(round_stack) as http_client:
        yield http_client


@pytest.fixture
def talk(client: httpx.Client, request: pytest.FixtureRequest) -> Talk:
    def send(message: str, conversation: int | None = None) -> Reply:
        body: dict[str, object] = {"message": message}
        if conversation is not None:
            body["conversation_id"] = conversation
        reply = timed_chat(client, body)
        reply.finished()
        record(f"r7:{request.node.originalname}", reply)
        return reply

    return send


@pytest.fixture(scope="module")
def web() -> None:
    try:
        httpx.get(DUCKDUCKGO, timeout=5.0).raise_for_status()
    except httpx.HTTPError as error:
        pytest.skip(f"DuckDuckGo not reachable: {error}")


def card(reply: Reply) -> dict[str, object]:
    cards = reply.of("approval_required")
    assert cards, (reply.tools, reply.said)
    return cards[-1]["payload"]


def message_of(body: str) -> str:
    return "\n\n".join(body.split("\n\n")[1:-1])


@pytest.mark.parametrize("run", RUNS)
def test_pharmacist_closing_time_one_line_after_a_web_answer(
    web: None, talk: Talk, run: int
) -> None:
    first = talk(PHARMACIST)
    talk("who is the prime minister of japan now", first.conversation)
    reply = talk("pharmacist closing time, one line", first.conversation)
    assert "sent" not in reply.said.lower(), reply.said
    assert re.search(r"\b7\s*(?:pm|p\.m\.)|19:00", reply.said, re.I), reply.said


@pytest.mark.parametrize("run", RUNS)
def test_are_you_sure_that_went_out_after_a_real_send(
    round_stack: Stack, talk: Talk, run: int
) -> None:
    sent = round_stack.sent_count()
    first = talk("send message to ops@example.test: the backup finished and all is okay")
    body = message_of(str(card(first)["body"]))
    assert not padded(body, "the backup finished and all is okay"), body
    done = talk("send it", first.conversation)
    assert done.said.endswith("done."), done.said
    assert round_stack.sent_count() == sent + 1
    sure = talk("are you sure that went out? dont just say yes", first.conversation)
    assert sure.said.startswith("Yes"), sure.said


@pytest.mark.parametrize("run", RUNS)
def test_what_does_owen_want_reads_his_mail(talk: Talk, run: int) -> None:
    reply = talk("what does Owen want from me, dear?")
    assert "nothing saved" not in reply.said.lower(), reply.said
    assert "mail_search" in reply.tools, reply.tools
    assert re.search(r"call|budget", reply.said, re.I), reply.said


@pytest.mark.parametrize("run", RUNS)
def test_no_wait_i_mean_wednesday_reads_wednesday(talk: Talk, run: int) -> None:
    first = talk("oh and what is on tuesday, dear?")
    reply = talk("no wait, i mean wednesday", first.conversation)
    wednesday = next_weekday(2).isoformat()
    assert reply.tools == ["cal_list"], (reply.tools, reply.said)
    assert reply.of("tool_call")[0]["args"]["start"].startswith(wednesday), reply.of("tool_call")
    assert "saved" not in reply.said.lower(), reply.said


@pytest.mark.parametrize("run", RUNS)
def test_why_that_time_on_a_right_event_explains(talk: Talk, run: int) -> None:
    thursday = next_weekday(3)
    first = talk(f"dinner with Faisal on thursday {thursday.day} {thursday:%b} at 7".lower())
    assert str(card(first)["start"]).startswith(f"{thursday.isoformat()}T19:00"), first.said
    why = talk("why that time?", first.conversation)
    assert why.actions == [], (why.said, why.actions)
    assert "19:00" in why.said and "wrong" not in why.said.lower(), why.said


@pytest.mark.parametrize("run", RUNS)
def test_a_reminder_on_my_calendar_is_an_event(talk: Talk, run: int) -> None:
    before = from_now(datetime.now(ZONE), 30)
    reply = talk("put a reminder on my calendar in 30 minutes, call it Tea with the neighbour")
    after = from_now(datetime.now(ZONE), 30)
    assert reply.actions == ["cal_create"], (reply.tools, reply.said)
    start = datetime.fromisoformat(str(card(reply)["start"]))
    assert before - timedelta(minutes=5) <= start <= after, start
    assert "tea" in str(card(reply)["title"]).lower(), card(reply)


@pytest.mark.parametrize("run", RUNS)
def test_discuss_this_after_a_web_answer_is_one_short_mention(
    web: None, talk: Talk, run: int
) -> None:
    first = talk("any news today on the pakistan cricket team?")
    details = " ".join(SENTENCE.split(first.said.split("**Sources**")[0].strip())[1:])
    reply = talk("email Tomas to discuss this", first.conversation)
    body = message_of(str(card(reply)["body"]))
    assert not copied(body, details), (body, details)
    assert len(body.split()) <= 70, body
    assert re.search(r"cricket|pakistan|match|cup", f"{card(reply)['subject']} {body}", re.I)


@pytest.mark.parametrize("run", RUNS)
def test_email_card_time(talk: Talk, run: int) -> None:
    reply = talk("email Tomas and say the contract draft will reach him by thursday")
    assert reply.actions == ["mail_send"], (reply.tools, reply.said)
    assert reply.approval_seconds is not None


@pytest.mark.parametrize("run", RUNS)
def test_weather_time(web: None, talk: Talk, run: int) -> None:
    reply = talk("is it raining in islamabad at the moment?")
    body = reply.said.split("**Sources**")[0]
    assert re.search(r"°|degrees|rain|dry|clear|cloud|sunny", body, re.I), reply.said


@pytest.mark.parametrize("run", RUNS)
def test_a_goodbye_names_no_other_day(talk: Talk, run: int) -> None:
    reply = talk("ok thanks, that is everything for now")
    today = f"{datetime.now(ZONE):%A}".lower()
    named = [day for day in WEEKDAYS if day in reply.said.lower() and day != today]
    assert named == [], reply.said
