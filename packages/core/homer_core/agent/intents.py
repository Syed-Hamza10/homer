import re
from datetime import date, datetime, timedelta
from typing import Annotated, Literal

import structlog
from pydantic import BaseModel, BeforeValidator, Field
from pydantic_ai import Agent, ToolOutput
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models import Model
from pydantic_ai.usage import RunUsage

log = structlog.get_logger(__name__)

DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIME = re.compile(r"^\s*(\d{1,2})(?:[:.](\d{2}))?\s*([ap]\.?m\.?)?\s*$", re.IGNORECASE)
WEEK_DAYS = 7
OUTPUT_TOOL = "record_intents"

PROMPT = """You turn the user's latest message into a list of intents for Homer, an email,
calendar and web assistant. Do not answer the message: call record_intents once with every
intent.
Dates. Copy them from this list, never calculate one:
{dates}
Intents:
- send_email: write, send, email or reply to someone. `to` is the name or address as written.
  `body_instructions` is what the email should say. Set `reply_to_latest_from` only when the
  user asks to reply to someone's email.
- create_event: schedule, book or add a meeting or event. Use start/end for an exact time
  ("at 3pm", "from 2 to 3"). Use window_start/window_end when the user wants a free slot inside
  a range ("between 9 and 11", "sometime in the morning"). attendees are every person the
  meeting is with, as names or addresses.
- read_calendar: questions about the user's calendar, schedule or meetings.
- read_email: questions about email the user received. Use `sender` for a person, `query` for
  a topic, `latest` for the newest email. `question` is what the user wants to know.
- web_search: news, current events, prices, weather, sports, anything about today or that
  needs the internet.
- remind: the user asks to be reminded of something.
- chat: anything else, including greetings and general questions.
A message with several requests gives several intents, in the order asked.
Earlier turns are context: use them to fill in who or what the latest message refers to."""


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


class ReadCalendar(BaseModel):
    kind: Literal["read_calendar"]
    range: Literal["today", "tomorrow", "this_week", "date", "range"]
    date: OptionalDate
    end_date: OptionalDate


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


class ChatIntent(BaseModel):
    kind: Literal["chat"]


Intent = Annotated[
    SendEmail | CreateEvent | ReadCalendar | ReadEmail | WebSearch | Remind | ChatIntent,
    Field(discriminator="kind"),
]


class Intents(BaseModel):
    intents: list[Intent]


def describe(day: date) -> str:
    return f"{day:%A} {day.isoformat()}"


def date_table(now: datetime) -> str:
    today = now.date()
    monday = today - timedelta(days=today.weekday())
    lines = [f"today: {describe(today)}", f"tomorrow: {describe(today + timedelta(days=1))}"]
    lines += [describe(today + timedelta(days=n)) for n in range(2, WEEK_DAYS + 1)]
    lines.append(f"this week: {monday.isoformat()} to {(monday + timedelta(days=6)).isoformat()}")
    return "\n".join(lines)


def build_intent_agent(model: Model) -> Agent[None, Intents]:
    output = ToolOutput(
        Intents, name=OUTPUT_TOOL, description="Records every intent in the message."
    )
    return Agent(model, output_type=output, retries=2)


async def extract(
    agent: Agent[None, Intents], message: str, history: list[ModelMessage], now: datetime
) -> tuple[list[Intent], RunUsage]:
    """One structured call; a model that cannot produce valid intents falls back to chat."""
    try:
        result = await agent.run(
            message, message_history=history, instructions=PROMPT.format(dates=date_table(now))
        )
    except UnexpectedModelBehavior:
        log.warning("intents_failed", message=message)
        return [ChatIntent(kind="chat")], RunUsage()
    return result.output.intents or [ChatIntent(kind="chat")], result.usage
