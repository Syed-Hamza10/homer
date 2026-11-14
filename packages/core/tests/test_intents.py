from datetime import date, datetime
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
from homer_core.agent.dates import date_table, default_format, numeric_date, weekday_date
from homer_core.agent.intents import (
    OUTPUT_TOOL,
    Background,
    CancelEvent,
    ChatIntent,
    CreateEvent,
    ReadCalendar,
    Remember,
    SendEmail,
    UpdateEvent,
    build_intent_agent,
    clock,
    extract,
)

NOW = datetime(2026, 11, 6, 10, 0, tzinfo=ZoneInfo("Asia/Karachi"))


def answering(*replies: Any, prompts: list[str] | None = None) -> FunctionModel:
    queue = list(replies)

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if prompts is not None:
            asked = " ".join(str(part.content) for part in messages[-1].parts)
            prompts.append(f"{getattr(messages[-1], 'instructions', '')}\n{asked}")
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


def test_date_table_names_fourteen_days_and_the_week_spans() -> None:
    table = date_table(NOW)
    lines = table.splitlines()
    assert lines[0] == "today: Friday 2026-11-06"
    assert "Wednesday 2026-11-11" in lines and "Thursday 2026-11-19" in lines
    assert "Friday 2026-11-20" not in table
    assert lines[-3:] == [
        "this week: 2026-11-02 to 2026-11-08",
        "next week: 2026-11-09 to 2026-11-15",
        "this weekend: 2026-11-07 to 2026-11-08",
    ]


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("schedule coffee with Maya next wed 11am", date(2026, 11, 11)),
        ("lunch w/ Tomas friday 1pm", date(2026, 11, 6)),
        ("next friday", date(2026, 11, 13)),
        ("tuesday next week", date(2026, 11, 10)),
        ("what do i have on mon 9th", date(2026, 11, 9)),
        ("move Monday to Tuesday", None),
        ("what is a for loop", None),
    ],
)
def test_weekday_date(message: str, expected: date | None) -> None:
    assert weekday_date(message, NOW.date()) == expected


@pytest.mark.parametrize(
    ("message", "form", "expected"),
    [
        ("calendar for 12/11", "DD/MM", date(2026, 11, 12)),
        ("calendar for 12/11", "MM/DD", date(2026, 12, 11)),
        ("on 3/1", "DD/MM", date(2027, 1, 3)),
        ("on 12.11.2026", "DD/MM", date(2026, 11, 12)),
        ("between 9-11", "DD/MM", None),
        ("at 3.05", "DD/MM", None),
        ("for 1/2 hour", "DD/MM", None),
        ("on 31/02", "DD/MM", None),
    ],
)
def test_numeric_date_follows_the_users_order(message: str, form: str, expected: date) -> None:
    assert numeric_date(message, NOW.date(), form) == expected  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("zone", "form"),
    [
        ("Asia/Karachi", "DD/MM"),
        ("Europe/Berlin", "DD/MM"),
        ("America/New_York", "MM/DD"),
        ("America/Indiana/Indianapolis", "MM/DD"),
        ("America/Toronto", "DD/MM"),
    ],
)
def test_default_date_format_comes_from_the_timezone(zone: str, form: str) -> None:
    assert default_format(zone) == form


async def test_wrong_weekday_from_the_model_is_resolved_in_code() -> None:
    wrong = [{"kind": "create_event", "title": "Coffee", "date": "2026-11-10", "start": "11am"}]
    intents, _ = await extract(
        build_intent_agent(answering(wrong)), "schedule coffee next wed 11am", [], NOW
    )
    assert isinstance(intents[0], CreateEvent) and intents[0].date == "2026-11-11"


async def test_a_right_weekday_is_kept() -> None:
    right = [{"kind": "create_event", "title": "Call", "date": "2026-11-13", "start": "3pm"}]
    intents, _ = await extract(build_intent_agent(answering(right)), "no, I meant Friday", [], NOW)
    assert isinstance(intents[0], CreateEvent) and intents[0].date == "2026-11-13"


async def test_numeric_date_overrides_a_us_reading() -> None:
    us = [{"kind": "read_calendar", "range": "date", "date": "2026-12-11"}]
    intents, _ = await extract(build_intent_agent(answering(us)), "calendar for 12/11", [], NOW)
    assert isinstance(intents[0], ReadCalendar)
    assert (intents[0].range, intents[0].date) == ("date", "2026-11-12")


async def test_the_day_after_follows_the_previous_date() -> None:
    prompts: list[str] = []
    again = [{"kind": "read_calendar", "range": "tomorrow"}]
    previous = [{"kind": "read_calendar", "date": "2026-11-07", "end_date": "2026-11-07"}]
    known = Background(previous=previous, facts=["The user's dog is called Biscuit."])
    intents, _ = await extract(
        build_intent_agent(answering(again, prompts=prompts)), "and the day after?", [], NOW, known
    )
    assert isinstance(intents[0], ReadCalendar) and intents[0].date == "2026-11-08"
    assert '"date": "2026-11-07"' in prompts[0]
    assert "- The user's dog is called Biscuit." in prompts[0]


async def test_day_after_tomorrow_is_left_to_the_model() -> None:
    given = [{"kind": "create_event", "title": "Call", "date": "2026-11-08", "start": "4pm"}]
    previous = [{"kind": "read_calendar", "date": "2026-11-09"}]
    intents, _ = await extract(
        build_intent_agent(answering(given)),
        "a call day after tomorrow 4pm",
        [],
        NOW,
        Background(previous=previous),
    )
    assert isinstance(intents[0], CreateEvent) and intents[0].date == "2026-11-08"


async def test_numeric_hint_is_in_the_prompt() -> None:
    prompts: list[str] = []
    model = answering([{"kind": "chat"}], prompts=prompts)
    await extract(build_intent_agent(model), "calendar for 12/11", [], NOW)
    assert "In this message 12/11 means Thursday 2026-11-12." in prompts[0]


async def test_new_intents_parse() -> None:
    model = answering(
        [
            {"kind": "update_event", "match": "design review", "new_start": "4pm"},
            {"kind": "cancel_event", "match": "lunch with Sam"},
            {"kind": "remember", "fact": "The user's dog is called Biscuit."},
            {"kind": "read_calendar", "range": "next_n_days", "days": 14, "person": "Rosa"},
        ]
    )
    intents, _ = await extract(build_intent_agent(model), "x", [], NOW)
    update, cancel, remember, read = intents
    assert isinstance(update, UpdateEvent) and update.new_start == "16:00"
    assert isinstance(cancel, CancelEvent) and cancel.match == "lunch with Sam"
    assert isinstance(remember, Remember)
    assert isinstance(read, ReadCalendar) and read.person == "Rosa"


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
        "Got it. I've cancelled the lunch with Sam.",
        "Your meeting has been moved to 4pm.",
        "I rescheduled the pitch rehearsal.",
        "Got it. Event 'Call with Rosa' on Fri 11 Nov 15:00-15:30 is ready.",
        "The email to ops@example.test has been sent.",
        "Your reply to Rosa has been sent.",
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


async def run_extract(given: list[dict[str, Any]], message: str) -> list[Any]:
    intents, _ = await extract(build_intent_agent(answering(given)), message, [], NOW)
    return intents


async def test_a_move_verb_never_creates_an_event() -> None:
    given = [
        {
            "kind": "create_event",
            "title": "call with Elena Marchetti",
            "date": "2026-11-10",
            "window_start": "09:00",
            "window_end": "12:00",
        }
    ]
    intents = await run_extract(given, "actually move it to Tuesday morning, same length")
    assert intents == [
        UpdateEvent(
            kind="update_event",
            match="call with Elena Marchetti",
            new_date="2026-11-10",
            new_start="09:00",
        )
    ]


async def test_a_correction_stays_an_update() -> None:
    update = [{"kind": "update_event", "match": "call with Maya", "new_date": "2026-11-12"}]
    intents = await run_extract(update, "no, I meant Friday")
    assert isinstance(intents[0], UpdateEvent) and intents[0].new_date == "2026-11-13"


@pytest.mark.parametrize(
    "message",
    ["respond to tomas about the invoice, say it goes out friday", "reply to Tomas: paid"],
)
async def test_reply_verbs_reply_to_the_latest_email(message: str) -> None:
    given = [{"kind": "send_email", "to": "Tomas", "body_instructions": "it goes out friday"}]
    intents = await run_extract(given, message)
    assert isinstance(intents[0], SendEmail) and intents[0].reply_to_latest_from == "Tomas"


async def test_identical_intents_run_once() -> None:
    read = {"kind": "read_calendar", "range": "today"}
    assert len(await run_extract([read, read], "what did I do today")) == 1


async def test_find_me_time_books_a_slot() -> None:
    given = [
        {
            "kind": "read_calendar",
            "range": "date",
            "date": "2026-11-09",
            "person": "Rosa",
            "start": "14:00",
            "end": "17:00",
        }
    ]
    intents = await run_extract(given, "find me 45 mins with Rosa on monday between 2 and 5pm")
    assert intents == [
        CreateEvent(
            kind="create_event",
            title="Meeting with Rosa",
            date="2026-11-09",
            window_start="14:00",
            window_end="17:00",
            duration_minutes=45,
            attendees=["Rosa"],
        )
    ]


@pytest.mark.parametrize(
    "given",
    [{"kind": "web_search", "query": "thursday", "needs_live_data": False}, {"kind": "chat"}],
)
async def test_whats_on_a_weekday_reads_the_calendar(given: dict[str, Any]) -> None:
    intents = await run_extract([given], "morning! quick q, whats on thursday?")
    assert intents == [ReadCalendar(kind="read_calendar", range="date", date="2026-11-12")]


@pytest.mark.parametrize(
    "given",
    [
        {"kind": "read_calendar", "range": "next_n_days", "days": 14, "start": "12:00"},
        {"kind": "read_calendar", "range": "next_week", "start": "12:00"},
    ],
)
async def test_one_weekday_question_is_that_day(given: dict[str, Any]) -> None:
    intents = await run_extract([given], "am i free next tuesday afternoon?")
    assert isinstance(intents[0], ReadCalendar)
    assert (intents[0].range, intents[0].date) == ("date", "2026-11-10")


async def test_next_meeting_looks_two_weeks_ahead() -> None:
    intents = await run_extract([{"kind": "read_calendar"}], "when's my next meeting?")
    assert isinstance(intents[0], ReadCalendar)
    assert (intents[0].range, intents[0].days) == ("next_n_days", 14)


async def test_a_person_without_a_time_looks_two_weeks_ahead() -> None:
    today = [{"kind": "read_calendar", "range": "today", "person": "Rosa"}]
    intents, _ = await extract(
        build_intent_agent(answering(today)), "what about Rosa, anything with her?", [], NOW
    )
    assert isinstance(intents[0], ReadCalendar)
    assert (intents[0].range, intents[0].days) == ("next_n_days", 14)
