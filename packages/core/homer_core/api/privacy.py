from fastapi import APIRouter

from homer_core.api.deps import CurrentUser, SessionDep, SettingsDep
from homer_core.api.schemas.privacy import (
    HostOut,
    HostsResponse,
    UsageResponse,
    WebSearchRequest,
    WebSearchResponse,
    WipeRequest,
    WipeResponse,
)
from homer_core.services import privacy
from homer_core.services.errors import DomainError
from homer_core.services.privacy import host_usage, token_usage

router = APIRouter(prefix="/api/privacy", tags=["privacy"])


@router.get("/hosts")
def hosts(user: CurrentUser, session: SessionDep, settings: SettingsDep) -> HostsResponse:
    configured = privacy.get_web_search(session, user.id)
    return HostsResponse(
        hosts=[HostOut.model_validate(item, from_attributes=True) for item in host_usage(session)],
        web_search=settings.web_search,
        web_search_configured=settings.web_search if configured is None else configured,
    )


@router.get("/usage")
def usage(user: CurrentUser, session: SessionDep) -> UsageResponse:
    return UsageResponse.model_validate(token_usage(session, user), from_attributes=True)


@router.put("/web-search")
def web_search(
    body: WebSearchRequest, user: CurrentUser, session: SessionDep, settings: SettingsDep
) -> WebSearchResponse:
    privacy.set_web_search(session, user.id, body.enabled)
    return WebSearchResponse(
        enabled=body.enabled, restart_required=body.enabled != settings.web_search
    )


@router.post("/wipe")
def wipe(body: WipeRequest, user: CurrentUser, session: SessionDep) -> WipeResponse:
    if not body.confirm:
        raise DomainError("confirm must be true")
    return WipeResponse(deleted=privacy.wipe(session, user))
