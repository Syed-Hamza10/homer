from sqlmodel import Session, select

from achilles_core.db.models import Conversation, Message, User
from achilles_core.services.errors import NotFound


def list_conversations(session: Session, user: User) -> list[Conversation]:
    statement = (
        select(Conversation)
        .where(Conversation.user_id == user.id)
        .order_by(Conversation.updated_at.desc())
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
        select(Message).where(Message.conversation_id == conversation_id).order_by(Message.id)
    )
    return list(session.exec(statement))
