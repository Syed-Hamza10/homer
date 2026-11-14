import json
import re
from datetime import UTC
from email.utils import getaddresses
from typing import Any
from zoneinfo import ZoneInfo

import structlog

from homer_core.agent.intents import ChatIntent, Intent, Recall, SendStatus
from homer_core.db.models import Approval
from homer_core.services import approvals
from homer_core.services.facts import closest, keywords
from homer_core.services.jobs import recipients
from homer_core.services.jobs.turn import JobError, ReconnectRequired, Turn

log = structlog.get_logger(__name__)

NOTHING_SENT = "No. Nothing has been sent from this chat."
STATUS = {
    "pending": "Not yet. The draft to {to} is waiting for you to press Send.",
    "running": "It is being sent to {to} right now.",
    "rejected": "No. You discarded the draft to {to}.",
    "expired": "No. The draft to {to} expired before it was sent.",
    "failed": "No. Sending to {to} failed.",
    "unknown": "I am not sure. Sending to {to} timed out, so check your Sent folder.",
}
SEND_WORD = re.compile(
    r"\b(?:sent|send|sending|went|gone|go(?:es)? out|deliver(?:ed|y)?|receive[ds]?|got it)\b",
    re.IGNORECASE,
)
NOT_NAMES = frozenset(
    {"it", "that", "this", "them", "him", "her", "the email", "the mail", "the message"}
    | {"email", "mail", "message", "the draft", "draft", "the reply", "reply"}
)
SENT_DAYS = 7
NAMED_IN = re.compile(
    r"\b(?:to|for)\s+(?!(?:it|him|her|them|me|you|us|the|my|a|an|that|this)\b)"
    r"(?P<to>[\w.+-]+@[\w.-]+|[A-Za-z][\w'-]+)"
    r"|\bthe\s+(?P<the>(?-i:[A-Z])[\w'-]+?)(?:'s)?\s+(?:reply|e-?mail|mail|message|draft)\b",
    re.IGNORECASE,
)
NOT_WHO = frozenset({"now", "sure", "real", "today", "yesterday", "tomorrow", "send", "go"})


def sent_at(turn: Turn, approval: Approval) -> str:
    if approval.decided_at is None:
        return ""
    decided = approval.decided_at.replace(tzinfo=approval.decided_at.tzinfo or UTC)
    local = decided.astimezone(ZoneInfo(turn.user.timezone))
    shown = f"{local:%H:%M}" if local.date() == turn.now.date() else f"{local:%a %d %b, %H:%M}"
    return f" at {shown}"


def describe(turn: Turn, approval: Approval) -> str:
    to = json.loads(approval.payload_json).get("to", "")
    if approval.status == "done":
        return f"Yes, sent to {to}{sent_at(turn, approval)}."
    return STATUS.get(approval.status, STATUS["pending"]).format(to=to)


def named(about: str | None) -> str:
    """The person asked about; "it", "that" and "the email" name no one."""
    text = (about or "").strip()
    return "" if text.lower() in NOT_NAMES else text


def asked_send(turn: Turn, about: str | None) -> Approval | None:
    """The newest email to the person named, from any chat; with no one named, this chat's
    newest email."""
    who = named(about).lower()
    if not who:
        return approvals.latest_send(turn.session, turn.user, turn.conversation_id, None)
    for word in [who, *(word for word in keywords(who) if len(word) > 2)]:
        found = approvals.latest_send(turn.session, turn.user, None, word)
        if found is not None:
            return found
    return None


def recipient(approval: Approval | None, about: str) -> str:
    if approval is not None:
        return str(json.loads(approval.payload_json).get("to", ""))
    return about


async def in_sent(turn: Turn, to: str) -> dict[str, Any] | None:
    """The newest message in the Sent folder to `to` from the last week, None when there is
    none or Gmail cannot say."""
    word = to if "@" in to else to.split()[0]
    args = {"query": f"in:sent to:{word} newer_than:{SENT_DAYS}d", "max_results": 1}
    try:
        found = recipients.listed(await turn.call("google", "mail_search", args), "messages")
    except ReconnectRequired:
        raise
    except JobError:
        return None
    return found[0] if found else None


def went_out(turn: Turn, message: dict[str, Any], to: str) -> str:
    people = [name or email for name, email in getaddresses([message.get("to", "")])]
    shown = people[0] if people else to
    moment = recipients.sent_at(message)
    when = f" {recipients.ago(moment, turn.now)}" if moment else ""
    subject = str(message.get("subject", "")).strip()
    about = f': "{subject}"' if subject else ""
    return f"Yes, an email to {shown} went out{when}{about}."


async def answer(turn: Turn, about: str | None = None) -> str:
    """Says whether the email asked about went out: from the approvals in this chat (or to
    the person named), checked against the Sent folder before ever saying no."""
    found = asked_send(turn, about)
    if found is not None and found.status in ("done", "pending", "running"):
        return describe(turn, found)
    to = recipient(found, named(about))
    sent = await in_sent(turn, to) if to else None
    if sent is not None:
        return went_out(turn, sent, to)
    if found is not None:
        return describe(turn, found)
    return f"No. I have not sent anything to {about}." if named(about) else NOTHING_SENT


def named_in(message: str) -> str:
    """The person the message itself names: "did you send my email to Priya?", "has the Rosa
    reply gone out?"."""
    for found in NAMED_IN.finditer(message):
        who = found["to"] or found["the"]
        if who.lower() not in NOT_WHO:
            return who
    return ""


async def status(turn: Turn, intent: SendStatus) -> None:
    turn.say(await answer(turn, named(intent.about) or named_in(turn.message) or None))


def rerouted(turn: Turn, intent: SendStatus) -> Intent:
    """A mail-status answer only for a message about sending: "pharmacist closing time, one
    line" asks about a saved fact, or goes on with the chat."""
    if SEND_WORD.search(turn.message):
        return intent
    log.info("send_status_rerouted", message=turn.message)
    if closest(turn.session, turn.user, turn.message):
        return Recall(kind="recall", about=turn.message)
    return ChatIntent(kind="chat")


def honest(turn: Turn) -> str | None:
    """The truth about this chat's latest email, said instead of an unbacked claim."""
    found = approvals.latest_send(turn.session, turn.user, turn.conversation_id, None)
    if found is None or found.status != "pending":
        return None
    to = json.loads(found.payload_json).get("to", "")
    return f"I have not sent it. The draft to {to} is waiting for you to press Send."
