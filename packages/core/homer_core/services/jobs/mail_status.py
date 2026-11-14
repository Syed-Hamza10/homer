import json
from datetime import UTC
from zoneinfo import ZoneInfo

from homer_core.agent.intents import SendStatus
from homer_core.db.models import Approval
from homer_core.services import approvals
from homer_core.services.facts import keywords
from homer_core.services.jobs.turn import Turn

NOTHING_SENT = "No. Nothing has been sent from this chat."
STATUS = {
    "pending": "Not yet. The draft to {to} is waiting for you to press Send.",
    "running": "It is being sent to {to} right now.",
    "rejected": "No. You discarded the draft to {to}.",
    "expired": "No. The draft to {to} expired before it was sent.",
    "failed": "No. Sending to {to} failed.",
    "unknown": "I am not sure. Sending to {to} timed out, so check your Sent folder.",
}


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


def asked_send(turn: Turn, about: str | None) -> Approval | None:
    """The newest email to the person named, from any chat; with no one named, this chat's
    newest email."""
    named = (about or "").strip().lower()
    if not named:
        return approvals.latest_send(turn.session, turn.user, turn.conversation_id, None)
    for who in [named, *(word for word in keywords(named) if len(word) > 2)]:
        found = approvals.latest_send(turn.session, turn.user, None, who)
        if found is not None:
            return found
    return None


def answer(turn: Turn, about: str | None = None) -> str:
    """Says from the approvals table whether the email asked about went out."""
    found = asked_send(turn, about)
    if found is not None:
        return describe(turn, found)
    return f"No. I have not sent anything to {about}." if about else NOTHING_SENT


async def status(turn: Turn, intent: SendStatus) -> None:
    turn.say(answer(turn, intent.about))


def honest(turn: Turn) -> str | None:
    """The truth about this chat's latest email, said instead of an unbacked claim."""
    found = approvals.latest_send(turn.session, turn.user, turn.conversation_id, None)
    if found is None or found.status != "pending":
        return None
    to = json.loads(found.payload_json).get("to", "")
    return f"I have not sent it. The draft to {to} is waiting for you to press Send."
