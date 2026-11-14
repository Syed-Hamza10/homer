import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import aclosing
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

import structlog
from pydantic import TypeAdapter
from pydantic_ai.exceptions import ModelAPIError, ModelHTTPError
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, TextPart, UserPromptPart
from pydantic_ai.usage import RunUsage
from sqlmodel import Session, col, select

from homer_core.agent import routing
from homer_core.agent.intents import Background, Intent, extract
from homer_core.agent.router import (
    Command,
    Decision,
    is_conversational,
    parse_command,
    parse_decision,
)
from homer_core.agent.runtime import Runtime
from homer_core.db.models import Approval, Conversation, Message, TokenCounter, User, utcnow
from homer_core.services import approvals, briefs, calendar, drafts, followups, inbox
from homer_core.services.conversations import (
    get_conversation,
    list_messages,
    make_title,
    retitle,
)
from homer_core.services.errors import DomainError
from homer_core.services.facts import prompt_facts
from homer_core.services.jobs import choice, dispatch, draft_question
from homer_core.services.jobs.turn import ChatEvent, JobError, ReconnectRequired, Turn
from homer_core.services.rules import get_rules

log = structlog.get_logger(__name__)

INTENT_HISTORY = 6
CONTEXT_TURNS = 4
GENERIC_ERROR = "The assistant could not answer. Please try again."
MODEL_DOWN = "The AI model isn't running. Start Ollama and try again."
CONNECTION_ERRORS = frozenset({"APIConnectionError", "APITimeoutError", "ConnectError"})
SKILL_COMMANDS = frozenset({"brief", "inbox", "digest", "slot", "draft", "followup"})
SLOT_LIMIT = 3
ALREADY_DONE = "I already drafted that one — it's above."
REPEAT_SECONDS = 120
INTENT: TypeAdapter[Intent] = TypeAdapter(Intent)


@dataclass
class Outcome:
    answer: str = ""
    usage: RunUsage = field(default_factory=RunUsage)
    shown: str = ""
    created_approval: bool = False
    context: list[dict[str, Any]] = field(default_factory=list)
    approval_ids: list[int] = field(default_factory=list)
    question: dict[str, Any] | None = None

    def track(self, event: ChatEvent) -> None:
        if event.name == "token":
            self.shown += event.data["text"]
        elif event.name == "replace":
            self.shown = event.data["text"]
        elif event.name == "approval_required":
            self.created_approval |= not event.data.get("again")
            self.approval_ids.append(event.data["approval_id"])


def to_history(messages: list[Message]) -> list[ModelMessage]:
    return [
        ModelRequest(parts=[UserPromptPart(content=message.content)])
        if message.role == "user"
        else ModelResponse(parts=[TextPart(content=choice.shown(message))])
        for message in messages
        if message.content
    ]


def last_context(messages: list[Message]) -> list[dict[str, Any]]:
    """The resolved intents of the latest assistant turn, for follow-ups."""
    for message in reversed(messages):
        if message.role == "assistant":
            return json.loads(message.context_json) if message.context_json else []
    return []


def recent_context(messages: list[Message]) -> list[dict[str, Any]]:
    """The resolved intents of the last few assistant turns, oldest first, so "it" can still
    mean the event booked two turns ago."""
    replies = [m for m in messages if m.role == "assistant" and m.context_json]
    return [item for m in replies[-CONTEXT_TURNS:] for item in json.loads(m.context_json or "[]")]


def start_conversation(session: Session, user: User, message: str) -> Conversation:
    conversation = Conversation(user_id=user.id, title=make_title(message))
    session.add(conversation)
    session.commit()
    session.refresh(conversation)
    return conversation


def repeated(session: Session, stored: list[Message], message: str) -> bool:
    """The same message was sent in this chat in the last two minutes, its turn made a card and
    no card of the chat was approved or rejected since."""
    asked = [index for index, item in enumerate(stored) if item.role == "user"]
    if not asked or asked[-1] + 1 >= len(stored):
        return False
    last, reply = stored[asked[-1]], stored[asked[-1] + 1]
    sent = last.created_at.replace(tzinfo=last.created_at.tzinfo or UTC)
    recent = (utcnow() - sent).total_seconds() <= REPEAT_SECONDS
    same = " ".join(last.content.lower().split()) == " ".join(message.lower().split())
    if not (same and recent and reply.created_approval):
        return False
    decided = select(Approval).where(
        Approval.conversation_id == last.conversation_id,
        col(Approval.decided_at) >= sent,
    )
    return session.exec(decided).first() is None


def save_message(
    session: Session,
    conversation: Conversation,
    role: str,
    content: str,
    stopped: bool = False,
    created_approval: bool = False,
    context: list[dict[str, Any]] | None = None,
    question: dict[str, Any] | None = None,
) -> Message:
    message = Message(
        conversation_id=conversation.id,
        role=role,
        content=content,
        stopped=stopped,
        created_approval=created_approval,
        context_json=json.dumps(context) if context else None,
        choice_json=json.dumps(question) if question else None,
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
    if decision == "approve" and not is_conversational(message):
        return draft_question.NO_DRAFT
    return None


def pending_card(approval: Approval) -> str:
    payload = json.loads(approval.payload_json)
    if approval.action == approvals.SEND_ACTION:
        to = payload.get("to_name") or payload.get("to", "")
        return f'email draft to {to}, subject "{payload.get("subject", "")}"'
    if approval.action == "cal_create":
        return f"new event '{payload.get('title', '')}' at {payload.get('start', '')}"
    return approval.preview.splitlines()[0]


def pending_cards(session: Session, user: User, conversation_id: int) -> str:
    """The cards waiting in this chat, in words for the intent call."""
    waiting = approvals.list_pending(session, user, conversation_id)
    return "; ".join(pending_card(approval) for approval in waiting) or "nothing"


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


Work = Callable[[Turn], Awaitable[None]]


async def run_jobs(turn: Turn, work: Work) -> None:
    try:
        await work(turn)
    except ReconnectRequired:
        turn.ask_to_reconnect()
    finally:
        turn.events.put_nowait(None)


async def jobs(turn: Turn) -> None:
    """One intent call and a job per intent. A job's error is said and the next job runs; a
    refused Google token ends the turn."""
    known = Background(
        turn.previous,
        turn.facts,
        turn.date_format,
        turn.user.timezone,
        pending_cards(turn.session, turn.user, turn.conversation_id or 0),
    )
    recent = turn.history[-INTENT_HISTORY:]
    found, usage = await extract(turn.runtime.intents, turn.message, recent, turn.now, known)
    turn.usage.incr(usage)
    intents = routing.refined(found, turn.message, turn.previous, turn.facts)
    log.info("intents", kinds=[intent.kind for intent in intents])
    for intent in intents:
        await attempt(turn, intent)


async def attempt(turn: Turn, intent: Intent) -> None:
    try:
        await dispatch.run(turn, intent)
    except ReconnectRequired:
        raise
    except choice.Choice as question:
        choice.ask(turn, question)
    except (JobError, DomainError) as error:
        turn.say(str(error))


def resume(intent: dict[str, Any]) -> Work:
    """Runs the job a pick-one question paused, with no intent call."""

    async def work(turn: Turn) -> None:
        await attempt(turn, INTENT.validate_python(intent))

    return work


async def run_turn(turn: Turn, outcome: Outcome, work: Work = jobs) -> AsyncIterator[ChatEvent]:
    task = asyncio.create_task(run_jobs(turn, work))
    try:
        while (event := await turn.events.get()) is not None:
            yield event
        await task
    finally:
        task.cancel()
    outcome.answer = turn.answer
    outcome.usage.incr(turn.usage)
    outcome.context = turn.resolved
    outcome.question = turn.question


def make_turn(
    session: Session,
    user: User,
    runtime: Runtime,
    conversation_id: int,
    history: list[ModelMessage],
    message: str,
    previous: list[dict[str, Any]] | None,
    earlier: list[dict[str, Any]] | None,
) -> Turn:
    return Turn(
        session=session,
        user=user,
        message=message,
        runtime=runtime,
        rules=get_rules(session, user.id),
        history=history,
        now=datetime.now(ZoneInfo(user.timezone)),
        conversation_id=conversation_id,
        previous=previous or [],
        earlier=earlier or [],
        facts=prompt_facts(session, user),
    )


async def respond(
    session: Session,
    user: User,
    runtime: Runtime,
    conversation_id: int,
    history: list[ModelMessage],
    message: str,
    outcome: Outcome,
    previous: list[dict[str, Any]] | None = None,
    earlier: list[dict[str, Any]] | None = None,
    answer: choice.Answer | None = None,
) -> AsyncIterator[ChatEvent]:
    if answer is not None:
        args = (session, user, runtime, conversation_id, history)
        turn = make_turn(*args, answer.message, previous, earlier)
        turn.picked = answer.picked
        async with aclosing(run_turn(turn, outcome, resume(answer.intent))) as events:
            async for event in events:
                yield event
        return
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
    turn = make_turn(session, user, runtime, conversation_id, history, message, previous, earlier)
    async with aclosing(run_turn(turn, outcome)) as events:
        async for event in events:
            yield event


def model_unreachable(error: BaseException | None) -> bool:
    """The model server could not be reached: a model API error with no HTTP status, or a
    connection error anywhere in the cause chain."""
    while error is not None:
        if isinstance(error, ModelAPIError) and not isinstance(error, ModelHTTPError):
            return True
        if type(error).__name__ in CONNECTION_ERRORS:
            return True
        error = error.__cause__ or error.__context__
    return False


async def stream(
    session: Session,
    user: User,
    runtime: Runtime,
    conversation_id: int | None,
    message: str,
    picked: tuple[str, str] | None = None,
) -> AsyncIterator[ChatEvent]:
    """Streams one turn. `picked` is a (question id, option id) click on a pick-one card; it
    continues the paused job, and falls back to the typed label when the question is gone."""
    if conversation_id is None:
        conversation = start_conversation(session, user, message)
    else:
        conversation = get_conversation(session, user, conversation_id)
    stored = list_messages(session, user, conversation.id)
    history = to_history(stored)
    previous = last_context(stored)
    earlier = recent_context(stored)
    answer = choice.take(session, stored, *picked) if picked else None
    user_message = save_message(session, conversation, "user", message)
    yield ChatEvent("meta", {"conversation_id": conversation.id, "message_id": user_message.id})
    if answer is None and repeated(session, stored, message):
        save_message(session, conversation, "assistant", ALREADY_DONE)
        yield ChatEvent("token", {"text": ALREADY_DONE})
        yield ChatEvent("done", {"input_tokens": 0, "output_tokens": 0})
        return

    outcome = Outcome()
    try:
        async with aclosing(
            respond(
                session,
                user,
                runtime,
                conversation.id,
                history,
                message,
                outcome,
                previous,
                earlier,
                answer,
            )
        ) as events:
            async for event in events:
                outcome.track(event)
                yield event
    except (asyncio.CancelledError, GeneratorExit):
        reply = save_message(
            session, conversation, "assistant", outcome.shown, True, outcome.created_approval
        )
        approvals.attach(session, outcome.approval_ids, reply.id)
        log.info("chat_stopped", conversation_id=conversation.id)
        raise
    except Exception as error:
        log.exception("chat_failed", conversation_id=conversation.id)
        message = MODEL_DOWN if model_unreachable(error) else GENERIC_ERROR
        yield ChatEvent("error", {"message": message})
        return

    reply = save_message(
        session,
        conversation,
        "assistant",
        outcome.answer,
        created_approval=outcome.created_approval,
        context=outcome.context,
        question=outcome.question,
    )
    approvals.attach(session, outcome.approval_ids, reply.id)
    if not stored:
        retitle(session, conversation, message, outcome.context)
    usage = outcome.usage
    count_tokens(session, user, usage.input_tokens, usage.output_tokens)
    yield ChatEvent(
        "done", {"input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens}
    )
