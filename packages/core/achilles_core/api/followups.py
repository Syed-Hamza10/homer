from fastapi import APIRouter

from achilles_core.api.deps import CurrentUser, RuntimeDep, SessionDep
from achilles_core.api.schemas.approvals import ApprovalOut
from achilles_core.services import followups

router = APIRouter(prefix="/api/followups", tags=["followups"])


@router.post("/{followup_id}/send")
async def request_send(
    followup_id: int, user: CurrentUser, session: SessionDep, runtime: RuntimeDep
) -> ApprovalOut:
    approval = await followups.request_send(session, user, runtime.manager, followup_id)
    return ApprovalOut.from_row(approval)
