from fastapi import APIRouter

from homer_core.api.deps import (
    CurrentUser,
    HttpClientDep,
    RuntimeDep,
    SessionDep,
    SettingsDep,
)
from homer_core.api.schemas.settings import UserSettings
from homer_core.llm import build_model
from homer_core.platform import Tier
from homer_core.services import models
from homer_core.services.rules import get_rules, save_rules
from homer_core.services.users import set_timezone

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
def read(user: CurrentUser, session: SessionDep) -> UserSettings:
    return UserSettings(**get_rules(session, user.id).model_dump(), timezone=user.timezone)


@router.put("")
def update(body: UserSettings, user: CurrentUser, session: SessionDep) -> UserSettings:
    save_rules(session, user.id, body.rules)
    set_timezone(session, user, body.timezone)
    return body


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
