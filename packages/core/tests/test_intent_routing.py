"""Every few-shot example and every QA round 5 failure line: given the model's structured
answer, the right job runs."""

import json
import re
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from homer_core.agent.intents import EXAMPLES, OUTPUT_TOOL, Background, build_intent_agent, extract
from homer_core.agent.router import parse_decision
from homer_core.agent.routing import refined
from homer_core.services.jobs import (
    calculate,
    chat,
    create_event,
    dispatch,
    draft_question,
    edit_email,
    mail_status,
    memory,
    read_calendar,
    read_email,
    send_email,
    web_search,
)
from homer_core.services.jobs.change_event import cancel, update

NOW = datetime(2026, 11, 14, 15, 0, tzinfo=ZoneInfo("Asia/Karachi"))
PLACEHOLDER = re.compile(r'"<[^>]+>"')
RUNNER = {
    "send_email": send_email.run,
    "edit_draft": edit_email.edit,
    "draft_question": draft_question.question,
    "send_status": mail_status.status,
    "discard_draft": draft_question.discard,
    "fix_last_action": dispatch.fix_last,
    "create_event": create_event.run,
    "update_event": update,
    "cancel_event": cancel,
    "read_calendar": read_calendar.run,
    "free_time": read_calendar.run,
    "read_email": read_email.run,
    "remember": memory.remember,
    "correct_memory": memory.correct,
    "forget": memory.drop,
    "recall": memory.recall,
    "calculate": calculate.run,
    "web_search": web_search.run,
    "chat": chat.run,
}


def examples() -> list[tuple[str, list[dict[str, Any]]]]:
    found = []
    day = (NOW + timedelta(days=1)).date().isoformat()
    for line in EXAMPLES.read_text().splitlines():
        if " -> " not in line:
            continue
        asked, answer = line.split(" -> ")
        message = asked.split('"', 1)[1].rsplit('"', 1)[0]
        found.append((message, json.loads(PLACEHOLDER.sub(f'"{day}"', answer))))
    return found


async def routed(message: str, answer: list[dict[str, Any]]) -> list[Any]:
    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[ToolCallPart(OUTPUT_TOOL, {"intents": answer})])

    agent = build_intent_agent(FunctionModel(function=respond))
    found, _ = await extract(agent, message, [], NOW, Background(timezone="Asia/Karachi"))
    return [dispatch.RUNNERS[intent.kind] for intent in refined(found, message, [])]


def test_there_are_about_forty_examples() -> None:
    assert 30 <= len(examples()) <= 45


@pytest.mark.parametrize(("message", "answer"), examples())
async def test_every_example_runs_its_job(message: str, answer: list[dict[str, Any]]) -> None:
    assert await routed(message, answer) == [RUNNER[intent["kind"]] for intent in answer]


ROUND_FIVE = [
    ("thanks. heavy week ahead", [{"kind": "chat"}], [chat.run]),
    (
        "actually he prefers mornings, before 11",
        [
            {
                "kind": "correct_memory",
                "about": "Imran meeting times",
                "new_fact": "Imran Qureshi prefers meetings in the mornings, before 11.",
            }
        ],
        [memory.correct],
    ),
    ("so when can imran meet", [{"kind": "recall", "about": "Imran"}], [memory.recall]),
    ("forget that about imran", [{"kind": "forget", "about": "Imran"}], [memory.drop]),
    ("what do you know about imran now", [{"kind": "recall", "about": "Imran"}], [memory.recall]),
    (
        "sorry I made a mistake, the wedding is on 19 december not 12",
        [
            {
                "kind": "correct_memory",
                "about": "Tariq's wedding date",
                "new_fact": "Your nephew Tariq Mehmood has his wedding on 19 December.",
            }
        ],
        [memory.correct],
    ),
    ("so what date is Tariq's wedding", [{"kind": "recall", "about": "Tariq"}], [memory.recall]),
    ("please forget about the wedding", [{"kind": "forget", "about": "wedding"}], [memory.drop]),
    ("do you know anything about Tariq?", [{"kind": "recall", "about": "Tariq"}], [memory.recall]),
    (
        "run me through tomorrow, and tell me if I have any gap after the design review",
        [
            {"kind": "read_calendar", "range": "tomorrow"},
            {"kind": "free_time", "date": "2026-11-15", "start": "12:00", "end": "17:00"},
        ],
        [read_calendar.run, read_calendar.run],
    ),
    (
        "which is my next meeeting please",
        [{"kind": "read_calendar", "range": "next_n_days", "days": 14}],
        [read_calendar.run],
    ),
    (
        "call with client wed 18 nov 11am",
        [
            {
                "kind": "create_event",
                "title": "Call with client",
                "date": "2026-11-18",
                "start": "11am",
            }
        ],
        [create_event.run],
    ),
    (
        "email kamran.raza@example.test: hearing notes are at https://example.test/notes/h-17",
        [
            {
                "kind": "send_email",
                "to": "kamran.raza@example.test",
                "body_instructions": "hearing notes are at https://example.test/notes/h-17",
            }
        ],
        [send_email.run],
    ),
    (
        "wheres the link",
        [{"kind": "draft_question", "question": "wheres the link"}],
        [draft_question.question],
    ),
    (
        "so the reply to Rosa has gone out, right? are you sure it was sent?",
        [{"kind": "send_status", "about": "Rosa"}],
        [mail_status.status],
    ),
    ("ok never mind, cancel it", [{"kind": "discard_draft"}], [draft_question.discard]),
    (
        "anything unread, and which of it actually needs me today?",
        [{"kind": "read_email", "question": "anything unread that needs me today?"}],
        [read_email.run],
    ),
    (
        "will it rain in lahore tomorrow dear",
        [{"kind": "web_search", "query": "Lahore rain forecast tomorrow", "needs_live_data": True}],
        [web_search.run],
    ),
    (
        "usd to eur rate right now, and whether it moved vs yesterday",
        [{"kind": "web_search", "query": "USD to EUR rate today", "needs_live_data": True}],
        [web_search.run],
    ),
    (
        "who won the champions league match last night? are you sure, check properly",
        [{"kind": "web_search", "query": "champions league result", "needs_live_data": True}],
        [web_search.run],
    ),
    (
        "sunset time karachi today",
        [{"kind": "web_search", "query": "sunset time Karachi today", "needs_live_data": True}],
        [web_search.run],
    ),
    (
        "what is newest iphone model now and how much price",
        [{"kind": "web_search", "query": "newest iPhone model price", "needs_live_data": True}],
        [web_search.run],
    ),
    (
        "latest stable python version and its release date",
        [{"kind": "web_search", "query": "latest stable Python version", "needs_live_data": True}],
        [web_search.run],
    ),
    (
        "thx. whats 2 hours before 6pm",
        [{"kind": "calculate", "expression": "6pm - 2 hours"}],
        [calculate.run],
    ),
    ("ok bye for now", [{"kind": "chat"}], [chat.run]),
]


@pytest.mark.parametrize(("message", "answer", "jobs"), ROUND_FIVE)
async def test_round_five_failures_run_the_right_job(
    message: str, answer: list[dict[str, Any]], jobs: list[Any]
) -> None:
    assert await routed(message, answer) == jobs


@pytest.mark.parametrize("message", ["ok never mind, cancel it", "never mind", "scrap that"])
def test_typed_rejections_settle_a_pending_card_without_the_model(message: str) -> None:
    assert parse_decision(message) == "reject"
