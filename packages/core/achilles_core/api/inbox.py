from fastapi import APIRouter
from sqlmodel import Session

from achilles_core.agent.runtime import Runtime
from achilles_core.api.deps import CurrentUser, RuntimeDep, SessionDep
from achilles_core.api.schemas.skills import (
    DraftOut,
    EmailOut,
    FollowUpOut,
    FollowUpRequest,
    RefreshOut,
    TriageOut,
)
from achilles_core.db.models import User
from achilles_core.services import drafts, followups, inbox
from achilles_core.services.rules import get_rules

router = APIRouter(prefix="/api/inbox", tags=["inbox"])


@router.get("")
def list_messages(user: CurrentUser, session: SessionDep) -> list[EmailOut]:
    return [EmailOut.from_row(row) for row in inbox.list_inbox(session, user)]


async def refresh_and_triage(user: User, session: Session, runtime: Runtime) -> RefreshOut:
    rules = get_rules(session, user.id)
    rows = await inbox.refresh_inbox(session, user, runtime.manager, rules)
    counts = await inbox.triage(session, user, runtime.manager, rules)
    return RefreshOut(messages=len(rows), **counts)


@router.post("/refresh")
async def refresh(user: CurrentUser, session: SessionDep, runtime: RuntimeDep) -> RefreshOut:
    return await refresh_and_triage(user, session, runtime)


@router.post("/triage")
async def triage(user: CurrentUser, session: SessionDep, runtime: RuntimeDep) -> TriageOut:
    result = await refresh_and_triage(user, session, runtime)
    return TriageOut(labeled=result.labeled, failed=result.failed)


@router.post("/{message_id}/archive")
async def archive(
    message_id: str, user: CurrentUser, session: SessionDep, runtime: RuntimeDep
) -> EmailOut:
    return EmailOut.from_row(await inbox.archive(session, user, runtime.manager, message_id))


@router.post("/{message_id}/follow-up")
async def create_follow_up(
    message_id: str,
    body: FollowUpRequest,
    user: CurrentUser,
    session: SessionDep,
    runtime: RuntimeDep,
) -> FollowUpOut:
    row = inbox.get_email(session, user, message_id)
    rules = get_rules(session, user.id)
    followup = await followups.create_followup(
        session, user, runtime.manager, rules, row.thread_id, body.days
    )
    return FollowUpOut.from_row(followup)


@router.post("/{message_id}/draft")
async def draft(
    message_id: str, user: CurrentUser, session: SessionDep, runtime: RuntimeDep
) -> DraftOut:
    rules = get_rules(session, user.id)
    result = await drafts.draft_reply(user, runtime.manager, runtime.model, rules, message_id)
    return DraftOut(**result)
