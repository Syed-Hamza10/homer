import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import structlog
from pydantic_ai.messages import (
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    PartDeltaEvent,
    PartStartEvent,
    TextPart,
    TextPartDelta,
    UserPromptPart,
)
from pydantic_ai.run import AgentRunResultEvent
from pydantic_ai.usage import RunUsage
from sqlmodel import Session

from achilles_core.agent.agent import Deps
from achilles_core.agent.gate import (
    APPROVAL_METADATA_KEY,
    ApprovalGate,
    RunState,
    mentioned_draft_ids,
)
from achilles_core.agent.router import Command, classify, parse_command
from achilles_core.agent.runtime import Runtime
from achilles_core.db.models import Conversation, Message, TokenCounter, User, utcnow
from achilles_core.services import approvals, briefs, calendar, drafts, followups, inbox
from achilles_core.services.conversations import get_conversation, list_messages
from achilles_core.services.errors import DomainError
from achilles_core.services.rules import get_rules

log = structlog.get_logger(__name__)

TITLE_LENGTH = 60
SUMMARY_LENGTH = 200
GENERIC_ERROR = "The assistant could not answer. Please try again."
REMIND_TOOLSET = "system"
SKILL_COMMANDS = frozenset({"brief", "inbox", "digest", "slot", "draft", "followup"})
SLOT_LIMIT = 3


@dataclass(frozen=True)
class ChatEvent:
    name: str
    data: dict[str, Any]


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


def summarise(content: Any) -> str:
    text = content if isinstance(content, str) else json.dumps(content, default=str)
    return text if len(text) <= SUMMARY_LENGTH else text[: SUMMARY_LENGTH - 1] + "…"


def text_event(outcome: Outcome, text: str) -> ChatEvent:
    outcome.answer += text
    return ChatEvent("token", {"text": text})


async def decide(session: Session, user: User, runtime: Runtime, command: Command) -> str:
    if not command.arg.isdigit():
        return f"Usage: /{command.name} <approval id>"
    approval_id = int(command.arg)
    try:
        if command.name == "approve":
            approval = await approvals.approve(session, user, approval_id, runtime.manager)
        else:
            approval = approvals.reject(session, user, approval_id)
    except DomainError as error:
        return str(error).capitalize()
    return f"Approval #{approval.id} ({approval.action}): {approval.status}."


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


async def run_agent(
    runtime: Runtime,
    toolset_name: str,
    prompt: str,
    history: list[ModelMessage],
    deps: Deps,
    outcome: Outcome,
) -> AsyncIterator[ChatEvent]:
    state = RunState(draft_ids=mentioned_draft_ids(history, prompt))
    gate = ApprovalGate(wrapped=runtime.toolsets[toolset_name], state=state)
    async with runtime.agent.run_stream_events(
        prompt, deps=deps, message_history=history, toolsets=[gate]
    ) as events:
        async for event in events:
            if isinstance(event, PartStartEvent) and isinstance(event.part, TextPart):
                if outcome.answer:
                    yield text_event(outcome, "\n\n")
                if event.part.content:
                    yield text_event(outcome, event.part.content)
            elif isinstance(event, PartDeltaEvent) and isinstance(event.delta, TextPartDelta):
                yield text_event(outcome, event.delta.content_delta)
            elif isinstance(event, FunctionToolCallEvent):
                yield ChatEvent(
                    "tool_call",
                    {"name": event.part.tool_name, "args": event.part.args_as_dict()},
                )
            elif isinstance(event, FunctionToolResultEvent):
                metadata = event.part.metadata
                if isinstance(metadata, dict) and APPROVAL_METADATA_KEY in metadata:
                    approval = next(
                        a for a in state.approvals if a.id == metadata[APPROVAL_METADATA_KEY]
                    )
                    yield ChatEvent(
                        "approval_required",
                        {
                            "approval_id": approval.id,
                            "action": approval.action,
                            "preview": approval.preview,
                        },
                    )
                yield ChatEvent(
                    "tool_result",
                    {"name": event.part.tool_name, "summary": summarise(event.part.content)},
                )
            elif isinstance(event, AgentRunResultEvent):
                outcome.usage.incr(event.result.usage)


async def respond(
    session: Session,
    user: User,
    runtime: Runtime,
    history: list[ModelMessage],
    message: str,
    outcome: Outcome,
) -> AsyncIterator[ChatEvent]:
    command = parse_command(message)
    deps = Deps(user_id=user.id, user_name=user.name, timezone=user.timezone, session=session)
    if command is None:
        toolset_name, usage = await classify(runtime.classifier, message)
        outcome.usage.incr(usage)
        log.info("toolset_chosen", toolset=toolset_name)
        events = run_agent(runtime, toolset_name, message, history, deps, outcome)
    elif command.name in SKILL_COMMANDS:
        yield text_event(outcome, await run_skill(session, user, runtime, command))
        return
    elif command.name == "remind":
        prompt = f"Set a reminder: {command.arg}"
        events = run_agent(runtime, REMIND_TOOLSET, prompt, history, deps, outcome)
    elif command.name in ("approve", "reject"):
        yield text_event(outcome, await decide(session, user, runtime, command))
        return
    else:
        yield text_event(outcome, "Unknown command.")
        return
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
        async for event in respond(session, user, runtime, history, message, outcome):
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
