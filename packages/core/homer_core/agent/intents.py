import json
import re
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from functools import cache
from pathlib import Path
from typing import Annotated, Any, Literal

import structlog
from pydantic import BaseModel, BeforeValidator, Field
from pydantic_ai import Agent, ToolOutput
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ModelMessage, ModelRequest
from pydantic_ai.models import Model
from pydantic_ai.usage import RunUsage

from homer_core.agent.dates import (
    DAY_AFTER,
    NEXT_WEEK,
    WEEKDAY,
    WEEKDAY_WORDS,
    DateFormat,
    date_table,
    now_line,
    numeric_date,
    numeric_hint,
    relative_minutes,
    stated_times,
    weekday_date,
)
from homer_core.agent.voice import capitalised

log = structlog.get_logger(__name__)

DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIME = re.compile(r"^\s*(\d{1,2})(?:[:.](\d{2}))?\s*([ap]\.?m\.?)?\s*$", re.IGNORECASE)
OUTPUT_TOOL = "record_intents"
CONTEXT_CHARS = 300
CORRECTION = re.compile(
    r"^\s*(?:no|nope|sorry|actually|oops|wait)\b|\bI meant\b|\bmake it\b|\bchange it\b"
    r"|\binstead\b|\bstill says\b",
    re.IGNORECASE,
)
DATED = re.compile(
    r"\b(?:today|tonight|tomorrow|yesterday|week|weekend|month|days?|morning|afternoon|evening"
    r"|jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec|\d{1,2}(?:st|nd|rd|th)?)\b",
    re.IGNORECASE,
)
SEARCH_DAYS = 14
MOVE = re.compile(
    r"\b(?:move|moving|moved|reschedule|rescheduling|push|pushing|shift|shifting|postpone"
    r"|bring (?:it |that )?forward)\b",
    re.IGNORECASE,
)
REPLY = re.compile(
    r"^\W*(?:(?:ok|okay|please|pls|can you|could you|hey)[,]?\s+)*"
    r"(?:reply|respond|write back|answer)\b",
    re.IGNORECASE,
)
NEXT_EVENT = re.compile(r"\b(?:next|upcoming) (?:mee+ting|event|call|appointment)\b", re.IGNORECASE)
SLOT = re.compile(
    r"\bfind (?:me |us )?(?:a |an )?"
    r"(?:(\d+)\s*(?:-\s*)?(min|mins|minutes|minute|h|hr|hrs|hour|hours)"
    r"|time|slot|free slot)\b",
    re.IGNORECASE,
)
WITH_PERSON = re.compile(r"\bwith\s+([A-Za-z][\w'-]+)")
NOT_PEOPLE = frozenset(
    {"me", "my", "the", "a", "an", "anyone", "anybody", "someone", "somebody", "him", "her"}
    | {"them", "us", "you", "whom", "nobody", "no", "any", "clients", "client", "team"}
)
TITLE_FOR = re.compile(
    r"\b(?:for|called|call it|titled|named)\s+(?:a |an |the |my |our )?"
    r"(?P<title>[A-Za-z][^,.;!?]*?)\s*(?=$|[,.;!?]|\s+(?:on|at|between|from|tomorrow|today"
    r"|next|this|in|before|after|by|anywhere|sometime)\b)",
    re.IGNORECASE,
)
NOT_TITLES = frozenset({"us", "me", "them", "it", "that", "this", "time", "a slot", "slot"})
GENERIC_TITLES = frozenset({"meeting", "event", "call", "appointment", "new event", "booking"})
WHATS_ON = re.compile(
    r"^\W*(?:\w+[,!.]?\s+){0,4}?(?:what(?:'s|s| is)|anything)\s+(?:on|planned|happening|the plan)"
    r"\b(?:\s+(?:for|on))?\s+(?:today|tonight|tomorrow|this \w+|next \w+|"
    + "|".join(WEEKDAY_WORDS)
    + r")\b",
    re.IGNORECASE,
)

INSTRUCTIONS = """You read the user's latest message and record what they want Homer, an email,
calendar, memory and web assistant, to do. Do not answer it: call record_intents once with
every intent, in the order asked.
Intents:
- send_email: write, send or reply to someone. `to` is the name or address as written;
  `body_instructions` is what it should say; `reply_to_latest_from` only when answering
  their email. When the message says "this", "that" or "it" about something in the earlier
  turns (a web answer, an email, an event), `body_instructions` names that thing in full.
- edit_draft: change the email draft pending in this chat ("make it shorter", "add that I'm
  late", "change the subject to X", "add the event link"). `instruction` is the change.
- draft_question: a question about the pending draft ("where's the link?", "does it mention
  Friday?", "show me the draft"). `question` is the question.
- send_status: whether an email went out ("did you send it?", "has the reply to Sarah gone
  out?"). `about` is the person's name or address, empty for "it".
- discard_draft: drop the pending draft or card ("cancel it", "never mind", "scrap that").
- fix_last_action: the user says Homer's last action (an event booked or moved, a draft
  written) is wrong or asks why it came out that way ("why 15:00?", "that's wrong", "that's
  not what I asked"). `what_is_wrong` in their words.
- create_event: book a NEW event. `title` is the event's name from the message ("client
  intake", "Budget talk"), never a bare "Meeting" when the message names it; `date` from the
  table; start/end for an exact time; window_start/window_end for a free slot inside a range;
  `relative_minutes` for a start counted from now ("in an hour" 60, "20 minutes from now"
  20), never a start you work out yourself; `after_next_event` for "right after my next
  meeting"; `attendees` are names or addresses;
  `description` is the topic from the earlier turns when the event is about "this" or "it".
- update_event: move, retime or rename an EXISTING event, also one booked earlier in this
  chat. `match` names it ("design review", or "it"); `date` only for the day it is on now;
  fill only what changes: new_date, new_start, new_end, new_title, duration_minutes,
  relative_minutes (a new start counted from now).
- cancel_event: delete an existing calendar event. `match` names it.
- read_calendar: what is on the calendar. range is next (the next upcoming event: "next
  meeting", "what's next"), today, tomorrow, this_week, next_week, this_weekend, next_n_days
  (with `days`), date (`date`) or range (`date` to `end_date`). `person` when one is named
  ("anything with Sam" is person Sam), `title_contains` for an event's name (next_n_days,
  days 14, when no time is given).
  start/end narrow the time of day: morning 09:00-12:00, afternoon 12:00-17:00, evening
  17:00-21:00.
- free_time: whether the user is free or busy, or has a gap. `date` (and `end_date`),
  start/end for the part of the day; `start` alone for one time ("at 2pm" is 14:00). The day
  of a date ("16 nov") is never a time.
- read_email: questions about email received or sent. `sender`, `query` for a topic,
  `latest` for the newest; `question` is what they want to know.
- remember: a new fact to keep. `fact` is one full sentence with every name and detail,
  saying "your" for the user; `about_person` is who it is about, if anyone.
- correct_memory: the user corrects a saved fact ("actually", "no, it's", "I made a
  mistake"). `about` is the person and topic; `new_fact` is the whole corrected fact as one
  sentence naming the person.
- forget: delete saved facts. `about` is the person or topic, empty for "forget that".
- recall: only a question about something the user told Homer to remember: people,
  preferences and personal details under Saved facts. `about` is the person or topic.
  Meetings, events, the schedule, free time, email and the inbox are never recall.
- calculate: arithmetic, percentages, time sums, unit or currency conversion. `expression`
  as written ("15% of 240", "3400 USD to EUR").
- web_search: needs the internet. `query`; `needs_live_data` is true for things that change
  (news, weather, prices, scores, who holds an office) or when the user asks to search.
- remind: remind the user of something. `text`, `date`, `time`.
- day_summary: what the user got done today, or what is still open or waiting on them.
- chat: anything else: greetings, thanks, goodbyes, general knowledge, questions about
  Homer, and requests too vague to act on (Homer then asks what they mean).
Rules:
- Dates: copy them from the table, never calculate one. A weekday name is the first day in
  the table with that name after today, or today when today has it and "next" is not said.
- With a card pending in this chat, "it", "the draft", "the link" and "the email" mean that
  card: questions about it are draft_question, changes are edit_draft, "cancel it" or "never
  mind" is discard_draft. "Email her about it" goes to the person named in the earlier turns;
  with no one named anywhere it is chat.
- A follow-up ("and the day after?", "what about Omar?") repeats the previous request's kind
  and changes only what the message changes; "the day after" is the day after the previous
  date. A correction ("actually I meant Friday", "make it 4pm") repeats the previous request
  with that field changed. A correction of a saved fact is correct_memory.
- Questions about the user or a person in the saved facts are recall, never web_search.
- Questions about meetings, the calendar, email or the inbox are read_calendar, free_time or
  read_email even when nothing is saved about them.
- Earlier turns only say who or what the message refers to; never repeat an earlier request
  unless the message follows it up.
Examples (context, then message, then intents):
{examples}"""
CONTEXT = """{now}
Timezone: {timezone}
Saved facts:
{facts}
Dates:
{dates}
Pending in this chat: {pending}
Previous request: {previous}
Earlier turns:
{context}

Latest message: {message}{numeric}"""
EXAMPLES = Path(__file__).parent / "prompts" / "intent_examples.md"


def clock(value: str | None) -> str | None:
    """Normalises '3pm', '3:30 PM', '15', '09.00' to HH:MM; None stays None."""
    if value is None or not value.strip():
        return None
    match = TIME.match(value)
    if match is None:
        raise ValueError(f"time must look like 15:00 or 3pm, got {value!r}")
    hour, minute = int(match.group(1)), int(match.group(2) or 0)
    suffix = (match.group(3) or "").lower().replace(".", "")
    if suffix == "pm" and hour < 12:
        hour += 12
    if suffix == "am" and hour == 12:
        hour = 0
    if hour > 23 or minute > 59:
        raise ValueError(f"not a time of day: {value!r}")
    return f"{hour:02d}:{minute:02d}"


def iso_date(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    value = value.strip()
    if not DATE.match(value):
        raise ValueError(f"date must be YYYY-MM-DD from the list, got {value!r}")
    date.fromisoformat(value)
    return value


IsoDate = Annotated[str, BeforeValidator(iso_date), Field(description="YYYY-MM-DD")]
OptionalDate = Annotated[
    str | None, BeforeValidator(iso_date), Field(default=None, description="YYYY-MM-DD")
]
Clock = Annotated[str | None, BeforeValidator(clock), Field(default=None, description="HH:MM")]


class SendEmail(BaseModel):
    kind: Literal["send_email"]
    to: str
    subject: str | None = None
    body_instructions: str
    reply_to_latest_from: str | None = None


class CreateEvent(BaseModel):
    kind: Literal["create_event"]
    title: str
    date: IsoDate
    start: Clock
    end: Clock
    window_start: Clock
    window_end: Clock
    duration_minutes: int | None = None
    relative_minutes: int | None = Field(default=None, ge=1, le=24 * 60)
    after_next_event: bool = False
    attendees: list[str] = Field(default_factory=list)
    description: str | None = None


class UpdateEvent(BaseModel):
    kind: Literal["update_event"]
    match: str
    date: OptionalDate
    new_date: OptionalDate
    new_start: Clock
    new_end: Clock
    new_title: str | None = None
    duration_minutes: int | None = None
    relative_minutes: int | None = Field(default=None, ge=1, le=24 * 60)


class FixLastAction(BaseModel):
    kind: Literal["fix_last_action"]
    what_is_wrong: str


class CancelEvent(BaseModel):
    kind: Literal["cancel_event"]
    match: str
    date: OptionalDate


class ReadCalendar(BaseModel):
    kind: Literal["read_calendar"]
    range: Literal[
        "today",
        "tomorrow",
        "this_week",
        "next_week",
        "this_weekend",
        "next_n_days",
        "next",
        "date",
        "range",
    ] = "today"
    date: OptionalDate
    end_date: OptionalDate
    days: int | None = Field(default=None, ge=1, le=60)
    person: str | None = None
    title_contains: str | None = None
    start: Clock
    end: Clock
    asks_if: Literal["free", "busy"] | None = None


class ReadEmail(BaseModel):
    kind: Literal["read_email"]
    sender: str | None = None
    query: str | None = None
    latest: bool = False
    question: str


class WebSearch(BaseModel):
    kind: Literal["web_search"]
    query: str
    needs_live_data: bool


class Remind(BaseModel):
    kind: Literal["remind"]
    text: str
    date: IsoDate
    time: Clock


class Remember(BaseModel):
    kind: Literal["remember"]
    fact: str
    about_person: str | None = None


class CorrectMemory(BaseModel):
    kind: Literal["correct_memory"]
    about: str
    new_fact: str


class Forget(BaseModel):
    kind: Literal["forget"]
    about: str | None = None


class DaySummary(BaseModel):
    kind: Literal["day_summary"]


class Calculate(BaseModel):
    kind: Literal["calculate"]
    expression: str


class Recall(BaseModel):
    kind: Literal["recall"]
    about: str | None = None


class EditDraft(BaseModel):
    kind: Literal["edit_draft"]
    instruction: str


class DraftQuestion(BaseModel):
    kind: Literal["draft_question"]
    question: str


class SendStatus(BaseModel):
    kind: Literal["send_status"]
    about: str | None = None


class DiscardDraft(BaseModel):
    kind: Literal["discard_draft"]


class FreeTime(BaseModel):
    kind: Literal["free_time"]
    date: OptionalDate
    end_date: OptionalDate
    start: Clock
    end: Clock


class ChatIntent(BaseModel):
    kind: Literal["chat"]


Intent = Annotated[
    SendEmail
    | EditDraft
    | DraftQuestion
    | SendStatus
    | DiscardDraft
    | FixLastAction
    | CreateEvent
    | UpdateEvent
    | CancelEvent
    | ReadCalendar
    | FreeTime
    | ReadEmail
    | WebSearch
    | Remind
    | Remember
    | CorrectMemory
    | Forget
    | DaySummary
    | Calculate
    | Recall
    | ChatIntent,
    Field(discriminator="kind"),
]


class Intents(BaseModel):
    intents: list[Intent]


def build_intent_agent(model: Model) -> Agent[None, Intents]:
    output = ToolOutput(
        Intents, name=OUTPUT_TOOL, description="Records every intent in the message."
    )
    return Agent(model, output_type=output, retries=2)


def context(history: list[ModelMessage]) -> str:
    """Earlier turns as quoted lines, so the model reads them as references, not as a script."""
    lines = []
    for message in history:
        speaker = "User" if isinstance(message, ModelRequest) else "Homer"
        for part in message.parts:
            text = " ".join(str(getattr(part, "content", "")).split())
            if text:
                lines.append(f"{speaker}: {text[:CONTEXT_CHARS]}")
    return "\n".join(lines) or "(none)"


@dataclass(frozen=True)
class Background:
    """What the intent call knows beyond the message: the previous turn's resolved intents,
    the user's remembered facts, how they write numeric dates, their timezone and the card
    waiting in this chat."""

    previous: list[dict[str, Any]] = field(default_factory=list)
    facts: list[str] = field(default_factory=list)
    date_format: DateFormat = "DD/MM"
    timezone: str = "UTC"
    pending: str = "nothing"


def single_day(intent: ReadCalendar, today: date) -> date | None:
    match intent.range:
        case "today":
            return today
        case "tomorrow":
            return today + timedelta(days=1)
        case "date" | "range" if intent.date and intent.end_date in (None, intent.date):
            return date.fromisoformat(intent.date)
    return None


def previous_day(previous: list[dict[str, Any]]) -> date | None:
    for item in previous:
        if item.get("date") and item.get("end_date") in (None, item["date"]):
            return date.fromisoformat(item["date"])
    return None


def agrees(given: str | None, expected: date, exact: bool) -> bool:
    if given is None:
        return True
    day = date.fromisoformat(given)
    return day == expected if exact else day.weekday() == expected.weekday()


def replacement(given: str, expected: date, exact: bool, today: date) -> str:
    """The exact date, or the day with the stated weekday nearest the model's own pick (never
    before today), so "no, I meant Friday" after a Wednesday next week lands on that week."""
    if exact:
        return expected.isoformat()
    day = date.fromisoformat(given)
    later = day + timedelta(days=(expected.weekday() - day.weekday()) % 7)
    earlier = later - timedelta(days=7)
    nearest = earlier if earlier >= today and day - earlier < later - day else later
    return nearest.isoformat()


def pin_dates(intent: Intent, expected: date, exact: bool, today: date) -> Intent:
    """Replaces a model date that contradicts the date code read from the message."""
    match intent:
        case ReadCalendar():
            day = single_day(intent, today)
            if day is not None and not agrees(day.isoformat(), expected, exact):
                fixed = replacement(day.isoformat(), expected, exact, today)
                return intent.model_copy(update={"range": "date", "date": fixed, "end_date": None})
        case CreateEvent() | Remind() | CancelEvent() if not agrees(intent.date, expected, exact):
            fixed = replacement(str(intent.date), expected, exact, today)
            return intent.model_copy(update={"date": fixed})
        case UpdateEvent() if not agrees(intent.new_date, expected, exact):
            fixed = replacement(str(intent.new_date), expected, exact, today)
            return intent.model_copy(update={"new_date": fixed})
    return intent


def as_free(intent: Intent) -> Intent:
    """A free-time question is a calendar read that answers yes or no first."""
    if not isinstance(intent, FreeTime):
        return intent
    span = "range" if intent.end_date not in (None, intent.date) else "date"
    return ReadCalendar(
        kind="read_calendar",
        range=span if intent.date else "today",
        date=intent.date,
        end_date=intent.end_date if span == "range" else None,
        start=intent.start,
        end=intent.end,
        asks_if="free",
    )


def as_move(intent: Intent, message: str) -> Intent:
    """A move verb never books a new event: the create the model read becomes an update."""
    if not isinstance(intent, CreateEvent) or not MOVE.search(message):
        return intent
    return UpdateEvent(
        kind="update_event",
        match=intent.title,
        new_date=intent.date,
        new_start=intent.start or intent.window_start,
        new_end=intent.end if intent.start else None,
        duration_minutes=intent.duration_minutes,
    )


def as_reply(intent: Intent, message: str) -> Intent:
    """ "Reply to Rosa" answers her latest email, so the subject keeps its "Re:"."""
    if isinstance(intent, SendEmail) and not intent.reply_to_latest_from and REPLY.match(message):
        return intent.model_copy(update={"reply_to_latest_from": intent.to})
    return intent


def named_title(message: str) -> str | None:
    """The event's name the message gives: "... for client intake", "call it Budget talk"."""
    found = TITLE_FOR.search(message)
    if found is None:
        return None
    title = found["title"].strip()
    return None if title.lower() in NOT_TITLES or len(title) < 3 else capitalised(title)


def titled(name: str | None, who: str | None) -> str:
    if name is None:
        return f"Meeting with {who}" if who else "Meeting"
    if who and who.split()[0].lower() not in name.lower():
        return f"{name} with {who}"
    return name


def as_slot(intent: Intent, message: str, today: date) -> Intent:
    """ "Find me 45 mins with Rosa between 2 and 5" books a free slot; it is not a question."""
    found = SLOT.search(message)
    if not isinstance(intent, ReadCalendar) or found is None:
        return intent
    day = single_day(intent, today) or weekday_date(message, today) or today
    minutes = None
    if found.group(1):
        minutes = int(found.group(1)) * (60 if found.group(2).lower().startswith("h") else 1)
    who = intent.person
    return CreateEvent(
        kind="create_event",
        title=titled(named_title(message), who),
        date=day.isoformat(),
        window_start=intent.start,
        window_end=intent.end,
        duration_minutes=minutes,
        attendees=[who] if who else [],
    )


def named(intent: Intent, message: str) -> Intent:
    """A new event the model called just "Meeting" takes the name the message gives it."""
    if not isinstance(intent, CreateEvent) or intent.title.strip().lower() not in GENERIC_TITLES:
        return intent
    name = named_title(message)
    if name is None:
        return intent
    who = intent.attendees[0] if len(intent.attendees) == 1 else None
    return intent.model_copy(update={"title": titled(name, who)})


def calendar_read(message: str, today: date) -> ReadCalendar:
    """The calendar read the message's own time words ask for: the next event, a weekday,
    tomorrow, next week, this week, else today."""
    day = weekday_date(message, today)
    lowered = message.lower()
    if NEXT_EVENT.search(message) and not DATED.search(message):
        return ReadCalendar(kind="read_calendar", range="next")
    if day is not None:
        return ReadCalendar(kind="read_calendar", range="date", date=day.isoformat())
    if "tomorrow" in lowered:
        return ReadCalendar(kind="read_calendar", range="tomorrow")
    if "next week" in lowered:
        return ReadCalendar(kind="read_calendar", range="next_week")
    if "this week" in lowered:
        return ReadCalendar(kind="read_calendar", range="this_week")
    return ReadCalendar(kind="read_calendar", range="today")


def as_calendar(intent: Intent, message: str, today: date) -> Intent:
    """ "What's on Thursday?" asks about the user's calendar, never the web."""
    if not isinstance(intent, WebSearch | ChatIntent) or not WHATS_ON.search(message):
        return intent
    return calendar_read(message, today)


def as_next(intent: Intent, message: str) -> Intent:
    """ "When's my next meeting?" asks for the next event, whatever range the model picked;
    "next" said of a week is next week."""
    if not isinstance(intent, ReadCalendar):
        return intent
    if NEXT_EVENT.search(message) and not DATED.search(message):
        return intent.model_copy(update={"range": "next", "days": None})
    if intent.range == "next" and NEXT_WEEK.search(message):
        return intent.model_copy(update={"range": "next_week"})
    return intent


def with_person(intent: Intent, message: str) -> Intent:
    """ "Anything with Sam this week?" is about Sam, also when the model left the name out."""
    if not isinstance(intent, ReadCalendar) or intent.person or intent.title_contains:
        return intent
    found = WITH_PERSON.search(message)
    if found is None or found.group(1).lower() in NOT_PEOPLE:
        return intent
    return intent.model_copy(update={"person": found.group(1)})


def span_minutes(start: str | None, end: str | None) -> int | None:
    if start is None or end is None or end <= start:
        return None
    (open_hour, open_minute), (close_hour, close_minute) = (
        map(int, start.split(":")),
        map(int, end.split(":")),
    )
    return (close_hour - open_hour) * 60 + close_minute - open_minute


def relative(intent: Intent, message: str) -> Intent:
    """ "In an hour" is counted by code from now, never by the model."""
    minutes = relative_minutes(message)
    if minutes is None or not isinstance(intent, CreateEvent | UpdateEvent):
        return intent
    if isinstance(intent, CreateEvent):
        length = intent.duration_minutes or span_minutes(intent.start, intent.end)
        update = {"relative_minutes": minutes, "duration_minutes": length, "start": None}
        return intent.model_copy(
            update=update | {"end": None, "window_start": None, "window_end": None}
        )
    return intent.model_copy(update={"relative_minutes": minutes, "new_start": None})


def timed(intent: Intent, message: str) -> Intent:
    """The one clock time the message names wins over the model's: "free monday 16 nov at
    2pm" is 14:00, and "move it to 11" moves it to 11:00."""
    times = stated_times(message)
    if len(times) != 1:
        return intent
    at = times[0]
    match intent:
        case ReadCalendar(asks_if=asked, end=None) if asked and intent.start != at:
            return intent.model_copy(update={"start": at})
        case UpdateEvent(new_end=None) if intent.new_start != at:
            return intent.model_copy(update={"new_start": at})
    return intent


def one_day(intent: Intent, message: str, today: date) -> Intent:
    """A question naming one weekday ("free next tuesday afternoon?") is about that day, not
    the coming fortnight."""
    day = weekday_date(message, today)
    if (
        not isinstance(intent, ReadCalendar)
        or day is None
        or intent.range not in ("next_n_days", "this_week", "next_week")
        or re.search(r"\bweeks?\b", message, re.IGNORECASE)
    ):
        return intent
    return intent.model_copy(update={"range": "date", "date": day.isoformat(), "end_date": None})


def unique(intents: list[Intent]) -> list[Intent]:
    kept: list[Intent] = []
    for intent in intents:
        if intent not in kept:
            kept.append(intent)
    return kept


def widened(intent: Intent, message: str) -> Intent:
    """A person or event named with no time is looked up over the coming two weeks."""
    if (
        isinstance(intent, ReadCalendar)
        and (intent.person or intent.title_contains)
        and intent.range in ("today", "date")
        and not DATED.search(message)
        and not WEEKDAY.search(message)
    ):
        return intent.model_copy(update={"range": "next_n_days", "days": SEARCH_DAYS})
    return intent


def repaired(intent: Intent, message: str, today: date) -> Intent:
    """Code's corrections of what the model tends to misread, in order."""
    intent = as_reply(as_move(as_free(intent), message), message)
    intent = named(as_calendar(as_slot(intent, message, today), message, today), message)
    intent = widened(with_person(intent, message), message)
    intent = timed(one_day(as_next(intent, message), message, today), message)
    return relative(intent, message)


def checked(intents: list[Intent], message: str, now: datetime, known: Background) -> list[Intent]:
    today = now.date()
    intents = unique([repaired(intent, message, today) for intent in intents])
    exact = numeric_date(message, today, known.date_format)
    if exact is None and (after := previous_day(known.previous)) and DAY_AFTER.search(message):
        exact = after + timedelta(days=1)
    expected = exact or weekday_date(message, today)
    if expected is None:
        return intents
    fixed = [pin_dates(intent, expected, exact is not None, today) for intent in intents]
    if fixed != intents:
        log.info("intent_dates_pinned", message=message, date=expected.isoformat())
    return fixed


def shown_previous(previous: list[dict[str, Any]]) -> str:
    return "; ".join(json.dumps(item, sort_keys=True) for item in previous) or "(none)"


def shown_facts(facts: list[str]) -> str:
    return "\n".join(f"- {fact}" for fact in facts) or "(none)"


@cache
def instructions() -> str:
    return INSTRUCTIONS.format(examples=EXAMPLES.read_text().strip())


def prompt(message: str, history: list[ModelMessage], now: datetime, known: Background) -> str:
    return CONTEXT.format(
        now=now_line(now),
        dates=date_table(now),
        timezone=known.timezone,
        pending=known.pending,
        previous=shown_previous(known.previous),
        facts=shown_facts(known.facts),
        context=context(history),
        message=message,
        numeric=numeric_hint(message, now.date(), known.date_format),
    )


async def prime(agent: Agent[None, Intents]) -> None:
    """One throwaway intent call, so Ollama has the static prefix cached before the first real
    message; a failure is logged, never raised."""
    try:
        await agent.run("hello", instructions=instructions())
    except Exception as error:
        log.warning("intent_prime_failed", error=str(error))


async def extract(
    agent: Agent[None, Intents],
    message: str,
    history: list[ModelMessage],
    now: datetime,
    known: Background | None = None,
) -> tuple[list[Intent], RunUsage]:
    """One structured call: the static instructions and examples first, so Ollama reuses
    their cached prefix, then this turn's context and message. A model that cannot produce
    valid intents falls back to chat. Dates code can read from the message itself override
    the model's."""
    known = known or Background()
    started = time.monotonic()
    try:
        result = await agent.run(prompt(message, history, now, known), instructions=instructions())
    except UnexpectedModelBehavior:
        log.warning("intents_failed", message=message)
        return [ChatIntent(kind="chat")], RunUsage()
    log.info("intent_call", seconds=round(time.monotonic() - started, 2))
    intents = result.output.intents or [ChatIntent(kind="chat")]
    return checked(intents, message, now, known), result.usage
