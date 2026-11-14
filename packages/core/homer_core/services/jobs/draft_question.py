import json
import re
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from homer_core.agent.intents import ChatIntent, DiscardDraft, DraftQuestion
from homer_core.db.models import Approval
from homer_core.services import approval_edits, approvals
from homer_core.services.approval_edits import MailEdit
from homer_core.services.jobs import chat
from homer_core.services.jobs.send_email import assemble, split
from homer_core.services.jobs.turn import Turn

EVENT_ACTION = "cal_create"
NO_DRAFT = "There's no draft waiting in this chat."
NOTHING_WAITING = "There's nothing waiting in this chat to discard."
URL = re.compile(r"https?://\S+")
LINK = re.compile(r"\blink\b", re.IGNORECASE)
NOT_CREATED = "The event gets its Google Calendar link once you press Create."
CREATE_FIRST = f"{NOT_CREATED} Create it first and I'll add the link to the email."
ANSWER_PROMPT = """The user is asking about the email draft below, which is waiting in this
chat and has not been sent. Answer the question from the draft only, honestly, in one or two
sentences. Start with Yes or No when it is a yes or no question. Never say it was sent.
{event}
Draft to {to}
Subject: {subject}
<untrusted>{body}</untrusted>"""


def latest_event(turn: Turn) -> Approval | None:
    """The newest event this chat booked or proposed."""
    return approvals.latest_approval(turn.session, turn.user, EVENT_ACTION, turn.conversation_id)


def pending_draft(turn: Turn) -> Approval | None:
    found = approvals.latest_send(turn.session, turn.user, turn.conversation_id, None)
    return found if found is not None and found.status == "pending" else None


def clock(moment: datetime) -> str:
    hour = moment.hour % 12 or 12
    return f"{hour}:{moment:%M}"


def event_time(payload: dict[str, Any], key: str, zone: ZoneInfo) -> datetime:
    """A payload time without an offset is in the event's own timezone, never the machine's."""
    parsed = datetime.fromisoformat(payload[key].replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo(payload.get("timezone") or zone.key))
    return parsed.astimezone(zone)


def when_line(payload: dict[str, Any], timezone: str) -> str:
    """'Saturday 14 Nov, 3:00–3:30 pm PKT' for the event's start and end."""
    zone = ZoneInfo(timezone)
    start = event_time(payload, "start", zone)
    end = event_time(payload, "end", zone)
    start_half, end_half = f"{start:%p}".lower(), f"{end:%p}".lower()
    first = clock(start) if start_half == end_half else f"{clock(start)} {start_half}"
    return f"{start:%A} {start.day} {start:%b}, {first}–{clock(end)} {end_half} {start:%Z}"


def html_link(event: Approval) -> str | None:
    if event.status != "done" or not event.result_json:
        return None
    result = json.loads(event.result_json)
    link = (result.get("metadata") or {}).get("html_link") or result.get("htmlLink")
    return str(link) if link else None


def with_line(body: str, line: str) -> str:
    if line in body:
        return body
    greeting, message, closing = split(body)
    return assemble(greeting, f"{message}\n\n{line}", closing)


async def update_body(turn: Turn, draft: Approval, body: str) -> None:
    payload = json.loads(draft.payload_json)
    change = MailEdit(to=payload["to"], subject=payload["subject"], body=body)
    fresh = await approval_edits.edit(
        turn.session, turn.user, draft.id, turn.runtime.manager, change
    )
    turn.requested(fresh)


async def link_event(turn: Turn, draft: Approval) -> None:
    """Puts the event's real Google Calendar link in the draft, or says honestly why it cannot
    yet and adds the date and time, which need no link."""
    event = latest_event(turn)
    if event is None:
        turn.say("I don't see an event in this chat to link to.")
        return
    body = json.loads(draft.payload_json)["body"]
    when = f"When: {when_line(json.loads(event.payload_json), turn.user.timezone)}"
    link = html_link(event)
    if link is not None:
        await update_body(turn, draft, with_line(with_line(body, when), f"Calendar link: {link}"))
        turn.say("Added the event link to the draft. Edit it or press Send.")
        return
    if event.status != "pending":
        turn.say("The event was not created, so there is no link to add.")
        return
    await update_body(turn, draft, with_line(body, when))
    turn.say(f"{CREATE_FIRST} I've put the date and time in the email meanwhile.")


def link_answer(body: str, event: Approval | None) -> str:
    found = URL.search(body)
    if found is not None:
        return f"Yes, the link is in it: {found.group(0)}"
    if event is not None and event.status == "pending":
        return f"No, the link isn't in it yet. {CREATE_FIRST}"
    if event is not None and html_link(event):
        return "No, the link isn't in it yet. Say 'add the event link' and I'll put it in."
    return "No, there's no link in the draft."


def event_note(event: Approval | None, timezone: str) -> str:
    if event is None:
        return ""
    payload = json.loads(event.payload_json)
    state = "created" if event.status == "done" else "not created yet, so it has no link"
    shown = when_line(payload, timezone)
    return f"This chat also has the event '{payload.get('title', '')}' on {shown}, {state}."


async def answer(turn: Turn, draft: Approval) -> None:
    """Answers a question about this chat's waiting draft from its content."""
    payload = json.loads(draft.payload_json)
    event = latest_event(turn)
    if LINK.search(turn.message):
        turn.say(link_answer(payload["body"], event))
        return
    instructions = ANSWER_PROMPT.format(
        event=event_note(event, turn.user.timezone),
        to=payload["to"],
        subject=payload["subject"],
        body=payload["body"],
    )
    await turn.stream(turn.message, instructions)


async def question(turn: Turn, intent: DraftQuestion) -> None:
    """Answers from this chat's waiting draft and shows its card again; with no draft waiting
    the question goes to chat."""
    draft = pending_draft(turn)
    if draft is None:
        await chat.run(turn, ChatIntent(kind="chat"))
        return
    await answer(turn, draft)
    turn.show(draft, again=True)


def dropped(approval: Approval) -> str:
    payload = json.loads(approval.payload_json)
    if approval.action == approvals.SEND_ACTION:
        to = payload.get("to_name") or payload.get("to", "")
        return f"Discarded the draft to {to}. Nothing was sent."
    if approval.action == EVENT_ACTION:
        return f"Dropped the proposed event '{payload.get('title', '')}'. Nothing was booked."
    return f"Discarded: {approval.preview.splitlines()[0]}. Nothing was changed."


async def discard(turn: Turn, intent: DiscardDraft) -> None:
    """Rejects the newest card waiting in this chat."""
    waiting = (
        approvals.list_pending(turn.session, turn.user, turn.conversation_id)
        if turn.conversation_id is not None
        else []
    )
    if not waiting:
        turn.say(NOTHING_WAITING)
        return
    card = waiting[-1]
    await approvals.discard(turn.session, turn.user, card.id, turn.runtime.manager)
    turn.note(approval_id=card.id)
    turn.say(dropped(card))
