from typing import Literal

from fastapi import APIRouter

from homer_core.api.deps import CurrentUser, RuntimeDep, SessionDep
from homer_core.api.schemas.approvals import ApprovalOut
from homer_core.services import approvals

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


@router.get("")
def list_approvals(
    user: CurrentUser, session: SessionDep, status: Literal["pending"] = "pending"
) -> list[ApprovalOut]:
    return [ApprovalOut.from_row(row) for row in approvals.list_pending(session, user)]


@router.post("/{approval_id}/approve")
async def approve(
    approval_id: int, user: CurrentUser, session: SessionDep, runtime: RuntimeDep
) -> ApprovalOut:
    return ApprovalOut.from_row(
        await approvals.approve(session, user, approval_id, runtime.manager)
    )


@router.post("/{approval_id}/reject")
def reject(approval_id: int, user: CurrentUser, session: SessionDep) -> ApprovalOut:
    return ApprovalOut.from_row(approvals.reject(session, user, approval_id))
