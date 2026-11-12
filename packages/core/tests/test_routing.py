from typing import Any

import pytest

from homer_core.agent.intents import (
    Calculate,
    ChatIntent,
    Forget,
    Intent,
    ReadCalendar,
    ReadEmail,
    Recall,
    Remember,
    WebSearch,
)
from homer_core.agent.routing import first_to_second_person, refined, routed, told_fact

FACTS = ["Dana prefers calls after 3pm.", "Your cat is called Mango."]


@pytest.mark.parametrize("message", ["thanks!", "hey", "good morning", "cool thank you"])
def test_greetings_and_thanks_skip_the_intent_call(message: str) -> None:
    assert routed(message, FACTS) == [ChatIntent(kind="chat")]


@pytest.mark.parametrize("message", ["no", "ok", "yes", "Email Bob", "what's the weather"])
def test_answers_and_requests_go_to_the_model(message: str) -> None:
    assert routed(message, FACTS) is None


def test_sums_route_to_the_calculator() -> None:
    assert routed("what is 17 times 23", []) == [
        Calculate(kind="calculate", expression="what is 17 times 23")
    ]


@pytest.mark.parametrize(
    ("message", "about"),
    [
        ("what do you remember about Dana?", "Dana"),
        ("what do you remember about me?", None),
        ("what do you know about me", None),
        ("What do you know about Dana", "Dana"),
        ("what have you saved", None),
    ],
)
def test_memory_questions_route_to_recall(message: str, about: str | None) -> None:
    assert routed(message, FACTS) == [Recall(kind="recall", about=about)]


def test_general_knowledge_questions_are_not_recall() -> None:
    assert routed("what do you know about REST APIs?", FACTS) is None


@pytest.mark.parametrize(
    ("message", "fact"),
    [
        ("Remember that Dana prefers calls after 3pm", "Dana prefers calls after 3pm."),
        (
            "btw remember that my cat is called Mango and shes allergic to chicken",
            "Your cat is called Mango and shes allergic to chicken.",
        ),
        ("My dog is Biscuit, remember that", "Your dog is Biscuit."),
        ("I like tea, remember", "You like tea."),
        ("please remember I'm vegetarian", "You're vegetarian."),
    ],
)
def test_remembered_facts_keep_the_users_words(message: str, fact: str) -> None:
    assert told_fact(message) == fact
    model = [Remember(kind="remember", fact="The user prefers calls after 3pm.")]
    assert refined(list(model), message, []) == [Remember(kind="remember", fact=fact)]


def test_first_to_second_person() -> None:
    assert (
        first_to_second_person("my wife and I like Rosa's coffee")
        == "Your wife and you like Rosa's coffee."
    )


@pytest.mark.parametrize(
    ("message", "kind"),
    [
        ("what's the capital of Australia", "chat"),
        ("explain REST", "chat"),
        ("who won the Lakers game last night", "web_search"),
        ("what's the latest on the Fed rate decision", "web_search"),
        ("search for the best ramen in Lisbon", "web_search"),
    ],
)
def test_search_only_for_things_that_change(message: str, kind: str) -> None:
    found = refined([WebSearch(kind="web_search", query=message)], message, [])
    assert [intent.kind for intent in found] == [kind]


def read_mail() -> ReadEmail:
    return ReadEmail(kind="read_email", question="anything needing my attention?")


@pytest.mark.parametrize(
    ("message", "previous", "kinds"),
    [
        ("anything needing my attention right now?", [], ["read_email"]),
        ("any mail from Rosa and what's on my calendar?", [], ["read_email", "read_calendar"]),
        ("anything from Rosa? and thursday?", [], ["read_email", "read_calendar"]),
        ("and from Rosa?", [{"kind": "read_calendar"}], ["read_email", "read_calendar"]),
    ],
)
def test_calendar_listing_only_when_asked(
    message: str, previous: list[dict[str, Any]], kinds: list[str]
) -> None:
    intents: list[Intent] = [read_mail(), ReadCalendar(kind="read_calendar")]
    assert [intent.kind for intent in refined(intents, message, previous)] == kinds


def test_a_lone_calendar_request_is_kept() -> None:
    found = refined([ReadCalendar(kind="read_calendar")], "and Rosa?", [])
    assert [intent.kind for intent in found] == ["read_calendar"]


@pytest.mark.parametrize(
    ("message", "about"),
    [
        ("forget that Dana thing please", "that Dana thing please"),
        ("please forget about the wifi hint", "the wifi hint"),
        ("forget that", "that"),
    ],
)
def test_forget_routes_without_the_model(message: str, about: str) -> None:
    assert routed(message, FACTS) == [Forget(kind="forget", about=about)]


def test_forget_it_goes_to_the_model() -> None:
    assert routed("forget it", FACTS) is None


@pytest.mark.parametrize(
    "message",
    ["any unread mail?", "anything that needs my attention?", "did I email Samuel yesterday?"],
)
def test_mail_reads_route_in_code(message: str) -> None:
    assert routed(message, FACTS) == [ReadEmail(kind="read_email", question=message)]


@pytest.mark.parametrize("message", ["did you send it?", "any meetings that need my attention"])
def test_status_and_calendar_questions_are_not_mail_reads(message: str) -> None:
    assert routed(message, FACTS) is None


def test_a_plain_remember_skips_the_intent_call() -> None:
    assert routed("ok so remember that my sister Zainab hates mushrooms", []) == [
        Remember(kind="remember", fact="Your sister Zainab hates mushrooms.")
    ]
    assert routed("remember that Dana likes tea and email her", []) is None


def test_do_you_remember_routes_to_recall() -> None:
    assert routed("do you remember what zainab doesnt eat", []) == [
        Recall(kind="recall", about="what zainab doesnt eat")
    ]


def test_people_in_memory_are_never_searched() -> None:
    search = [WebSearch(kind="web_search", query="dana allergies")]
    assert refined(search, "what is Dana allergic to right now", [], FACTS) == [
        ChatIntent(kind="chat")
    ]
    nba = [WebSearch(kind="web_search", query="nba finals")]
    assert refined(nba, "did the NBA finals finish, who took it", [], FACTS) == nba
