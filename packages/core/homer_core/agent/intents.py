import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
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
    WEEKDAY,
    WEEKDAY_WORDS,
    DateFormat,
    date_table,
    numeric_date,
    numeric_hint,
    weekday_date,
)

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
NEXT_EVENT = re.compile(r"\b(?:next|upcoming) (?:meeting|event|call|appointment)\b", re.IGNORECASE)
SLOT = re.compile(
    r"\bfind (?:me |us )?(?:a |an )?"
    r"(?:(\d+)\s*(?:-\s*)?(min|mins|minutes|minute|h|hr|hrs|hour|hours)"
    r"|time|slot|free slot)\b",
    re.IGNORECASE,
)
WHATS_ON = re.compile(
    r"^\W*(?:\w+[,!.]?\s+){0,4}?(?:what(?:'s|s| is)|anything)\s+(?:on|planned|happening|the plan)"
    r"\b(?:\s+(?:for|on))?\s+(?:today|tonight|tomorrow|this \w+|next \w+|"
    + "|".join(WEEKDAY_WORDS)
    + r")\b",
    re.IGNORECASE,
)

PROMPT = """You turn the user's latest message into a list of intents for Homer, an email,
calendar and web assistant. Do not answer the message: call record_intents once with every
intent.
Dates. Copy them from this table, never calculate one. A weekday name ("wed", "Friday",
"next Wednesday") is the first day in the table with that name after today, or today itself
when today has that name and the user did not say "next".
{dates}{numeric}
Intents:
- send_email: write, send, email or reply to someone. `to` is the name or address as written.
  `body_instructions` is what the email should say. Set `reply_to_latest_from` only when the
  user asks to reply to someone's email.
- create_event: schedule, book or add a NEW meeting or event. Use start/end for an exact time
  ("at 3pm", "from 2 to 3"). Use window_start/window_end when the user wants a free slot inside
  a range ("between 9 and 11", "sometime in the morning"). attendees are every person the
  meeting is with, as names or addresses.
- update_event: move, reschedule, push, shift, rename or change the time of an EXISTING event,
  including one booked earlier in this chat. `match` is how the user names it ("design review",
  "lunch with Sam", "Monday call with Elena"), or "it" for "it", "that" or "the call we just
  booked". `date` only when they say which day it is on NOW ("my Monday call"); never put the
  new day there. Fill only what changes: new_date, new_start, new_end, new_title, and
  duration_minutes only when they state a new length.
- cancel_event: cancel, delete or remove an existing event. `match` names it as above.
- read_calendar: questions about the user's calendar, schedule, meetings or free time.
  range: today, tomorrow, this_week, next_week, this_weekend, next_n_days (with `days`),
  date (one day in `date`) or range (`date` to `end_date`). `person` when the user asks about
  events with someone; `title_contains` when they name an event. When a person or event is
  named with no time, use next_n_days with days 14. start/end narrow the time of day (morning
  09:00-12:00, afternoon 12:00-17:00, evening 17:00-21:00, "at 1:30pm" is start 13:30).
  asks_if is "free" or "busy" when the user asks whether they are free or busy.
- read_email: questions about email the user received. Use `sender` for a person, `query` for
  a topic, `latest` for the newest email. `question` is what the user wants to know.
- web_search: news, current events, prices, weather, sports, anything about today or that
  needs the internet. Never for questions about the user themself.
- remind: the user asks to be reminded of something.
- remember: the user tells you a fact to remember ("my dog is Biscuit, remember that").
  `fact` is one short sentence about the user, such as "The user's dog is called Biscuit."
- forget: the user asks you to forget something. `about` names it, or stays empty for
  "forget that".
- day_summary: what the user got done, sent or booked today, what is still open, pending or
  waiting on them.
- chat: anything else: greetings, thanks, questions about the user (answer them from the
  facts below), about you or about this conversation, and general knowledge.
A message with several requests gives several intents, in the order asked.
Follow-ups. The previous request is shown below with its resolved dates. A short follow-up
("and the day after?", "what about Monday?", "what about Rosa?", "anything with her?")
repeats its kind and changes only what the message changes; "the day after" is the day after
the previous date. A correction ("no, I meant Friday", "make it 4pm") repeats the previous
request with the corrected field and keeps everything else.
Previous request: {previous}
Facts the user asked you to remember:
{facts}
Classify only the latest message. Earlier turns, quoted below, only tell you who or what it
refers to ("him", "that email"); never repeat an earlier request unless it is a follow-up.
Earlier turns:
{context}"""


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
    attendees: list[str] = Field(default_factory=list)


class UpdateEvent(BaseModel):
    kind: Literal["update_event"]
    match: str
    date: OptionalDate
    new_date: OptionalDate
    new_start: Clock
    new_end: Clock
    new_title: str | None = None
    duration_minutes: int | None = None


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


class Remind(BaseModel):
    kind: Literal["remind"]
    text: str
    date: IsoDate
    time: Clock


class Remember(BaseModel):
    kind: Literal["remember"]
    fact: str


class Forget(BaseModel):
    kind: Literal["forget"]
    about: str | None = None


class DaySummary(BaseModel):
    kind: Literal["day_summary"]


class ChatIntent(BaseModel):
    kind: Literal["chat"]


Intent = Annotated[
    SendEmail
    | CreateEvent
    | UpdateEvent
    | CancelEvent
    | ReadCalendar
    | ReadEmail
    | WebSearch
    | Remind
    | Remember
    | Forget
    | DaySummary
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
    the user's remembered facts and how they write numeric dates."""

    previous: list[dict[str, Any]] = field(default_factory=list)
    facts: list[str] = field(default_factory=list)
    date_format: DateFormat = "DD/MM"


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
        title=f"Meeting with {who}" if who else "Meeting",
        date=day.isoformat(),
        window_start=intent.start,
        window_end=intent.end,
        duration_minutes=minutes,
        attendees=[who] if who else [],
    )


def as_calendar(intent: Intent, message: str, today: date) -> Intent:
    """ "What's on Thursday?" asks about the user's calendar, never the web."""
    if not isinstance(intent, WebSearch | ChatIntent) or not WHATS_ON.search(message):
        return intent
    day = weekday_date(message, today)
    if day is not None:
        return ReadCalendar(kind="read_calendar", range="date", date=day.isoformat())
    lowered = message.lower()
    if "tomorrow" in lowered:
        return ReadCalendar(kind="read_calendar", range="tomorrow")
    if "next week" in lowered:
        return ReadCalendar(kind="read_calendar", range="next_week")
    if "this week" in lowered:
        return ReadCalendar(kind="read_calendar", range="this_week")
    return ReadCalendar(kind="read_calendar", range="today")


def as_next(intent: Intent, message: str) -> Intent:
    """ "When's my next meeting?" looks two weeks ahead, whatever range the model picked."""
    if (
        isinstance(intent, ReadCalendar)
        and NEXT_EVENT.search(message)
        and not DATED.search(message)
    ):
        return intent.model_copy(update={"range": "next_n_days", "days": SEARCH_DAYS})
    return intent


def one_day(intent: Intent, message: str, today: date) -> Intent:
    """A question naming one weekday ("free next tuesday afternoon?") is about that day, not
    the coming fortnight."""
    day = weekday_date(message, today)
    if (
        not isinstance(intent, ReadCalendar)
        or day is None
        or intent.range != "next_n_days"
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
    intent = as_reply(as_move(intent, message), message)
    intent = as_calendar(as_slot(intent, message, today), message, today)
    return one_day(as_next(widened(intent, message), message), message, today)


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


async def extract(
    agent: Agent[None, Intents],
    message: str,
    history: list[ModelMessage],
    now: datetime,
    known: Background | None = None,
) -> tuple[list[Intent], RunUsage]:
    """One structured call; a model that cannot produce valid intents falls back to chat.
    Dates code can read from the message itself override the model's."""
    known = known or Background()
    instructions = PROMPT.format(
        dates=date_table(now),
        numeric=numeric_hint(message, now.date(), known.date_format),
        previous=shown_previous(known.previous),
        facts=shown_facts(known.facts),
        context=context(history),
    )
    try:
        result = await agent.run(message, instructions=instructions)
    except UnexpectedModelBehavior:
        log.warning("intents_failed", message=message)
        return [ChatIntent(kind="chat")], RunUsage()
    intents = result.output.intents or [ChatIntent(kind="chat")]
    return checked(intents, message, now, known), result.usage
