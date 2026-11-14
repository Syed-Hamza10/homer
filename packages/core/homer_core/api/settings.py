from fastapi import APIRouter

from homer_core.agent.prompt import known_name
from homer_core.api.deps import (
    CurrentUser,
    HttpClientDep,
    RuntimeDep,
    SessionDep,
    SettingsDep,
)
from homer_core.api.schemas.settings import SearchIn, SearchOut, SearchProbe, UserSettings
from homer_core.llm import build_model
from homer_core.platform import Tier
from homer_core.services import models
from homer_core.services.rules import get_rules, save_rules
from homer_core.services.search_settings import (
    SearchSettings,
    key_hint,
    load_search,
    save_search,
)
from homer_core.services.users import set_name, set_timezone

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
def read(user: CurrentUser, session: SessionDep) -> UserSettings:
    rules = get_rules(session, user.id).model_dump()
    return UserSettings(**rules, timezone=user.timezone, name=known_name(user.name) or "")


@router.put("")
def update(body: UserSettings, user: CurrentUser, session: SessionDep) -> UserSettings:
    save_rules(session, user.id, body.rules)
    set_timezone(session, user, body.timezone)
    if body.name is not None:
        set_name(session, user, body.name)
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


def search_out(search: SearchSettings) -> SearchOut:
    return SearchOut(
        provider=search.provider,
        api_provider=search.api_provider,
        fallback=search.fallback,
        key_hint=key_hint(search.api_key),
        hosts=list(search.hosts()),
    )


@router.get("/search")
def read_search(user: CurrentUser, settings: SettingsDep) -> SearchOut:
    return search_out(load_search(settings))


@router.put("/search")
def update_search(body: SearchIn, user: CurrentUser, settings: SettingsDep) -> SearchOut:
    """A missing `api_key` keeps the saved key; an empty one removes it."""
    key = load_search(settings).api_key if body.api_key is None else body.api_key.strip()
    search = SearchSettings(
        provider=body.provider, api_provider=body.api_provider, fallback=body.fallback, api_key=key
    )
    save_search(settings, search)
    return search_out(search)


@router.post("/search/test")
async def probe_search(user: CurrentUser, runtime: RuntimeDep) -> SearchProbe:
    return SearchProbe.model_validate(await runtime.manager.call("search", "search_test", {}))
