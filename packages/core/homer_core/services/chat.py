import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

import structlog
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, TextPart, UserPromptPart
from pydantic_ai.usage import RunUsage
from sqlmodel import Session

from homer_core.agent.intents import extract
from homer_core.agent.router import (
    Command,
    Decision,
    asks_if_sent,
    is_conversational,
    is_edit,
    parse_command,
    parse_decision,
)
from homer_core.agent.runtime import Runtime
from homer_core.db.models import Conversation, Message, TokenCounter, User, utcnow
from homer_core.services import approvals, briefs, calendar, drafts, followups, inbox
from homer_core.services.conversations import get_conversation, list_messages
from homer_core.services.errors import DomainError
from homer_core.services.jobs import dispatch, edit_email, mail_status
from homer_core.services.jobs.turn import ChatEvent, JobError, Turn
from homer_core.services.rules import get_rules

log = structlog.get_logger(__name__)

TITLE_LENGTH = 60
INTENT_HISTORY = 6
GENERIC_ERROR = "The assistant could not answer. Please try again."
SKILL_COMMANDS = frozenset({"brief", "inbox", "digest", "slot", "draft", "followup"})
SLOT_LIMIT = 3
NOTHING_PENDING = "There's no draft waiting in this chat."


@dataclass
class Outcome:
    answer: str = ""
    usage: RunUsage = field(default_factory=RunUsage)


def to_history(messages: list[Message]) -> list[ModelMessage]:
    return [
        ModelRequest(parts=[UserPromptPart(content=message.content)])
        if message.role == "user"
        else ModelResponse(parts=[TextPart(content=message.content)])
        for message in messages
        if message.content
    ]


def start_conversation(session: Session, user: User, message: str) -> Conversation:
    conversation = Conversation(user_id=user.id, title=message[:TITLE_LENGTH])
    session.add(conversation)
    session.commit()
    session.refresh(conversation)
    return conversation


def save_message(session: Session, conversation: Conversation, role: str, content: str) -> Message:
    message = Message(conversation_id=conversation.id, role=role, content=content)
    conversation.updated_at = utcnow()
    session.add(message)
    session.add(conversation)
    session.commit()
    session.refresh(message)
    return message


def count_tokens(session: Session, user: User, input_tokens: int, output_tokens: int) -> None:
    counter = session.get(TokenCounter, user.id) or TokenCounter(user_id=user.id)
    counter.input_tokens += input_tokens
    counter.output_tokens += output_tokens
    counter.requests += 1
    session.add(counter)
    session.commit()


def text_event(outcome: Outcome, text: str) -> ChatEvent:
    outcome.answer += text
    return ChatEvent("token", {"text": text})


async def settle(
    session: Session, user: User, runtime: Runtime, decision: Decision, approval_id: int
) -> str:
    try:
        if decision == "approve":
            approval = await approvals.approve(session, user, approval_id, runtime.manager)
        else:
            approval = await approvals.discard(session, user, approval_id, runtime.manager)
    except DomainError as error:
        return str(error).capitalize()
    return f"Approval #{approval.id} ({approval.action}): {approval.status}."


async def decide(session: Session, user: User, runtime: Runtime, command: Command) -> str:
    if not command.arg.isdigit():
        return f"Usage: /{command.name} <approval id>"
    decision: Decision = "approve" if command.name == "approve" else "reject"
    return await settle(session, user, runtime, decision, int(command.arg))


async def decide_pending(
    session: Session, user: User, runtime: Runtime, conversation_id: int, message: str
) -> str | None:
    """Settles this chat's one pending approval from a typed reply; None lets the message on."""
    decision = parse_decision(message)
    if decision is None:
        return None
    pending = approvals.list_pending(session, user, conversation_id)
    if len(pending) == 1:
        return await settle(session, user, runtime, decision, pending[0].id)
    if pending:
        listed = "; ".join(f"#{a.id} {a.action}" for a in pending)
        return f"Several approvals are waiting: {listed}. Say /{decision} N to pick one."
    return None if is_conversational(message) else NOTHING_PENDING


async def run_skill(session: Session, user: User, runtime: Runtime, command: Command) -> str:
    rules = get_rules(session, user.id)
    try:
        match command.name:
            case "brief":
                return (await briefs.morning_brief(session, user, runtime.manager, rules)).content
            case "inbox":
                rows = await inbox.refresh_inbox(session, user, runtime.manager, rules)
                if rows:
                    await inbox.triage(session, user, runtime.manager, rules)
                return inbox.summary(session, user)
            case "digest":
                return (await briefs.eod_digest(session, user, runtime.manager, rules)).content
            case "slot":
                minutes = int(command.arg) if command.arg.isdigit() else 30
                slots = await calendar.find_slots(runtime.manager, rules, minutes)
                if not slots:
                    return "No free slots found in the next week."
                shown = slots[:SLOT_LIMIT]
                listed = "; ".join(f"{slot['start']} to {slot['end']}" for slot in shown)
                return f"Free slots: {listed}."
            case "draft":
                if not command.arg:
                    return "Usage: /draft <message id>"
                result = await drafts.draft_reply(
                    user, runtime.manager, runtime.model, rules, command.arg
                )
                return (
                    f"Draft ready to {result['to']}: {result['subject']} "
                    f"(draft {result['draft_id']})."
                )
            case "followup":
                parts = command.arg.split()
                if not parts:
                    return "Usage: /followup <thread id> [days]"
                days = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
                row = await followups.create_followup(
                    session, user, runtime.manager, rules, parts[0], days
                )
                return f"Follow-up #{row.id} on '{row.subject}' due {row.due_at:%Y-%m-%d}."
    except DomainError as error:
        return str(error).capitalize()
    return "Unknown command."


async def routed(turn: Turn) -> bool:
    """Answers send-status questions and edits of this chat's draft without the intent call."""
    if asks_if_sent(turn.message):
        turn.say(mail_status.answer(turn))
        return True
    if not is_edit(turn.message):
        return False
    pending = approvals.list_pending(turn.session, turn.user, turn.conversation_id)
    drafts = [approval for approval in pending if approval.action == approvals.SEND_ACTION]
    if len(drafts) != 1:
        return False
    try:
        await edit_email.run(turn, drafts[0])
    except (JobError, DomainError) as error:
        turn.say(str(error))
    return True


async def run_jobs(turn: Turn) -> None:
    try:
        if await routed(turn):
            return
        recent = turn.history[-INTENT_HISTORY:]
        intents, usage = await extract(turn.runtime.intents, turn.message, recent, turn.now)
        turn.usage.incr(usage)
        log.info("intents", kinds=[intent.kind for intent in intents])
        for intent in intents:
            try:
                await dispatch.run(turn, intent)
            except (JobError, DomainError) as error:
                turn.say(str(error))
    finally:
        turn.events.put_nowait(None)


async def run_turn(turn: Turn, outcome: Outcome) -> AsyncIterator[ChatEvent]:
    task = asyncio.create_task(run_jobs(turn))
    while (event := await turn.events.get()) is not None:
        yield event
    await task
    outcome.answer = turn.answer
    outcome.usage.incr(turn.usage)


async def respond(
    session: Session,
    user: User,
    runtime: Runtime,
    conversation_id: int,
    history: list[ModelMessage],
    message: str,
    outcome: Outcome,
) -> AsyncIterator[ChatEvent]:
    command = parse_command(message)
    if command is not None and command.name in SKILL_COMMANDS:
        yield text_event(outcome, await run_skill(session, user, runtime, command))
        return
    if command is not None and command.name in ("approve", "reject"):
        yield text_event(outcome, await decide(session, user, runtime, command))
        return
    if command is not None and command.name == "remind":
        message = f"Remind me {command.arg}"
    settled = await decide_pending(session, user, runtime, conversation_id, message)
    if settled is not None:
        yield text_event(outcome, settled)
        return
    turn = Turn(
        session=session,
        user=user,
        message=message,
        runtime=runtime,
        rules=get_rules(session, user.id),
        history=history,
        now=datetime.now(ZoneInfo(user.timezone)),
        conversation_id=conversation_id,
    )
    async for event in run_turn(turn, outcome):
        yield event


async def stream(
    session: Session,
    user: User,
    runtime: Runtime,
    conversation_id: int | None,
    message: str,
) -> AsyncIterator[ChatEvent]:
    if conversation_id is None:
        conversation = start_conversation(session, user, message)
    else:
        conversation = get_conversation(session, user, conversation_id)
    history = to_history(list_messages(session, user, conversation.id))
    user_message = save_message(session, conversation, "user", message)
    yield ChatEvent("meta", {"conversation_id": conversation.id, "message_id": user_message.id})

    outcome = Outcome()
    try:
        async for event in respond(
            session, user, runtime, conversation.id, history, message, outcome
        ):
            yield event
    except Exception:
        log.exception("chat_failed", conversation_id=conversation.id)
        yield ChatEvent("error", {"message": GENERIC_ERROR})
        return

    save_message(session, conversation, "assistant", outcome.answer)
    usage = outcome.usage
    count_tokens(session, user, usage.input_tokens, usage.output_tokens)
    yield ChatEvent(
        "done", {"input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens}
    )
