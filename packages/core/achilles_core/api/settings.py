from fastapi import APIRouter

from achilles_core.api.deps import CurrentUser, SessionDep
from achilles_core.services.rules import ClientRules, get_rules, save_rules

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
def read(user: CurrentUser, session: SessionDep) -> ClientRules:
    return get_rules(session, user.id)


@router.put("")
def update(body: ClientRules, user: CurrentUser, session: SessionDep) -> ClientRules:
    return save_rules(session, user.id, body)
