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
from homer_core.agent.dates import (
    date_table,
    default_format,
    from_now,
    now_line,
    numeric_date,
    relative_minutes,
    stated_times,
    this_week,
    weekday_date,
)
from homer_core.agent.intents import (
    OUTPUT_TOOL,
    Background,
    CancelEvent,
    ChatIntent,
    CreateEvent,
    FixLastAction,
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


async def test_next_meeting_reads_the_next_event() -> None:
    intents = await run_extract([{"kind": "read_calendar"}], "when's my next meeting?")
    assert isinstance(intents[0], ReadCalendar)
    assert (intents[0].range, intents[0].days) == ("next", None)


async def test_a_person_without_a_time_looks_two_weeks_ahead() -> None:
    today = [{"kind": "read_calendar", "range": "today", "person": "Rosa"}]
    intents, _ = await extract(
        build_intent_agent(answering(today)), "what about Rosa, anything with her?", [], NOW
    )
    assert isinstance(intents[0], ReadCalendar)
    assert (intents[0].range, intents[0].days) == ("next_n_days", 14)


SATURDAY = datetime(2026, 11, 14, 16, 7, tzinfo=ZoneInfo("Asia/Karachi"))


async def at_saturday(given: list[dict[str, Any]], message: str) -> list[Any]:
    agent = build_intent_agent(answering(given))
    intents, _ = await extract(agent, message, [], SATURDAY, Background(timezone="Asia/Karachi"))
    return intents


@pytest.mark.parametrize(
    ("today", "first", "last"),
    [
        (date(2026, 11, 11), date(2026, 11, 9), date(2026, 11, 15)),
        (date(2026, 11, 14), date(2026, 11, 14), date(2026, 11, 22)),
        (date(2026, 11, 15), date(2026, 11, 15), date(2026, 11, 22)),
        (date(2026, 11, 16), date(2026, 11, 16), date(2026, 11, 22)),
        (date(2026, 12, 31), date(2026, 12, 28), date(2027, 1, 3)),
    ],
)
def test_this_week_runs_to_sunday_and_past_it_on_a_weekend(
    today: date, first: date, last: date
) -> None:
    assert this_week(today) == (first, last)


def test_the_date_table_keeps_calendar_weeks_on_a_weekend() -> None:
    table = date_table(SATURDAY)
    assert "this week: 2026-11-09 to 2026-11-15" in table
    assert "next week: 2026-11-16 to 2026-11-22" in table


@pytest.mark.parametrize(
    ("today", "word", "expected"),
    [
        (date(2026, 11, 14), "monday", date(2026, 11, 16)),
        (date(2026, 11, 16), "monday", date(2026, 11, 16)),
        (date(2026, 11, 16), "next monday", date(2026, 11, 23)),
        (date(2026, 11, 15), "sunday", date(2026, 11, 15)),
    ],
)
def test_a_weekday_is_the_next_one_including_today(today: date, word: str, expected: date) -> None:
    assert weekday_date(f"free {word}?", today) == expected


@pytest.mark.parametrize(
    ("message", "times"),
    [
        ("am i free monday 16 nov at 2pm?", ["14:00"]),
        ("move workshop prep tomorrow to 11", ["11:00"]),
        ("free 16/11 at 14:30", ["14:30"]),
        ("move it to 11 nov", []),
        ("between 10am and 1pm", ["10:00", "13:00"]),
        ("lunch for 5 people", []),
    ],
)
def test_stated_times_never_read_a_date_as_a_time(message: str, times: list[str]) -> None:
    assert stated_times(message) == times


@pytest.mark.parametrize(
    ("message", "minutes"),
    [
        ("set a meet with him for 1 hour from now", 60),
        ("call Omar in an hour", 60),
        ("in 20 minutes", 20),
        ("in half an hour", 30),
        ("book a 1 hour meeting tomorrow", None),
    ],
)
def test_relative_minutes_are_read_by_code(message: str, minutes: int | None) -> None:
    assert relative_minutes(message) == minutes


def test_from_now_rounds_up_to_five_minutes() -> None:
    now = datetime(2026, 11, 14, 16, 23, 41, tzinfo=ZoneInfo("Asia/Karachi"))
    assert from_now(now, 60) == datetime(2026, 11, 14, 17, 25, tzinfo=ZoneInfo("Asia/Karachi"))
    assert now_line(now) == "Now: Saturday 14 Nov 2026, 16:23 PKT"


async def test_the_intent_prompt_states_now_in_the_user_zone() -> None:
    prompts: list[str] = []
    agent = build_intent_agent(answering([{"kind": "chat"}], prompts=prompts))
    await extract(agent, "hi", [], SATURDAY, Background(timezone="Asia/Karachi"))
    assert "Now: Saturday 14 Nov 2026, 16:07 PKT" in prompts[0]


async def test_the_time_asked_wins_over_the_day_of_the_month() -> None:
    given = [
        {"kind": "read_calendar", "range": "date", "date": "2026-11-16", "start": "16:00"}
        | {"asks_if": "free"}
    ]
    intents = await at_saturday(given, "am i free monday 16 nov at 2pm?")
    assert (intents[0].date, intents[0].start, intents[0].end) == ("2026-11-16", "14:00", None)


async def test_a_move_with_only_a_time_gets_that_time() -> None:
    given = [{"kind": "update_event", "match": "workshop prep", "new_date": "2026-11-15"}]
    intents = await at_saturday(given, "move workshop prep tomorrow to 11")
    assert isinstance(intents[0], UpdateEvent)
    assert (intents[0].new_date, intents[0].new_start) == ("2026-11-15", "11:00")


async def test_a_person_named_with_with_is_kept() -> None:
    given = [{"kind": "read_calendar", "range": "this_week"}]
    intents = await at_saturday(given, "anything with Sam this week? check the calendar")
    assert (intents[0].range, intents[0].person) == ("this_week", "Sam")


async def test_next_week_is_never_the_next_event() -> None:
    intents = await at_saturday([{"kind": "read_calendar", "range": "next"}], "plans next week?")
    assert intents[0].range == "next_week"


@pytest.mark.parametrize(
    ("given", "message", "title"),
    [
        (
            [{"kind": "read_calendar", "range": "date", "date": "2026-11-16"}],
            "find 45 minutes between 10am and 1pm on Monday 16 nov for client intake",
            "Client intake",
        ),
        (
            [{"kind": "read_calendar", "range": "tomorrow", "person": "Dana"}],
            "find 30 minutes with Dana tomorrow for a client intake call",
            "Client intake call with Dana",
        ),
        (
            [{"kind": "create_event", "title": "Meeting", "date": "2026-11-16", "start": "10am"}],
            "book monday at 10 for portfolio review",
            "Portfolio review",
        ),
    ],
)
async def test_an_event_takes_the_name_the_request_gives(
    given: list[dict[str, Any]], message: str, title: str
) -> None:
    intents = await at_saturday(given, message)
    assert isinstance(intents[0], CreateEvent) and intents[0].title == title


async def test_in_an_hour_is_counted_by_code_and_keeps_the_length() -> None:
    given = [
        {"kind": "create_event", "title": "Meet", "date": "2026-11-14", "start": "15:00"}
        | {"end": "16:00", "attendees": ["Omar"]}
    ]
    intents = await at_saturday(given, "set a meet with him for 1 hour from now")
    assert isinstance(intents[0], CreateEvent)
    assert (intents[0].relative_minutes, intents[0].start, intents[0].duration_minutes) == (
        60,
        None,
        60,
    )


async def after(previous: list[dict[str, Any]], given: list[dict[str, Any]], message: str) -> Any:
    agent = build_intent_agent(answering(given))
    known = Background(previous=previous, timezone="Asia/Karachi")
    intents, _ = await extract(agent, message, [], SATURDAY, known)
    return intents[0]


TUESDAY_READ = {"kind": "read_calendar", "range": "date", "date": "2026-11-17"}
BOOKED = {"kind": "create_event", "title": "Dinner", "date": "2026-11-19", "approval_id": 7}
DRAFTED = {"kind": "send_email", "to": "Omar", "approval_id": 3}


@pytest.mark.parametrize(
    "misread",
    [
        {"kind": "recall", "about": "wednesday"},
        {"kind": "chat"},
        {"kind": "send_status"},
    ],
)
async def test_a_day_correction_after_a_calendar_read_reads_that_day(
    misread: dict[str, Any],
) -> None:
    intent = await after([TUESDAY_READ], [misread], "no wait, i mean wednesday")
    assert intent == ReadCalendar(kind="read_calendar", range="date", date="2026-11-18")


@pytest.mark.parametrize(
    ("previous", "message"),
    [
        ([BOOKED], "no wait, i mean friday"),
        ([BOOKED], "actually 8pm"),
        ([DRAFTED], "no, make it Friday"),
    ],
)
async def test_a_correction_after_a_card_fixes_the_card(
    previous: list[dict[str, Any]], message: str
) -> None:
    intent = await after(previous, [{"kind": "recall", "about": "friday"}], message)
    assert intent == FixLastAction(kind="fix_last_action", what_is_wrong=message)


RECALL = {"kind": "recall", "about": "x"}
FACT_FIX = {"kind": "correct_memory", "about": "birthday", "new_fact": "His birthday is Wed."}


@pytest.mark.parametrize(
    ("previous", "message", "given"),
    [
        ([], "no wait, i mean wednesday", RECALL),
        ([BOOKED], "no thanks, that's all", RECALL),
        ([TUESDAY_READ], "what do you know about wednesday's guest?", RECALL),
        ([TUESDAY_READ], "sorry, his birthday is on wednesday", FACT_FIX),
    ],
)
async def test_other_messages_keep_the_models_reading(
    previous: list[dict[str, Any]], message: str, given: dict[str, Any]
) -> None:
    intent = await after(previous, [given], message)
    assert intent.kind == given["kind"]


async def test_a_reminder_on_my_calendar_is_a_calendar_event() -> None:
    given = [{"kind": "remind", "text": "Tea with the neighbour", "date": "2026-11-14"}]
    message = "put a reminder on my calendar in 30 minutes, call it Tea with the neighbour"
    intent = (await at_saturday(given, message))[0]
    assert isinstance(intent, CreateEvent)
    assert (intent.title, intent.date, intent.relative_minutes) == (
        "Tea with the neighbour",
        "2026-11-14",
        30,
    )


async def test_a_plain_reminder_stays_a_reminder() -> None:
    given = [{"kind": "remind", "text": "call mum", "date": "2026-11-14", "time": "18:00"}]
    intent = (await at_saturday(given, "remind me to call mum at 6pm"))[0]
    assert intent.kind == "remind"
