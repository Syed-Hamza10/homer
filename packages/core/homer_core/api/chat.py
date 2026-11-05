import json
from collections.abc import AsyncIterator
from contextlib import aclosing

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from homer_core.api.deps import CurrentUser, RuntimeDep, SessionDep
from homer_core.api.schemas.chat import ChatRequest
from homer_core.services import chat
from homer_core.services.conversations import get_conversation

router = APIRouter(prefix="/api", tags=["chat"])


def sse_frame(event: chat.ChatEvent) -> str:
    return f"event: {event.name}\ndata: {json.dumps(event.data)}\n\n"


async def frames(events: AsyncIterator[chat.ChatEvent]) -> AsyncIterator[str]:
    async with aclosing(events):
        async for event in events:
            yield sse_frame(event)


@router.post("/chat")
async def post_chat(
    body: ChatRequest, user: CurrentUser, session: SessionDep, runtime: RuntimeDep
) -> StreamingResponse:
    if body.conversation_id is not None:
        get_conversation(session, user, body.conversation_id)
    events = chat.stream(session, user, runtime, body.conversation_id, body.message)
    return StreamingResponse(
        frames(events), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
    )
