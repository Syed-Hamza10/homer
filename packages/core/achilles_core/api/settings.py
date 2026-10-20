from fastapi import APIRouter

from achilles_core.api.deps import (
    CurrentUser,
    HttpClientDep,
    RuntimeDep,
    SessionDep,
    SettingsDep,
)
from achilles_core.llm import build_model
from achilles_core.platform import Tier
from achilles_core.services import models
from achilles_core.services.rules import ClientRules, get_rules, save_rules

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
def read(user: CurrentUser, session: SessionDep) -> ClientRules:
    return get_rules(session, user.id)


@router.put("")
def update(body: ClientRules, user: CurrentUser, session: SessionDep) -> ClientRules:
    return save_rules(session, user.id, body)


@router.get("/models")
def model_options(user: CurrentUser, session: SessionDep) -> models.ModelOptions:
    return models.options(get_rules(session, user.id).model_tier)


@router.post("/smoke")
async def smoke(
    user: CurrentUser,
    runtime: RuntimeDep,
    settings: SettingsDep,
    client: HttpClientDep,
    tier: Tier | None = None,
) -> models.SmokeResult:
    model = runtime.model if tier is None else build_model(settings, client, tier)
    return await models.smoke(model)
