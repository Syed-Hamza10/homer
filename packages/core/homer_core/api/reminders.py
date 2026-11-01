from fastapi import APIRouter

from homer_core.api.deps import CurrentUser, SessionDep
from homer_core.api.schemas.reminders import ReminderOut
from homer_core.services.reminders import list_reminders

router = APIRouter(prefix="/api/reminders", tags=["reminders"])


@router.get("")
def list_all(user: CurrentUser, session: SessionDep) -> list[ReminderOut]:
    return [
        ReminderOut.model_validate(item, from_attributes=True)
        for item in list_reminders(session, user)
    ]
