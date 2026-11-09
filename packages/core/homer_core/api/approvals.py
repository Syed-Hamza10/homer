from typing import Literal

from fastapi import APIRouter

from homer_core.api.deps import CurrentUser, RuntimeDep, SessionDep
from homer_core.api.schemas.approvals import ApprovalOut
from homer_core.services import approval_edits, approvals
from homer_core.services.approval_edits import EventEdit, MailEdit

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


@router.get("")
def list_approvals(
    user: CurrentUser,
    session: SessionDep,
    status: Literal["pending"] = "pending",
    conversation_id: int | None = None,
) -> list[ApprovalOut]:
    """Pending approvals, or every approval of one conversation with its current status."""
    rows = (
        approvals.list_pending(session, user)
        if conversation_id is None
        else approvals.list_for_conversation(session, user, conversation_id)
    )
    return [ApprovalOut.from_row(row) for row in rows]


@router.post("/{approval_id}/approve")
async def approve(
    approval_id: int, user: CurrentUser, session: SessionDep, runtime: RuntimeDep
) -> ApprovalOut:
    return ApprovalOut.from_row(
        await approvals.approve(session, user, approval_id, runtime.manager)
    )


@router.post("/{approval_id}/reject")
async def reject(
    approval_id: int, user: CurrentUser, session: SessionDep, runtime: RuntimeDep
) -> ApprovalOut:
    return ApprovalOut.from_row(
        await approvals.discard(session, user, approval_id, runtime.manager)
    )


@router.post("/{approval_id}/edit")
async def edit(
    approval_id: int,
    body: MailEdit | EventEdit,
    user: CurrentUser,
    session: SessionDep,
    runtime: RuntimeDep,
) -> ApprovalOut:
    return ApprovalOut.from_row(
        await approval_edits.edit(session, user, approval_id, runtime.manager, body)
    )
