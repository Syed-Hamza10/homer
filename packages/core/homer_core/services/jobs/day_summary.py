import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, time
from email.utils import parseaddr, parsedate_to_datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlmodel import select

from homer_core.db.models import Approval
from homer_core.mcp.manager import PROFILE_TOOL
from homer_core.services import approvals
from homer_core.services.jobs.read_calendar import bounds
from homer_core.services.jobs.recipients import listed
from homer_core.services.jobs.turn import Turn

SENT_QUERY = "in:sent newer_than:7d"
INBOX_QUERY = "in:inbox newer_than:7d"
MAX_MESSAGES = 25
MAX_ITEMS = 6
AUTOMATED = re.compile(
    r"no-?reply|do-?not-?reply|newsletter|notifications?@|mailer|digest|marketing|billing@"
    r"|updates@|news@|info@",
    re.IGNORECASE,
)
BULK = frozenset(
    {"CATEGORY_PROMOTIONS", "CATEGORY_SOCIAL", "CATEGORY_UPDATES", "CATEGORY_FORUMS", "SPAM"}
)
NO_RECORD = re.compile(
    r"\bno record\b|\b(?:haven't|have not|didn't|did not) sen[dt]\b"
    r"|\bno emails? (?:were |was )?sent\b"
    r"|\bnothing (?:was )?sent\b",
    re.IGNORECASE,
)
NOTHING = "Nothing sent or booked today, and nothing is waiting on you."
PROMPT = """You are Homer. Write the person's end-of-day summary, talking to them as "you", from
the facts below and nothing else. Use two headings, "Done today" and "Still open", with one short
bullet per fact, keeping names, subjects and times as given. When a heading has no facts, say so
in a few words. Under 120 words. Never mention "the facts", "the data" or "the user".
{facts}"""


@dataclass
class Day:
    sent: list[str] = field(default_factory=list)
    calendar: list[str] = field(default_factory=list)
    pending: list[str] = field(default_factory=list)
    waiting: list[str] = field(default_factory=list)

    @property
    def done(self) -> list[str]:
        return self.sent + self.calendar

    @property
    def open(self) -> list[str]:
        return self.pending + self.waiting


def received(message: dict[str, Any]) -> datetime | None:
    stamp = (message.get("metadata") or {}).get("internal_date")
    if stamp:
        return datetime.fromtimestamp(int(stamp) / 1000, tz=UTC)
    try:
        parsed = parsedate_to_datetime(str(message.get("date", "")))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def who(header: str) -> str:
    name, email = parseaddr(header)
    return name or email or header


def address(header: str) -> str:
    return parseaddr(header)[1].lower()


def decided(approval: Approval) -> datetime:
    stamp = approval.decided_at or approval.created_at
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=UTC)


def clock(moment: datetime, zone: ZoneInfo) -> str:
    return f"{moment.astimezone(zone):%H:%M}"


def sent_today(
    turn: Turn, sent: list[dict[str, Any]], done: list[Approval], midnight: datetime
) -> list[str]:
    """Gmail's Sent folder for today, plus emails sent through Homer that it does not show."""
    zone = ZoneInfo(turn.user.timezone)
    seen: set[tuple[str, str]] = set()
    lines = []
    for message in sent:
        at = received(message)
        if at is None or at < midnight:
            continue
        seen.add((address(message.get("to", "")), str(message.get("subject", ""))))
        lines.append(
            f'Sent to {who(message.get("to", ""))}: "{message.get("subject", "")}" '
            f"at {clock(at, zone)}"
        )
    for approval in done:
        if approval.action != approvals.SEND_ACTION:
            continue
        payload = json.loads(approval.payload_json)
        if (payload.get("to", "").lower(), payload.get("subject", "")) in seen:
            continue
        lines.append(
            f'Sent to {payload.get("to", "")}: "{payload.get("subject", "")}" '
            f"at {clock(decided(approval), zone)}"
        )
    return lines


def calendar_today(turn: Turn, done: list[Approval]) -> list[str]:
    zone = ZoneInfo(turn.user.timezone)
    lines = []
    for approval in done:
        payload = json.loads(approval.payload_json)
        if approval.action == "cal_create":
            opens, closes = bounds(json.loads(approval.result_json or "{}") or payload, zone)
            when = f"{opens:%a %d %b} {opens:%H:%M}-{closes:%H:%M}"
            lines.append(f"Booked '{payload.get('title', '')}' for {when}")
        elif approval.action in ("cal_update", "cal_delete"):
            lines.append(approval.preview.splitlines()[0])
    return lines


def waiting_card(approval: Approval) -> str:
    payload = json.loads(approval.payload_json)
    if approval.action == approvals.SEND_ACTION:
        return f'Draft to {payload.get("to", "")} "{payload.get("subject", "")}" waits for Send'
    if approval.action == "cal_create":
        return f"Event '{payload.get('title', '')}' waits for Create"
    return f"{approval.preview.splitlines()[0]} waits for Approve"


def awaiting_reply(
    turn: Turn, inbox: list[dict[str, Any]], sent: list[dict[str, Any]], me: str
) -> list[str]:
    """Threads whose newest message is from someone else, a person rather than a mailer, and
    that the user has not answered since; priority contacts and important mail first."""
    answered: dict[str, datetime] = {}
    for message in sent:
        at = received(message)
        thread = str(message.get("thread_id", ""))
        if at is not None and at > answered.get(thread, datetime.min.replace(tzinfo=UTC)):
            answered[thread] = at
    newest: dict[str, dict[str, Any]] = {}
    for message in inbox:
        thread = str(message.get("thread_id", ""))
        at = received(message) or datetime.min.replace(tzinfo=UTC)
        if thread not in newest or at > (received(newest[thread]) or at):
            newest[thread] = message
    priority = {contact.lower() for contact in turn.rules.priority_contacts}
    found = []
    for thread, message in newest.items():
        sender = address(message.get("from", ""))
        at = received(message) or datetime.min.replace(tzinfo=UTC)
        if not sender or sender == me or AUTOMATED.search(sender):
            continue
        if BULK & set(message.get("labels", [])) or answered.get(thread, at) > at:
            continue
        rank = (sender in priority or "IMPORTANT" in message.get("labels", []), at)
        found.append((rank, message))
    found.sort(key=lambda pair: pair[0], reverse=True)
    zone = ZoneInfo(turn.user.timezone)
    return [
        f'{who(m.get("from", ""))} is waiting on your reply: "{m.get("subject", "")}" '
        f"({(received(m) or turn.now).astimezone(zone):%a %d %b})"
        for _, m in found[:MAX_ITEMS]
    ]


def done_today(turn: Turn, midnight: datetime) -> list[Approval]:
    statement = (
        select(Approval)
        .where(Approval.user_id == turn.user.id, Approval.status == "done")
        .order_by(Approval.id)
    )
    return [a for a in turn.session.exec(statement) if decided(a) >= midnight]


async def messages(turn: Turn, query: str) -> list[dict[str, Any]]:
    args = {"query": query, "max_results": MAX_MESSAGES}
    return listed(await turn.call("google", "mail_search", args), "messages")


async def gather(turn: Turn) -> Day:
    zone = ZoneInfo(turn.user.timezone)
    midnight = datetime.combine(turn.now.date(), time.min, zone).astimezone(UTC)
    profile = await turn.call("google", PROFILE_TOOL, {})
    me = str(profile.get("email", "")).lower() if isinstance(profile, dict) else ""
    sent = await messages(turn, SENT_QUERY)
    inbox = await messages(turn, INBOX_QUERY)
    done = done_today(turn, midnight)
    return Day(
        sent=sent_today(turn, sent, done, midnight)[:MAX_ITEMS],
        calendar=calendar_today(turn, done)[:MAX_ITEMS],
        pending=[waiting_card(a) for a in approvals.list_pending(turn.session, turn.user)][
            :MAX_ITEMS
        ],
        waiting=awaiting_reply(turn, inbox, sent, me),
    )


def listing(day: Day) -> str:
    done = "\n".join(f"- {line}" for line in day.done) or "- Nothing sent or booked yet."
    still = "\n".join(f"- {line}" for line in day.open) or "- Nothing is waiting on you."
    return f"Done today:\n{done}\n\nStill open:\n{still}"


async def run(turn: Turn, intent: Any = None) -> None:
    day = await gather(turn)
    if not day.done and not day.open:
        turn.say(NOTHING)
        return
    index = await turn.stream(turn.message, PROMPT.format(facts=listing(day)), guarded=False)
    if day.sent and NO_RECORD.search(turn.segments[index]):
        turn.replace(index, listing(day))
