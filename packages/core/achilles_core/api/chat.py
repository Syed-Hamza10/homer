import json
from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from achilles_core.api.deps import AgentDep, CurrentUser, SessionDep
from achilles_core.api.schemas.chat import ChatRequest
from achilles_core.services import chat
from achilles_core.services.conversations import get_conversation

router = APIRouter(prefix="/api", tags=["chat"])


def sse_frame(event: chat.ChatEvent) -> str:
    return f"event: {event.name}\ndata: {json.dumps(event.data)}\n\n"


async def frames(events: AsyncIterator[chat.ChatEvent]) -> AsyncIterator[str]:
    async for event in events:
        yield sse_frame(event)


@router.post("/chat")
async def post_chat(
    body: ChatRequest, user: CurrentUser, session: SessionDep, agent: AgentDep
) -> StreamingResponse:
    if body.conversation_id is not None:
        get_conversation(session, user, body.conversation_id)
    events = chat.stream(session, user, agent, body.conversation_id, body.message)
    return StreamingResponse(
        frames(events), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
    )
