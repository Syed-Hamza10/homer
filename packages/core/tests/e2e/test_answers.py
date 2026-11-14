"""Search, calculator, memory and mail-reading answers on the real stack, three runs each."""

import base64
import json
import re
import tempfile
from collections.abc import Iterator
from email.message import EmailMessage
from pathlib import Path

import httpx
import pytest

from homer_sim.state import KNOWN_TOKEN

from .conftest import require_ollama
from .real_stack import Stack, real_stack
from .test_core_jobs import DUCKDUCKGO, Reply, connect, timed_chat

pytestmark = pytest.mark.e2e

RUNS = range(3)
TIMINGS = Path(tempfile.gettempdir()) / "homer-e2e-answers.jsonl"
NON_ANSWER = re.compile(
    r"\bprovided\b|\bthe (?:text|pages?|snippets?)\b|does not (?:contain|say|mention)"
    r"|doesn't (?:contain|say|mention)|impossible to determine|no information",
    re.IGNORECASE,
)
SEARCHES = [
    "who won the Lakers game last night",
    "what's the latest on the Fed rate decision",
    "any news on OpenAI this week",
    "price of gold today",
    "is it going to rain in London tomorrow",
]
NO_SEARCH = ["what's the capital of Australia", "explain REST in two sentences", "no", "thanks"]
NEWSLETTER = "Ten rebrands that worked this quarter"


def timed(
    client: httpx.Client, scenario: str, message: str, conversation: int | None = None
) -> Reply:
    body: dict[str, object] = {"message": message}
    if conversation is not None:
        body["conversation_id"] = conversation
    reply = timed_chat(client, body)
    with TIMINGS.open("a") as handle:
        row = {"scenario": scenario, "message": message, "seconds": round(reply.seconds, 1)}
        handle.write(json.dumps({**row, "said": reply.said[:300]}) + "\n")
    return reply


def insert_newsletter(stack: Stack) -> None:
    message = EmailMessage()
    message["From"] = "The Brand Letter <newsletter@brandletter.example.test>"
    message["To"] = "jordan.reyes@example.test"
    message["Subject"] = NEWSLETTER
    message["List-Unsubscribe"] = "<mailto:unsubscribe@brandletter.example.test>"
    message.set_content("This week: ten rebrands. You receive this because you subscribed.")
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    response = httpx.post(
        f"{stack.sim_url}/gmail/v1/users/me/messages",
        json={"raw": raw, "labelIds": ["INBOX", "UNREAD"]},
        headers={"Authorization": f"Bearer {KNOWN_TOKEN}"},
    )
    response.raise_for_status()


@pytest.fixture(scope="module")
def answers_stack(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Stack]:
    require_ollama()
    with real_stack(tmp_path_factory.mktemp("homer-answers-home"), web_search=True) as running:
        insert_newsletter(running)
        yield running


@pytest.fixture
def client(answers_stack: Stack) -> Iterator[httpx.Client]:
    with connect(answers_stack) as http_client:
        yield http_client


@pytest.fixture(scope="module")
def web() -> None:
    try:
        httpx.get(DUCKDUCKGO, timeout=5.0).raise_for_status()
    except httpx.HTTPError as error:
        pytest.skip(f"DuckDuckGo not reachable: {error}")


def answered(reply: Reply) -> str:
    reply.finished()
    body = reply.said.split("**Sources**")[0]
    assert not NON_ANSWER.search(body), reply.said
    return body


@pytest.mark.parametrize("run", RUNS)
@pytest.mark.parametrize("question", SEARCHES)
def test_search_answers_with_sources(
    web: None, client: httpx.Client, question: str, run: int
) -> None:
    reply = timed(client, "search", question)
    body = answered(reply)
    assert reply.tools[0] == "web_search", (reply.tools, reply.said)
    assert "**Sources**" in reply.said and "](http" in reply.said, reply.said
    assert body.strip() and reply.seconds < 30, (reply.seconds, reply.said)


@pytest.mark.parametrize("run", RUNS)
@pytest.mark.parametrize("message", NO_SEARCH)
def test_no_search_when_not_needed(web: None, client: httpx.Client, message: str, run: int) -> None:
    reply = timed(client, "no_search", message)
    answered(reply)
    assert "web_search" not in reply.tools, (reply.tools, reply.said)
    if "Australia" in message:
        assert "Canberra" in reply.said, reply.said


@pytest.mark.parametrize("run", RUNS)
def test_arithmetic_is_computed(client: httpx.Client, run: int) -> None:
    reply = timed(client, "calculator", "what is 17 times 23")
    assert reply.said == "17 times 23 = 391" and reply.tools == [], reply.said
    assert reply.seconds < 3, reply.seconds


@pytest.mark.parametrize("run", RUNS)
def test_currency_uses_a_searched_rate(web: None, client: httpx.Client, run: int) -> None:
    reply = timed(client, "currency", "how many euros is 3,400 US dollars")
    reply.finished()
    assert reply.tools[0] == "web_search", reply.tools
    assert re.search(r"3,400 USD is about [\d,.]+ EUR, at 1 USD = [\d.]+ EUR", reply.said), (
        reply.said
    )


def fact_texts(client: httpx.Client) -> list[str]:
    return [fact["text"] for fact in client.get("/api/facts").json()]


@pytest.mark.parametrize("run", RUNS)
def test_remember_recall_and_forget(client: httpx.Client, run: int) -> None:
    saved = timed(client, "memory", "Remember that Dana prefers calls after 3pm")
    assert "Dana prefers calls after 3pm" in saved.said, saved.said
    conversation = saved.conversation
    hint = timed(
        client, "memory", "also remember that my wifi password hint is blue-heron", conversation
    )
    assert "blue-heron" in hint.said and "Your" in hint.said, hint.said
    recalled = timed(client, "memory", "what do you remember about Dana?", conversation)
    assert "Dana" in recalled.said and "3pm" in recalled.said, recalled.said
    forgot = timed(client, "memory", "forget that the wifi hint thing", conversation)
    assert forgot.said.startswith("Forgot:") and "blue-heron" in forgot.said, forgot.said
    dana = timed(client, "memory", "forget that Dana thing please", conversation)
    assert dana.said == "Forgot: Dana prefers calls after 3pm.", dana.said
    left = fact_texts(client)
    assert not any("Dana" in text or "blue-heron" in text for text in left), left


@pytest.mark.parametrize("run", RUNS)
def test_unread_rundown(client: httpx.Client, run: int) -> None:
    reply = timed(client, "mail", "give me a rundown of my unread mail")
    answered(reply)
    assert reply.tools == ["mail_search"], reply.tools
    assert reply.said.startswith("You have ") and "Elena Marchetti" in reply.said, reply.said
    assert "Samuel Okafor" in reply.said and "Tomas Keller" in reply.said, reply.said


@pytest.mark.parametrize("run", RUNS)
def test_attention_skips_newsletters_and_the_calendar(client: httpx.Client, run: int) -> None:
    reply = timed(client, "mail", "anything that needs my attention right now?")
    answered(reply)
    assert set(reply.tools) == {"mail_search"}, reply.tools
    lines = reply.said.splitlines()
    assert "Elena Marchetti" in lines[1], reply.said
    assert NEWSLETTER not in reply.said and "newsletter" in lines[0], reply.said


@pytest.mark.parametrize("run", RUNS)
def test_newest_email(client: httpx.Client, run: int) -> None:
    reply = timed(client, "mail", "show me the newest email in my inbox")
    answered(reply)
    assert reply.said.startswith("Your newest email:\n- "), reply.said
    assert len(reply.said.splitlines()) == 2, reply.said


@pytest.mark.parametrize("run", RUNS)
def test_did_you_email_someone_reads_the_sent_folder(client: httpx.Client, run: int) -> None:
    reply = timed(client, "mail", "did you email Samuel yesterday?")
    reply.finished()
    assert reply.tools and set(reply.tools) == {"mail_search"}, reply.tools
    assert reply.said.startswith(("Yes", "No")), reply.said
    assert "Partnership proposal" in reply.said, reply.said


ROUND3_SEARCHES = {
    "how much is a barrel of brent crude today": re.compile(r"\$\s?\d{2,3}(?:\.\d+)?"),
    "did the NBA finals finish, who took it": re.compile(r"\b[A-Z][a-z]+"),
    "who is the current mayor of new york": re.compile(r"\b[A-Z][a-z]+ [A-Z][a-z]+"),
    "any news on the pakistan cricket team this week": re.compile(r"\b[A-Z][a-z]+"),
}
ROUND3_NO_SEARCH = [
    "whats 15% of 240",
    "how many days are in a leap year",
    "random one: whats a good name for a goldfish",
]


@pytest.mark.parametrize("run", RUNS)
@pytest.mark.parametrize("question", list(ROUND3_SEARCHES))
def test_round3_searches_answer_with_the_figure(
    web: None, client: httpx.Client, question: str, run: int
) -> None:
    reply = timed(client, "round3_search", question)
    body = answered(reply)
    assert "Something went wrong" not in reply.said, reply.said
    assert reply.tools[0] == "web_search", (reply.tools, reply.said)
    assert ROUND3_SEARCHES[question].search(body), reply.said
    assert reply.seconds < 20, (reply.seconds, reply.said)


@pytest.mark.parametrize("run", RUNS)
@pytest.mark.parametrize("message", ROUND3_NO_SEARCH)
def test_round3_questions_that_need_no_web(client: httpx.Client, message: str, run: int) -> None:
    reply = timed(client, "round3_no_search", message)
    answered(reply)
    assert "web_search" not in reply.tools, (reply.tools, reply.said)
    assert reply.said.strip(), reply.said
    if "15%" in message:
        assert reply.said == "15% of 240 = 36" and reply.seconds < 3, reply.said


@pytest.mark.parametrize("run", RUNS)
def test_round3_memory_by_name(client: httpx.Client, run: int) -> None:
    saved = timed(
        client,
        "round3_memory",
        "ok so remember that my sister Zainab is vegetarian and hates mushrooms",
    )
    assert "Zainab" in saved.said, saved.said
    chat = saved.conversation
    asked = timed(client, "round3_memory", "do you remember what zainab doesnt eat", chat)
    assert "vegetarian" in asked.said and "mushrooms" in asked.said, asked.said
    gone = timed(client, "round3_memory", "forget that thing about zainab pls", chat)
    assert gone.said.startswith("Forgot:") and "Zainab" in gone.said, gone.said
    assert not any("Zainab" in text for text in fact_texts(client))


@pytest.mark.parametrize("run", RUNS)
def test_round3_unread_and_attention(client: httpx.Client, run: int) -> None:
    unread = timed(client, "round3_mail", "any unread mail?")
    answered(unread)
    assert unread.said.startswith("You have "), unread.said
    assert unread.of("tool_call")[0]["args"]["query"] == "is:unread in:inbox"
    attention = timed(client, "round3_mail", "anything that needs my attention?")
    answered(attention)
    assert set(attention.tools) == {"mail_search"}, attention.tools
    assert "may need your attention" in attention.said.splitlines()[0], attention.said
    assert NEWSLETTER not in attention.said, attention.said
    sent = timed(client, "round3_mail", "did I email Samuel yesterday?")
    assert sent.said.startswith(("Yes", "No")), sent.said
    assert sent.of("tool_call")[0]["args"]["query"].startswith("in:sent to:Samuel after:")
