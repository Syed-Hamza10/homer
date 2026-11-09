import json
import re
from typing import Any

from sqlmodel import Session, col, delete, func, select

from homer_core.db.models import Conversation, Message, User, utcnow
from homer_core.services.errors import DomainError, NotFound

LEGACY_TITLE_WORDS = 6
TITLE_WORDS = 5
TITLE_LENGTH = 60
ADDRESS = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
CALENDAR_RANGES = {
    "today": "today",
    "tomorrow": "tomorrow",
    "this_week": "this week",
    "next_week": "next week",
    "this_weekend": "this weekend",
}


class CannotRegenerate(DomainError):
    status_code = 409


def name_of(who: str) -> str:
    """A first name from a name or an address, never the address itself."""
    local = who.split("@")[0] if "@" in who else who
    parts = [part for part in re.split(r"[^A-Za-z\u00C0-\uFFFF]+", local) if part]
    return parts[0].capitalize() if parts else who


def short(text: str) -> str:
    words = ADDRESS.sub(lambda match: name_of(match.group()), text).split()
    title = " ".join(words[:TITLE_WORDS]).rstrip(",.;:!?")
    if len(words) > TITLE_WORDS:
        title += "…"
    return (title[:1].upper() + title[1:])[:TITLE_LENGTH]


def make_title(message: str) -> str:
    return short(message) or "New chat"


def intent_title(intent: dict[str, Any]) -> str | None:
    match intent.get("kind"):
        case "send_email" if intent.get("to"):
            return f"Email to {name_of(intent['to'])}"
        case "read_email" if intent.get("sender"):
            return f"Email from {name_of(intent['sender'])}"
        case "create_event" if intent.get("title"):
            return short(intent["title"])
        case "read_calendar":
            when = CALENDAR_RANGES.get(intent.get("range", ""))
            return f"Calendar {when}" if when else "Calendar"
        case "web_search" if intent.get("query"):
            return short(intent["query"])
        case "remind" if intent.get("text"):
            return short(f"Reminder: {intent['text']}")
        case "day_summary":
            return "Day summary"
    return None


def title_for(message: str, context: list[dict[str, Any]]) -> str:
    """A short title from the first resolved intent, else the first words of the message."""
    for intent in context:
        if (title := intent_title(intent)) is not None:
            return title
    return make_title(message)


def retitle(
    session: Session, conversation: Conversation, message: str, context: list[dict[str, Any]]
) -> None:
    """Replaces the default title after the first turn; a title the user typed stays."""
    if conversation.title not in (make_title(message), legacy_title(message)):
        return
    conversation.title = title_for(message, context)
    session.add(conversation)
    session.commit()


def legacy_title(message: str) -> str:
    return " ".join(message.split()[:LEGACY_TITLE_WORDS])[:TITLE_LENGTH]


def first_turns(session: Session, ids: list[int]) -> dict[int, dict[str, Message]]:
    firsts = (
        select(func.min(Message.id))
        .where(col(Message.conversation_id).in_(ids))
        .group_by(col(Message.conversation_id), col(Message.role))
    )
    turns: dict[int, dict[str, Message]] = {}
    for message in session.exec(select(Message).where(col(Message.id).in_(firsts))):
        turns.setdefault(message.conversation_id, {})[message.role] = message
    return turns


def backfill_titles(session: Session, conversations: list[Conversation]) -> None:
    """Gives chats titled the old way (the first six words) a short readable title."""
    turns = first_turns(session, [c.id for c in conversations if c.id is not None])
    changed = False
    for conversation in conversations:
        turn = turns.get(conversation.id or 0, {})
        asked, answered = turn.get("user"), turn.get("assistant")
        if asked is None or conversation.title != legacy_title(asked.content):
            continue
        context = json.loads(answered.context_json) if answered and answered.context_json else []
        title = title_for(asked.content, context)
        if title != conversation.title:
            conversation.title = title
            session.add(conversation)
            changed = True
    if changed:
        session.commit()


def list_conversations(session: Session, user: User) -> list[Conversation]:
    statement = (
        select(Conversation)
        .where(Conversation.user_id == user.id)
        .order_by(col(Conversation.updated_at).desc())
    )
    conversations = list(session.exec(statement))
    backfill_titles(session, conversations)
    return conversations


def get_conversation(session: Session, user: User, conversation_id: int) -> Conversation:
    conversation = session.get(Conversation, conversation_id)
    if conversation is None or conversation.user_id != user.id:
        raise NotFound(f"conversation {conversation_id} not found")
    return conversation


def list_messages(session: Session, user: User, conversation_id: int) -> list[Message]:
    get_conversation(session, user, conversation_id)
    statement = (
        select(Message).where(Message.conversation_id == conversation_id).order_by(col(Message.id))
    )
    return list(session.exec(statement))


def rename(session: Session, user: User, conversation_id: int, title: str) -> Conversation:
    conversation = get_conversation(session, user, conversation_id)
    conversation.title = title.strip()[:TITLE_LENGTH]
    session.add(conversation)
    session.commit()
    session.refresh(conversation)
    return conversation


def delete_conversation(session: Session, user: User, conversation_id: int) -> None:
    conversation = get_conversation(session, user, conversation_id)
    session.exec(delete(Message).where(col(Message.conversation_id) == conversation_id))
    session.delete(conversation)
    session.commit()


def regenerate(session: Session, user: User, conversation_id: int) -> str:
    """Removes the last exchange and returns its user text, for the client to send again."""
    conversation = get_conversation(session, user, conversation_id)
    messages = list_messages(session, user, conversation_id)
    if len(messages) < 2 or messages[-1].role != "assistant" or messages[-2].role != "user":
        raise CannotRegenerate("the last message is not an assistant reply")
    if messages[-1].created_approval:
        raise CannotRegenerate("a reply that created an approval cannot be regenerated")
    text = messages[-2].content
    session.delete(messages[-1])
    session.delete(messages[-2])
    conversation.updated_at = utcnow()
    session.add(conversation)
    session.commit()
    return text
