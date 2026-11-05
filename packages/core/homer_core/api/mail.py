from typing import Annotated

from fastapi import APIRouter, Query

from homer_core.api.deps import CurrentUser, RuntimeDep, SessionDep
from homer_core.api.schemas.approvals import ApprovalOut
from homer_core.api.schemas.mail import (
    ComposeDraftOut,
    ComposeIn,
    FolderOut,
    LabelChange,
    ThreadLabelsOut,
    ThreadOut,
    ThreadPageOut,
    WriteIn,
    WriteOut,
)
from homer_core.services import drafts, mail
from homer_core.services.rules import get_rules

router = APIRouter(prefix="/api/mail", tags=["mail"])


@router.get("/folders")
async def folders(user: CurrentUser, runtime: RuntimeDep) -> list[FolderOut]:
    return [FolderOut.model_validate(f) for f in await mail.folders(runtime.manager)]


@router.get("/threads")
async def threads(
    user: CurrentUser,
    runtime: RuntimeDep,
    folder: str = "inbox",
    q: str = "",
    page_token: str | None = None,
    size: Annotated[int, Query(ge=1, le=25)] = 20,
) -> ThreadPageOut:
    page = await mail.list_threads(runtime.manager, folder, q, page_token, size)
    return ThreadPageOut.model_validate(page)


@router.get("/threads/{thread_id}")
async def thread(
    thread_id: str, user: CurrentUser, runtime: RuntimeDep, images: bool = False
) -> ThreadOut:
    return ThreadOut.model_validate(await mail.thread(runtime.manager, thread_id, images))


@router.post("/threads/{thread_id}/labels")
async def change_labels(
    thread_id: str, body: LabelChange, user: CurrentUser, session: SessionDep, runtime: RuntimeDep
) -> ThreadLabelsOut:
    result = await mail.change_labels(
        session, user, runtime.manager, thread_id, body.add, body.remove
    )
    return ThreadLabelsOut.model_validate(result)


@router.get("/threads/{thread_id}/reply")
async def reply_draft(
    thread_id: str, user: CurrentUser, runtime: RuntimeDep, mode: mail.ReplyMode = "reply"
) -> ComposeDraftOut:
    return ComposeDraftOut.model_validate(await mail.reply_draft(runtime.manager, thread_id, mode))


@router.post("/compose")
async def compose(
    body: ComposeIn, user: CurrentUser, session: SessionDep, runtime: RuntimeDep
) -> ApprovalOut:
    approval = await mail.compose(
        session, user, runtime.manager, body.to, body.subject, body.body, body.thread_id
    )
    return ApprovalOut.from_row(approval)


@router.post("/write")
async def write(
    body: WriteIn, user: CurrentUser, session: SessionDep, runtime: RuntimeDep
) -> WriteOut:
    messages = await mail.read_thread(runtime.manager, body.thread_id) if body.thread_id else None
    text = await drafts.compose_body(
        user, runtime.model, get_rules(session, user.id), body.instruction, body.to, messages
    )
    return WriteOut(body=text)
