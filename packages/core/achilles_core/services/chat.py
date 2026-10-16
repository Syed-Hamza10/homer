from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import structlog
from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, TextPart, UserPromptPart
from sqlmodel import Session

from achilles_core.agent.agent import Deps
from achilles_core.db.models import Conversation, Message, TokenCounter, User, utcnow
from achilles_core.services.conversations import get_conversation, list_messages

log = structlog.get_logger(__name__)

TITLE_LENGTH = 60
GENERIC_ERROR = "The assistant could not answer. Please try again."


@dataclass(frozen=True)
class ChatEvent:
    name: str
    data: dict[str, Any]


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


async def stream(
    session: Session,
    user: User,
    agent: Agent[Deps, str],
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

    deps = Deps(user_name=user.name, timezone=user.timezone)
    answer = ""
    try:
        async with agent.run_stream(message, deps=deps, message_history=history) as result:
            async for delta in result.stream_text(delta=True):
                answer += delta
                yield ChatEvent("token", {"text": delta})
            usage = result.usage
    except Exception:
        log.exception("chat_failed", conversation_id=conversation.id)
        yield ChatEvent("error", {"message": GENERIC_ERROR})
        return

    save_message(session, conversation, "assistant", answer)
    count_tokens(session, user, usage.input_tokens, usage.output_tokens)
    yield ChatEvent(
        "done", {"input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens}
    )
