from fastapi import APIRouter, status

from homer_core.api.deps import CurrentUser, SessionDep
from homer_core.api.schemas.facts import FactOut
from homer_core.services.facts import delete_fact, list_facts

router = APIRouter(prefix="/api/facts", tags=["facts"])


@router.get("")
def list_all(user: CurrentUser, session: SessionDep) -> list[FactOut]:
    facts = list_facts(session, user)
    return [FactOut.model_validate(fact, from_attributes=True) for fact in facts]


@router.delete("/{fact_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(fact_id: int, user: CurrentUser, session: SessionDep) -> None:
    delete_fact(session, user, fact_id)
