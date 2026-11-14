from typing import Any

import pytest

from homer_core.agent.intents import (
    ChatIntent,
    Intent,
    ReadCalendar,
    ReadEmail,
    Remember,
    WebSearch,
)
from homer_core.agent.routing import first_to_second_person, refined, told_fact

FACTS = ["Dana prefers calls after 3pm.", "Your cat is called Mango."]


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
    ("message", "live", "kind"),
    [
        ("what's the capital of Australia", False, "chat"),
        ("explain REST", False, "chat"),
        ("who won the Lakers game last night", True, "web_search"),
        ("what's the latest on the Fed rate decision", True, "web_search"),
        ("search for the best ramen in Lisbon", False, "web_search"),
    ],
)
def test_search_only_for_live_data_or_when_asked(message: str, live: bool, kind: str) -> None:
    search = WebSearch(kind="web_search", query=message, needs_live_data=live)
    assert [intent.kind for intent in refined([search], message, [])] == [kind]


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


def test_several_calendar_reads_are_all_kept() -> None:
    reads: list[Intent] = [
        ReadCalendar(kind="read_calendar", range="tomorrow"),
        ReadCalendar(kind="read_calendar", range="tomorrow", asks_if="free"),
    ]
    message = "run me through tomorrow and tell me if I have time after the review"
    assert refined(reads, message, []) == reads


def test_people_in_memory_are_never_searched() -> None:
    search = [WebSearch(kind="web_search", query="dana allergies", needs_live_data=True)]
    assert refined(search, "what is Dana allergic to right now", [], FACTS) == [
        ChatIntent(kind="chat")
    ]
    nba = [WebSearch(kind="web_search", query="nba finals", needs_live_data=True)]
    assert refined(nba, "did the NBA finals finish, who took it", [], FACTS) == nba
