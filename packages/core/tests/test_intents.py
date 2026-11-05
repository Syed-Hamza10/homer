from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from homer_core.agent.claims import HONEST, review
from homer_core.agent.intents import (
    OUTPUT_TOOL,
    ChatIntent,
    CreateEvent,
    SendEmail,
    build_intent_agent,
    clock,
    date_table,
    extract,
)

NOW = datetime(2026, 11, 6, 10, 0, tzinfo=ZoneInfo("Asia/Karachi"))


def answering(*replies: Any, prompts: list[str] | None = None) -> FunctionModel:
    queue = list(replies)

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if prompts is not None:
            prompts.append(str(getattr(messages[-1], "instructions", "")))
        reply = queue.pop(0)
        if isinstance(reply, str):
            return ModelResponse(parts=[TextPart(content=reply)])
        return ModelResponse(parts=[ToolCallPart(OUTPUT_TOOL, {"intents": reply})])

    return FunctionModel(function=respond)


async def test_compound_message_gives_intents_in_order() -> None:
    prompts: list[str] = []
    model = answering(
        [
            {"kind": "send_email", "to": "Tomas", "body_instructions": "the invoice is paid"},
            {
                "kind": "create_event",
                "title": "Meeting with Tomas",
                "date": "2026-11-10",
                "window_start": "9am",
                "window_end": "11 am",
                "attendees": ["Tomas"],
            },
        ],
        prompts=prompts,
    )
    intents, usage = await extract(build_intent_agent(model), "email and meet Tomas", [], NOW)
    assert isinstance(intents[0], SendEmail) and intents[0].to == "Tomas"
    assert isinstance(intents[1], CreateEvent)
    assert (intents[1].window_start, intents[1].window_end) == ("09:00", "11:00")
    assert usage.requests == 1
    assert "tomorrow: Saturday 2026-11-07" in prompts[0]


async def test_earlier_turns_are_quoted_in_the_instructions_not_replayed() -> None:
    prompts: list[str] = []
    model = answering([{"kind": "chat"}], prompts=prompts)
    history: list[ModelMessage] = [
        ModelRequest(parts=[UserPromptPart(content="Email Sara about the invoice")]),
        ModelResponse(parts=[TextPart(content="Which Sara do you mean?")]),
    ]
    await extract(build_intent_agent(model), "Sara Mbeki", history, NOW)
    assert "User: Email Sara about the invoice\nHomer: Which Sara do you mean?" in prompts[0]


async def test_invalid_date_is_retried() -> None:
    bad = [{"kind": "create_event", "title": "x", "date": "next Tuesday", "start": "3pm"}]
    good = [{**bad[0], "date": "2026-11-10"}]
    intents, usage = await extract(build_intent_agent(answering(bad, good)), "x", [], NOW)
    assert isinstance(intents[0], CreateEvent) and intents[0].start == "15:00"
    assert usage.requests == 2


async def test_a_model_that_never_answers_with_intents_falls_back_to_chat() -> None:
    model = answering("hi", "hi", "hi", "hi")
    intents, _ = await extract(build_intent_agent(model), "hello", [], NOW)
    assert intents == [ChatIntent(kind="chat")]


async def test_empty_list_is_chat() -> None:
    intents, _ = await extract(build_intent_agent(answering([])), "hmm", [], NOW)
    assert intents == [ChatIntent(kind="chat")]


def test_date_table_names_every_day_of_the_coming_week() -> None:
    table = date_table(NOW)
    assert table.splitlines()[0] == "today: Friday 2026-11-06"
    assert "Tuesday 2026-11-10" in table and "Friday 2026-11-13" in table
    assert table.endswith("this week: 2026-11-02 to 2026-11-08")


@pytest.mark.parametrize(
    ("given", "expected"),
    [("3pm", "15:00"), ("3:30 PM", "15:30"), ("09.00", "09:00"), ("12am", "00:00"), ("", None)],
)
def test_clock(given: str, expected: str | None) -> None:
    assert clock(given) == expected


def test_clock_refuses_nonsense() -> None:
    with pytest.raises(ValueError):
        clock("lunchtime")
    with pytest.raises(ValidationError):
        CreateEvent(kind="create_event", title="x", date="2026-11-10", start="25:00")


@pytest.mark.parametrize(
    "text",
    [
        "I've sent the email to Ada.",
        "The meeting has been scheduled for Tuesday.",
        "Email sent successfully!",
        "I have created the event.",
    ],
)
def test_claims_without_an_action_are_replaced(text: str) -> None:
    assert review(text, acted=False) == HONEST
    assert review(text, acted=True) == text


@pytest.mark.parametrize(
    "text", ["Hello! How can I help?", "You can send it from the card.", "Sara sent you a file."]
)
def test_plain_text_passes(text: str) -> None:
    assert review(text, acted=False) == text
