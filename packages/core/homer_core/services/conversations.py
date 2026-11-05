from sqlmodel import Session, col, delete, select

from homer_core.db.models import Conversation, Message, User, utcnow
from homer_core.services.errors import DomainError, NotFound

TITLE_WORDS = 6
TITLE_LENGTH = 60


class CannotRegenerate(DomainError):
    status_code = 409


def make_title(message: str) -> str:
    return " ".join(message.split()[:TITLE_WORDS])[:TITLE_LENGTH]


def list_conversations(session: Session, user: User) -> list[Conversation]:
    statement = (
        select(Conversation)
        .where(Conversation.user_id == user.id)
        .order_by(col(Conversation.updated_at).desc())
    )
    return list(session.exec(statement))


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
