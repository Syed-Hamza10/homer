"""QA round 6 phrasings on the real stack with the live model, three runs each: calendar
questions that went to memory, week and time math, a plain move, draft edits and questions,
context in drafts, relative times, Homer fixing its own mistake, and web answers."""

import re
from collections.abc import Iterator
from datetime import date, datetime, timedelta

import httpx
import pytest

from homer_core.agent.dates import from_now, this_week

from .conftest import require_ollama
from .real_stack import ZONE, Stack, local_offset, local_today, real_stack
from .test_answers import DUCKDUCKGO
from .test_core_jobs import RUNS, Reply, Talk, connect, next_weekday, record, timed_chat

pytestmark = pytest.mark.e2e

HAMZA = {"id": "c9", "given": "Syed Hamza", "family": "Shah", "email": "hamza.shah@example.test"}
OWNER = "BSDSF21A019-Syed Jordan"
WORKSHOP = "Workshop prep for Meridian Roast"
DISCUSS = "need to discuss this with hamza. send him a mail asking when hes free"
RULE_WORDS = re.compile(r"\bunless\b|\bevery point\b|\bfirst person\b|\bplaceholder", re.I)


def offset(day: date) -> int:
    return local_offset((day - local_today()).days)


def sam_day() -> date | None:
    first, last = this_week(local_today())
    ahead = [first + timedelta(days=n) for n in range((last - first).days + 1)]
    ahead = [day for day in ahead if day > local_today() + timedelta(days=1)]
    return ahead[len(ahead) // 2] if ahead else None


def utc_event(event_id: str, title: str, day: date, start: str, end: str) -> dict[str, object]:
    """A simulator event at local times (Asia/Karachi is UTC+5)."""

    def utc(clock: str) -> str:
        hour, minute = map(int, clock.split(":"))
        return f"{hour - 5:02d}:{minute:02d}"

    return {
        "id": event_id,
        "weekday": offset(day),
        "start": utc(start),
        "end": utc(end),
        "summary": title,
        "location": "",
        "description": "",
        "attendees": [],
    }


def round_six_events() -> tuple[dict[str, object], ...]:
    tomorrow = local_today() + timedelta(days=1)
    events = [
        utc_event("evt_r6_workshop", WORKSHOP, tomorrow, "09:30", "10:30"),
        utc_event("evt_r6_portfolio", "Portfolio review", next_weekday(0), "14:00", "15:00"),
    ]
    lunch = sam_day()
    if lunch is not None:
        events.append(utc_event("evt_r6_sam", "Lunch with Sam", lunch, "12:30", "13:30"))
    return tuple(events)


@pytest.fixture(scope="module")
def round_stack(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Stack]:
    require_ollama()
    home = tmp_path_factory.mktemp("homer-round6")
    with real_stack(home, True, round_six_events(), contacts=(HAMZA,), owner_name=OWNER) as running:
        yield running


@pytest.fixture
def client(round_stack: Stack) -> Iterator[httpx.Client]:
    with connect(round_stack) as http_client:
        settings = http_client.get("/api/settings").json()
        http_client.put("/api/settings", json={**settings, "name": ""})
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
def test_next_meeting_reads_the_calendar(talk: Talk, run: int) -> None:
    reply = talk("when is my next meeting, please?")
    assert reply.said.startswith("Your next one is"), reply.said
    assert "nothing saved" not in reply.said.lower()


@pytest.mark.parametrize("run", RUNS)
def test_what_needs_me_today_reads_the_mail(talk: Talk, run: int) -> None:
    reply = talk("any unread mail? and which of it actually needs me today?")
    assert "nothing saved" not in reply.said.lower(), reply.said
    assert reply.tools.count("mail_search") >= 2, reply.tools


@pytest.mark.parametrize("run", RUNS)
def test_sam_this_week_lists_the_coming_days(talk: Talk, run: int) -> None:
    if sam_day() is None:
        pytest.skip("no day left this week")
    reply = talk("anything with Sam this week? check the calendar, dont guess")
    first, _ = this_week(local_today())
    assert reply.of("tool_call")[0]["args"]["start"].startswith(first.isoformat()), reply.tools
    assert "Lunch with Sam" in reply.said, reply.said


@pytest.mark.parametrize("run", RUNS)
def test_free_monday_at_2pm_answers_for_that_slot(talk: Talk, run: int) -> None:
    monday = next_weekday(0)
    reply = talk(f"am i free monday {monday.day} {monday:%b}".lower() + " at 2pm?")
    assert reply.said.startswith("No, you are busy at 14:00"), reply.said
    assert "Portfolio review" in reply.said and "16:00" not in reply.said, reply.said


@pytest.mark.parametrize("run", RUNS)
def test_move_tomorrow_to_11_keeps_the_day_and_length(talk: Talk, run: int) -> None:
    reply = talk("move workshop prep tomorrow to 11")
    day = (local_today() + timedelta(days=1)).isoformat()
    assert card(reply)["changes"] == {
        "start": f"{day}T11:00:00+05:00",
        "end": f"{day}T12:00:00+05:00",
    }, reply.said


def drafted_to_elena(talk: Talk) -> Reply:
    reply = talk(
        "email elena.marchetti@example.test: the figures look right and I will review the "
        "deck tonight, and I can send notes by friday"
    )
    assert reply.actions == ["mail_send"], (reply.tools, reply.said)
    return reply


@pytest.mark.parametrize("run", RUNS)
def test_make_it_shorter_is_shorter_and_has_no_rule_text(talk: Talk, run: int) -> None:
    first = drafted_to_elena(talk)
    before = message_of(str(card(first)["body"]))
    edited = talk("make it shorter and a bit warmer", first.conversation)
    after = message_of(str(card(edited)["body"]))
    assert not RULE_WORDS.search(after), after
    assert len(after.split()) < len(before.split()), (before, after)


@pytest.mark.parametrize("run", RUNS)
def test_who_is_that_going_to_names_the_recipient(talk: Talk, run: int) -> None:
    first = drafted_to_elena(talk)
    reply = talk("who is that going to, and does it mention the deck?", first.conversation)
    assert "elena" in reply.said.lower(), reply.said
    assert not re.match(r"^\s*(?:no|yes)\b", reply.said, re.I), reply.said
    assert len(reply.said.split()) >= 4


@pytest.mark.parametrize("run", RUNS)
def test_in_one_hour_is_now_plus_an_hour(talk: Talk, run: int) -> None:
    before = from_now(datetime.now(ZONE), 60)
    reply = talk("set a meet with Priya for 1 hour from now")
    after = from_now(datetime.now(ZONE), 60)
    start = datetime.fromisoformat(str(card(reply)["start"]))
    assert before <= start <= after, (start, reply.said)


@pytest.mark.parametrize("run", RUNS)
def test_why_that_time_fixes_the_card(talk: Talk, run: int) -> None:
    first = talk("book a call with Priya tomorrow at 3pm")
    assert first.actions == ["cal_create"], (first.tools, first.said)
    fixed = talk("why 15:00? I said 4pm", first.conversation)
    day = (local_today() + timedelta(days=1)).isoformat()
    assert str(card(fixed)["start"]).startswith(f"{day}T16:00"), fixed.said
    assert "edit or delete" not in fixed.said.lower()


@pytest.mark.parametrize("run", RUNS)
def test_discuss_this_after_an_email_names_it_and_greets_by_the_users_word(
    talk: Talk, run: int
) -> None:
    first = talk("what did Elena ask in her last email?")
    reply = talk(DISCUSS, first.conversation)
    body = str(card(reply)["body"])
    assert body.startswith("Hi Hamza,"), body
    assert body.endswith("Best,\nJordan"), body
    assert re.search(r"deck|quarterly|review", body, re.I), body
    assert not re.search(r"this matter|the topic", body, re.I), body


@pytest.mark.parametrize("run", RUNS)
def test_islamabad_weather_is_answered(web: None, talk: Talk, run: int) -> None:
    reply = talk("what is the weather in islamabad now")
    body = reply.said.split("**Sources**")[0]
    assert not re.search(r"\bvisit\b|website", body, re.I), reply.said
    assert re.search(r"°|degrees|\d+\s*C\b", body), reply.said


@pytest.mark.parametrize("run", RUNS)
def test_dollar_to_rupee_is_pkr(web: None, talk: Talk, run: int) -> None:
    reply = talk("what's the dollar to rupee rate today")
    body = reply.said.split("**Sources**")[0]
    assert re.search(r"PKR|Pakistani", body), reply.said
    assert "INR" not in body, reply.said


@pytest.mark.parametrize("run", RUNS)
def test_discuss_this_after_a_web_answer_names_it(web: None, talk: Talk, run: int) -> None:
    first = talk("who won the cricket match yesterday?")
    reply = talk(DISCUSS, first.conversation)
    body = str(card(reply)["body"])
    names = set(re.findall(r"\b[A-Z][a-z]{3,}\b", first.said.split("**Sources**")[0]))
    assert re.search(r"cricket|match", body, re.I) or any(n in body for n in names), body
    assert not re.search(r"this matter|the topic", body, re.I), body
