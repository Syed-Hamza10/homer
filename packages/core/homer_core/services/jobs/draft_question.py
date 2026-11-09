import json
import re
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlmodel import col, select

from homer_core.db.models import Approval
from homer_core.services import approval_edits, approvals
from homer_core.services.approval_edits import MailEdit
from homer_core.services.jobs.send_email import assemble, split
from homer_core.services.jobs.turn import Turn

EVENT_ACTION = "cal_create"
URL = re.compile(r"https?://\S+")
LINK = re.compile(r"\blink\b", re.IGNORECASE)
NOT_CREATED = "The event gets its Google Calendar link once you press Create."
CREATE_FIRST = f"{NOT_CREATED} Create it first and I'll add the link to the email."
NO_DRAFT = "There's no draft in this chat yet."
ANSWER_PROMPT = """The user is asking about the email draft below, which is waiting in this
chat and has not been sent. Answer the question from the draft only, honestly, in one or two
sentences. Start with Yes or No when it is a yes or no question. Never say it was sent.
{event}
Draft to {to}
Subject: {subject}
<untrusted>{body}</untrusted>"""


def latest_event(turn: Turn) -> Approval | None:
    """The newest event this chat booked or proposed."""
    statement = (
        select(Approval)
        .where(
            Approval.user_id == turn.user.id,
            Approval.conversation_id == turn.conversation_id,
            Approval.action == EVENT_ACTION,
            Approval.status != approvals.SUPERSEDED,
        )
        .order_by(col(Approval.id).desc())
    )
    return turn.session.exec(statement).first()


def pending_draft(turn: Turn) -> Approval | None:
    found = approvals.latest_send(turn.session, turn.user, turn.conversation_id, None)
    return found if found is not None and found.status == "pending" else None


def clock(moment: datetime) -> str:
    hour = moment.hour % 12 or 12
    return f"{hour}:{moment:%M}"


def when_line(payload: dict[str, Any], timezone: str) -> str:
    """'Saturday 14 Nov, 3:00–3:30 pm PKT' for the event's start and end."""
    zone = ZoneInfo(timezone)
    start = datetime.fromisoformat(payload["start"]).astimezone(zone)
    end = datetime.fromisoformat(payload["end"]).astimezone(zone)
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


async def link_event(turn: Turn) -> None:
    """Puts the event's real Google Calendar link in the draft, or says honestly why it cannot
    yet and adds the date and time, which need no link."""
    draft, event = pending_draft(turn), latest_event(turn)
    if draft is None:
        turn.say(NO_DRAFT)
        return
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


async def answer(turn: Turn) -> None:
    """Answers a question about this chat's waiting draft from its content."""
    draft = pending_draft(turn)
    if draft is None:
        turn.say(NO_DRAFT)
        return
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
