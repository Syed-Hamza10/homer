import asyncio
from collections.abc import AsyncIterator
from contextlib import aclosing
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
    is_conversational,
    parse_command,
    parse_decision,
)
from homer_core.agent.runtime import Runtime
from homer_core.db.models import Conversation, Message, TokenCounter, User, utcnow
from homer_core.services import approvals, briefs, calendar, drafts, followups, inbox
from homer_core.services.conversations import get_conversation, list_messages, make_title
from homer_core.services.errors import DomainError
from homer_core.services.jobs import dispatch
from homer_core.services.jobs.turn import ChatEvent, JobError, ReconnectRequired, Turn
from homer_core.services.rules import get_rules

log = structlog.get_logger(__name__)

INTENT_HISTORY = 6
GENERIC_ERROR = "The assistant could not answer. Please try again."
SKILL_COMMANDS = frozenset({"brief", "inbox", "digest", "slot", "draft", "followup"})
SLOT_LIMIT = 3
NOTHING_PENDING = "Nothing is waiting for your approval."


@dataclass
class Outcome:
    answer: str = ""
    usage: RunUsage = field(default_factory=RunUsage)
    shown: str = ""
    created_approval: bool = False

    def track(self, event: ChatEvent) -> None:
        if event.name == "token":
            self.shown += event.data["text"]
        elif event.name == "replace":
            self.shown = event.data["text"]
        elif event.name == "approval_required":
            self.created_approval = True


def to_history(messages: list[Message]) -> list[ModelMessage]:
    return [
        ModelRequest(parts=[UserPromptPart(content=message.content)])
        if message.role == "user"
        else ModelResponse(parts=[TextPart(content=message.content)])
        for message in messages
        if message.content
    ]


def start_conversation(session: Session, user: User, message: str) -> Conversation:
    conversation = Conversation(user_id=user.id, title=make_title(message))
    session.add(conversation)
    session.commit()
    session.refresh(conversation)
    return conversation


def save_message(
    session: Session,
    conversation: Conversation,
    role: str,
    content: str,
    stopped: bool = False,
    created_approval: bool = False,
) -> Message:
    message = Message(
        conversation_id=conversation.id,
        role=role,
        content=content,
        stopped=stopped,
        created_approval=created_approval,
    )
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
    session: Session, user: User, runtime: Runtime, message: str
) -> str | None:
    """Settles the one pending approval from a typed word; None lets the message through."""
    decision = parse_decision(message)
    if decision is None:
        return None
    pending = approvals.list_pending(session, user)
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


async def run_jobs(turn: Turn) -> None:
    try:
        recent = turn.history[-INTENT_HISTORY:]
        intents, usage = await extract(turn.runtime.intents, turn.message, recent, turn.now)
        turn.usage.incr(usage)
        log.info("intents", kinds=[intent.kind for intent in intents])
        for intent in intents:
            try:
                await dispatch.run(turn, intent)
            except ReconnectRequired:
                turn.ask_to_reconnect()
                break
            except (JobError, DomainError) as error:
                turn.say(str(error))
    finally:
        turn.events.put_nowait(None)


async def run_turn(turn: Turn, outcome: Outcome) -> AsyncIterator[ChatEvent]:
    task = asyncio.create_task(run_jobs(turn))
    try:
        while (event := await turn.events.get()) is not None:
            yield event
        await task
    finally:
        task.cancel()
    outcome.answer = turn.answer
    outcome.usage.incr(turn.usage)


async def respond(
    session: Session,
    user: User,
    runtime: Runtime,
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
    settled = await decide_pending(session, user, runtime, message)
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
    )
    async with aclosing(run_turn(turn, outcome)) as events:
        async for event in events:
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
        async with aclosing(respond(session, user, runtime, history, message, outcome)) as events:
            async for event in events:
                outcome.track(event)
                yield event
    except (asyncio.CancelledError, GeneratorExit):
        save_message(
            session, conversation, "assistant", outcome.shown, True, outcome.created_approval
        )
        log.info("chat_stopped", conversation_id=conversation.id)
        raise
    except Exception:
        log.exception("chat_failed", conversation_id=conversation.id)
        yield ChatEvent("error", {"message": GENERIC_ERROR})
        return

    save_message(
        session,
        conversation,
        "assistant",
        outcome.answer,
        created_approval=outcome.created_approval,
    )
    usage = outcome.usage
    count_tokens(session, user, usage.input_tokens, usage.output_tokens)
    yield ChatEvent(
        "done", {"input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens}
    )
