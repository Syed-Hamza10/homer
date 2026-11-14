import json

from fastapi import APIRouter, Response

from homer_core.api.deps import CurrentUser, SessionDep
from homer_core.api.schemas.conversations import (
    ChoiceCard,
    ConversationOut,
    MessageOut,
    RegenerateOut,
    RenameIn,
)
from homer_core.db.models import Message
from homer_core.services import conversations
from homer_core.services.jobs.choice import card

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.get("")
def list_conversations(user: CurrentUser, session: SessionDep) -> list[ConversationOut]:
    return [
        ConversationOut.model_validate(item, from_attributes=True)
        for item in conversations.list_conversations(session, user)
    ]


def message_out(message: Message) -> MessageOut:
    out = MessageOut.model_validate(message, from_attributes=True)
    if not message.choice_json:
        return out
    shown = ChoiceCard.model_validate(card(json.loads(message.choice_json)))
    return out.model_copy(update={"choice": shown})


@router.get("/{conversation_id}/messages")
def list_messages(conversation_id: int, user: CurrentUser, session: SessionDep) -> list[MessageOut]:
    return [
        message_out(item) for item in conversations.list_messages(session, user, conversation_id)
    ]


@router.patch("/{conversation_id}")
def rename(
    conversation_id: int, body: RenameIn, user: CurrentUser, session: SessionDep
) -> ConversationOut:
    conversation = conversations.rename(session, user, conversation_id, body.title)
    return ConversationOut.model_validate(conversation, from_attributes=True)


@router.delete("/{conversation_id}", status_code=204)
def delete(conversation_id: int, user: CurrentUser, session: SessionDep) -> Response:
    conversations.delete_conversation(session, user, conversation_id)
    return Response(status_code=204)


@router.post("/{conversation_id}/regenerate")
def regenerate(conversation_id: int, user: CurrentUser, session: SessionDep) -> RegenerateOut:
    return RegenerateOut(message=conversations.regenerate(session, user, conversation_id))
