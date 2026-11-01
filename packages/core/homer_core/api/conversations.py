from fastapi import APIRouter

from homer_core.api.deps import CurrentUser, SessionDep
from homer_core.api.schemas.conversations import ConversationOut, MessageOut
from homer_core.services import conversations

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.get("")
def list_conversations(user: CurrentUser, session: SessionDep) -> list[ConversationOut]:
    return [
        ConversationOut.model_validate(item, from_attributes=True)
        for item in conversations.list_conversations(session, user)
    ]


@router.get("/{conversation_id}/messages")
def list_messages(conversation_id: int, user: CurrentUser, session: SessionDep) -> list[MessageOut]:
    return [
        MessageOut.model_validate(item, from_attributes=True)
        for item in conversations.list_messages(session, user, conversation_id)
    ]
