from collections.abc import AsyncIterator
from datetime import date, datetime, timedelta
from types import ModuleType
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from fastmcp.client import Client
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models import Model
from pydantic_ai.models.function import AgentInfo, FunctionModel

from homer_core.agent.intents import OUTPUT_TOOL
from homer_core.config import Settings
from homer_core.mcp.manager import McpManager
from homer_core.services.jobs import read_email, web_search
from homer_core.services.jobs.read_email import Span, sent_query, span
from homer_core.services.jobs.web_search import cleaned, dated_query, published, ranked

from .conftest import ORIGIN, PostChat, load_fake_server
from .test_jobs import calls, of, said

KARACHI = "Asia/Karachi"
ZONE = ZoneInfo(KARACHI)
NOW = datetime(2026, 11, 6, 9, 0, tzinfo=ZONE)
Turns = list[list[dict[str, Any]]]


def today() -> date:
    return datetime.now(ZONE).date()


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
def intents() -> Turns:
    return []


@pytest.fixture
def replies() -> list[str]:
    return ["It launched."]


@pytest.fixture
def instructions() -> list[str]:
    return []


@pytest.fixture
def model(intents: Turns, replies: list[str], instructions: list[str]) -> Model:
    """Plays one intents list per turn, then `replies` in order for each plain answer (the
    last one repeats)."""
    queue = list(intents)
    answers = list(replies)

    def reply() -> str:
        return answers.pop(0) if len(answers) > 1 else answers[0]

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if OUTPUT_TOOL in {tool.name for tool in info.output_tools}:
            found = queue.pop(0) if queue else [{"kind": "chat"}]
            return ModelResponse(parts=[ToolCallPart(OUTPUT_TOOL, {"intents": found})])
        instructions.append(str(getattr(messages[-1], "instructions", "")))
        return ModelResponse(parts=[TextPart(content=reply())])

    async def stream(messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator[str]:
        instructions.append(str(getattr(messages[-1], "instructions", "")))
        yield reply()

    return FunctionModel(function=respond, stream_function=stream, model_name="test")


def search(query: str) -> list[list[dict[str, Any]]]:
    return [[{"kind": "web_search", "query": query}]]


class TestWebSearch:
    @pytest.mark.parametrize(("intents", "replies"), [(search("launch news"), ["It launched."])])
    def test_snippets_that_answer_need_no_second_call(
        self, post_chat: PostChat, instructions: list[str]
    ) -> None:
        frames = post_chat({"message": "what's the latest launch news?"})
        assert said(frames).startswith("It launched.\n\n**Sources**\n- [Launch news](")
        assert len(instructions) == 1 and "Snippet A" in instructions[0]
        assert "answer the user's question directly in 1-3 sentences" in instructions[0].lower()

    @pytest.mark.parametrize(
        ("intents", "replies"),
        [
            (
                search("launch news"),
                ["NEED_PAGES", "Based on the provided text, it launched on Monday."],
            )
        ],
    )
    def test_pages_are_read_when_snippets_do_not_answer(
        self, post_chat: PostChat, fake_search: ModuleType, instructions: list[str]
    ) -> None:
        frames = post_chat({"message": "what's the latest launch news?"})
        assert sorted(fake_search.fetched) == [
            "https://news.example.test/a",
            "https://news.example.test/b",
        ]
        assert "Page A text" in instructions[1]
        assert said(frames) == (
            "It launched on Monday.\n\n**Sources**\n- [Launch news](https://news.example.test/a)\n"
            "- [More news](https://news.example.test/b)"
        )

    @pytest.mark.parametrize(
        ("intents", "replies"),
        [(search("premier league results yesterday"), ["Arsenal won."])],
    )
    def test_yesterday_becomes_a_date_in_the_query_and_the_prompt(
        self, post_chat: PostChat, fake_search: ModuleType, instructions: list[str]
    ) -> None:
        post_chat({"message": "who won the premier league match yesterday"})
        yesterday = today() - timedelta(days=1)
        expected = f"premier league results {yesterday:%B} {yesterday.day} {yesterday.year}"
        assert fake_search.queries == [expected]
        assert f"Yesterday was {yesterday:%A} {yesterday.day} {yesterday:%B %Y}." in instructions[0]

    @pytest.mark.parametrize(
        ("intents", "replies"),
        [(search("capital of Australia"), ["The capital of Australia is Canberra."])],
    )
    def test_stable_knowledge_is_answered_without_search(self, post_chat: PostChat) -> None:
        frames = post_chat({"message": "what's the capital of Australia"})
        assert calls(frames) == [] and said(frames) == "The capital of Australia is Canberra."

    @pytest.mark.parametrize("replies", [["I don't know."]])
    def test_small_talk_never_searches(self, post_chat: PostChat) -> None:
        for message in ("no", "ok", "thanks"):
            assert calls(post_chat({"message": message})) == []


def test_dated_query() -> None:
    day = date(2026, 11, 6)
    assert dated_query("Lakers game last night", "", day) == "Lakers game November 5 2026"
    assert dated_query("Lakers score", "who won last night?", day) == (
        "Lakers score November 5 2026"
    )
    assert dated_query("gold price today", "", day) == "gold price November 6 2026"
    assert dated_query("Fed decision", "latest on the Fed", day) == "Fed decision"


def result(snippet: str, url: str) -> dict[str, Any]:
    return {"title": "", "url": url, "snippet": snippet}


def test_future_results_are_dropped_and_fresh_ones_lead() -> None:
    found = [
        result("Oct 20, 2026 - season preview", "old"),
        result("Live scores and schedule", "undated"),
        result("Nov 9, 2026 - upcoming game", "future"),
        result("5 hours ago - Lakers beat the Suns 112-104", "fresh"),
    ]
    assert [r["url"] for r in ranked(found, NOW, latest=True)] == ["fresh", "undated", "old"]
    assert [r["url"] for r in ranked(found, NOW, latest=False)] == ["old", "undated", "fresh"]
    assert published("6 Nov 2026 · Fed holds rates", NOW) == date(2026, 11, 6)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Based on the provided text, the Fed held rates.", "The Fed held rates."),
        ("The Fed held rates, according to the results.", "The Fed held rates."),
        (
            "The Fed held rates at 4%. The provided pages do not say more.",
            "The Fed held rates at 4%.",
        ),
    ],
)
def test_talk_about_the_sources_is_removed(text: str, expected: str) -> None:
    assert cleaned(text) == expected


class TestCalculator:
    def test_sums_need_no_model(self, post_chat: PostChat) -> None:
        frames = post_chat({"message": "what is 17 times 23"})
        assert said(frames) == "17 times 23 = 391" and calls(frames) == []

    @pytest.mark.parametrize("replies", [["0.87"]])
    def test_currency_uses_one_searched_rate(
        self, post_chat: PostChat, fake_search: ModuleType
    ) -> None:
        frames = post_chat({"message": "how many euros is 3,400 US dollars"})
        assert fake_search.queries == ["1 USD to EUR exchange rate today"]
        assert said(frames).startswith(
            "3,400 USD is about 2,958 EUR, at 1 USD = 0.87 EUR.\n\n**Sources**\n"
        )

    def test_units_are_converted_in_code(self, post_chat: PostChat) -> None:
        assert said(post_chat({"message": "10 miles to km"})) == "10 miles is 16.0934 km."


def remember(fact: str) -> list[dict[str, Any]]:
    return [{"kind": "remember", "fact": fact}]


class TestMemory:
    @pytest.mark.parametrize(
        "intents",
        [
            [
                remember("The user prefers calls after 3pm."),
                remember("The user's wifi hint is blue-heron."),
                remember("The user drinks oat milk."),
                [{"kind": "forget", "about": "the wifi hint thing"}],
                [{"kind": "forget", "about": "Dana thing"}],
            ]
        ],
    )
    def test_forget_finds_the_fact_by_keyword(
        self, post_chat: PostChat, logged_in: TestClient
    ) -> None:
        stored = post_chat({"message": "Remember that Dana prefers calls after 3pm"})
        assert said(stored) == "Saved to memory: Dana prefers calls after 3pm."
        post_chat({"message": "also remember that my wifi password hint is blue-heron"})
        post_chat({"message": "remember I drink oat milk"})
        assert said(post_chat({"message": "forget that the wifi hint thing"})) == (
            "Forgot: Your wifi password hint is blue-heron."
        )
        assert said(post_chat({"message": "forget that Dana thing please"})) == (
            "Forgot: Dana prefers calls after 3pm."
        )
        facts = logged_in.get("/api/facts").json()
        assert [fact["text"] for fact in facts] == ["You drink oat milk."]

    @pytest.mark.parametrize(
        "intents",
        [[remember("x"), remember("x"), [{"kind": "forget", "about": "the gym thing"}]]],
    )
    def test_recall_lists_and_forget_says_when_nothing_matches(
        self, post_chat: PostChat, logged_in: TestClient
    ) -> None:
        post_chat({"message": "Remember that Dana prefers calls after 3pm"})
        post_chat({"message": "remember that my cat is called Mango"})
        assert said(post_chat({"message": "what do you remember about Dana?"})) == (
            "Here is what I have saved about Dana:\n- Dana prefers calls after 3pm."
        )
        assert said(post_chat({"message": "what do you know about me?"})) == (
            "Here is what I have saved:\n- Your cat is called Mango.\n"
            "- Dana prefers calls after 3pm."
        )
        assert said(post_chat({"message": "forget the gym thing"})).startswith(
            "I have nothing saved like that"
        )
        facts = logged_in.get("/api/facts").json()
        gone = logged_in.delete(f"/api/facts/{facts[0]['id']}", headers=ORIGIN)
        assert gone.status_code == 204 and len(logged_in.get("/api/facts").json()) == 1


def read(question: str, **fields: Any) -> list[list[dict[str, Any]]]:
    return [[{"kind": "read_email", "question": question, **fields}]]


class TestReadEmail:
    @pytest.mark.parametrize(
        ("intents", "replies"),
        [(read("give me a rundown of my unread mail"), ["1. Asks to pay invoice 42\n2. Asks"])],
    )
    def test_unread_lists_one_line_per_message(self, post_chat: PostChat) -> None:
        frames = post_chat({"message": "give me a rundown of my unread mail"})
        assert of(frames, "tool_call")[0]["args"]["query"] == "is:unread in:inbox"
        assert said(frames) == (
            "You have 2 unread emails:\n"
            "- ada@example.test: Invoice 42 - Asks to pay invoice 42\n"
            "- ada@example.test: Proposal follow-up - Asks"
        )

    @pytest.mark.parametrize(
        ("intents", "replies"),
        [(read("did you email Ada yesterday?", sender="Ada"), ["unused"])],
    )
    def test_sent_mail_is_read_from_the_sent_folder(self, post_chat: PostChat) -> None:
        frames = post_chat({"message": "did you email Ada yesterday?"})
        queries = [call["args"]["query"] for call in of(frames, "tool_call")]
        assert queries[0].startswith("in:sent to:Ada after:")
        assert said(frames).startswith("No, I found no email sent to Ada yesterday.")

    @pytest.mark.parametrize(
        ("intents", "replies"),
        [(read("what did Ada ask?", sender="Ada"), ["The provided emails have no information."])],
    )
    def test_a_no_information_answer_becomes_the_list(self, post_chat: PostChat) -> None:
        frames = post_chat({"message": "what did Ada ask?"})
        assert of(frames, "replace")[-1]["text"] == (
            "Here is what I found:\n"
            "- ada@example.test: Invoice 42 - Please pay invoice 42 by Friday.\n"
            "- ada@example.test: Proposal follow-up - Did you get a chance to read the proposal?"
        )


def test_sent_queries_use_real_local_dates() -> None:
    period = span("did I email Samuel yesterday?", NOW)
    assert period.start == datetime(2026, 11, 5, tzinfo=ZONE)
    query = sent_query("Samuel Okafor", period)
    start, end = int(period.start.timestamp()), int(NOW.replace(hour=0).timestamp())
    assert query == f"in:sent to:Samuel after:{start} before:{end}"
    assert sent_query(None, Span("", None, None)) == "in:sent"


def test_newsletters_are_not_attention() -> None:
    letter = {"from": "The Brief <newsletter@brief.example.test>", "body": "Read more."}
    promo = {"from": "a@example.test", "labels": ["CATEGORY_PROMOTIONS"], "body": "Sale"}
    unsub = {"from": "a@example.test", "metadata": {"list_unsubscribe": True}, "body": "Hi"}
    person = {"from": "Elena <elena@example.test>", "body": "Can you review the deck?"}
    assert [read_email.is_bulk(m) for m in (letter, promo, unsub, person)] == [
        True,
        True,
        True,
        False,
    ]


def test_priority_contacts_come_first() -> None:
    messages = [
        {"id": "1", "from": "a@example.test"},
        {"id": "2", "from": "b@example.test", "labels": ["STARRED"]},
        {"id": "3", "from": "Rosa <rosa@example.test>"},
    ]
    assert [m["id"] for m in read_email.ranked(messages, ["rosa"])] == ["3", "2", "1"]


def test_web_search_module_keeps_its_limits() -> None:
    assert (web_search.PAGES, web_search.PAGE_TIMEOUT_SECONDS) == (2, 5.0)
